from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..db import connect
from ..hr_users import get_hr_user_by_id, list_email_ingest_users, mark_email_ingest_run
from ..phase2_repositories import create_resume_import_batch, finalize_resume_import_batch, insert_resume_import_result
from ..repositories import (
    add_candidate_timeline_event,
    add_log,
    create_task,
    get_task,
    insert_candidate,
    insert_score,
    insert_snapshot,
)
from ..scoring_targets import get_scoring_target
from ..search_service import ResumeSearchService
from .dedup import EmailResumeDeduplicator
from .dispatcher import EmailResumeDispatcher
from .importer import EmailResumeImporter
from .models import EmailIngestRunSummary, EmailResumeFile
from .scanner import EmailResumeScanner
from .scorer import EmailResumeScorer


UTC = timezone.utc
EMAIL_INGEST_SOURCE = "email_import"


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _to_sql(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


class EmailResumeIngestService:
    def __init__(
        self,
        *,
        scanner: EmailResumeScanner | None = None,
        dedup: EmailResumeDeduplicator | None = None,
        importer: EmailResumeImporter | None = None,
        scorer: EmailResumeScorer | None = None,
        dispatcher: EmailResumeDispatcher | None = None,
        search_service: ResumeSearchService | None = None,
    ) -> None:
        self.scanner = scanner or EmailResumeScanner()
        self.dedup = dedup or EmailResumeDeduplicator()
        self.importer = importer or EmailResumeImporter()
        self.scorer = scorer or EmailResumeScorer()
        self.dispatcher = dispatcher or EmailResumeDispatcher()
        self.search_service = search_service or ResumeSearchService()

    def run_once(
        self,
        *,
        user_id: str,
        trigger: str = "manual",
        max_files: int | None = None,
        ingest_directory: str | None = None,
    ) -> dict[str, Any]:
        user = self._require_ingest_user(user_id)
        scorecard_id = str(user.get("default_scorecard_id") or "").strip()
        source_name = EMAIL_INGEST_SOURCE
        scan_directory = str(ingest_directory or user.get("email_ingest_directory") or "").strip() or None
        target = get_scoring_target(scorecard_id)
        if not target:
            raise ValueError(f"默认评分卡不存在或不可用: {scorecard_id}")

        scanned, effective_scan_directory = self._scan_user_files(
            user=user,
            max_files=max_files,
            ingest_directory=scan_directory,
        )
        scan_directory_display = (
            effective_scan_directory
            or scan_directory
            or str((self.scanner.root_dir / str(user["id"])).resolve())
        )
        summary = EmailIngestRunSummary(
            ok=True,
            user_id=str(user["id"]),
            scorecard_id=scorecard_id,
            source=source_name,
            trigger=str(trigger or "manual"),
            scan_directory=scan_directory_display,
            scanned_files=len(scanned),
        )
        if not scanned:
            self._touch_next_run(user, now=_utc_now())
            return asdict(summary)

        candidates_to_process = []
        for file_ref in scanned:
            file_sha1 = self.dedup.file_sha1(file_ref.file_path)
            existing = self.dedup.get_record_by_hash(user_id=str(user["id"]), file_sha1=file_sha1)
            if existing:
                summary.duplicate_files += 1
                summary.skipped_count += 1
                continue
            candidates_to_process.append((file_ref, file_sha1))

        summary.new_files = len(candidates_to_process)
        if not candidates_to_process:
            self._touch_next_run(user, now=_utc_now())
            return asdict(summary)

        task = self._get_or_create_email_task(
            user_id=str(user["id"]),
            scorecard_id=scorecard_id,
        )
        summary.task_id = str(task["id"])
        batch = create_resume_import_batch(
            scorecard_id=scorecard_id,
            scorecard_name=str(target.get("name") or scorecard_id),
            batch_name=f"邮箱采集-{user.get('username') or user.get('display_name') or user.get('id')}",
            created_by=f"email_ingest:{user.get('username') or user.get('id')}",
            total_files=len(candidates_to_process),
            summary={
                "source": source_name,
                "trigger": trigger,
                "user_id": str(user["id"]),
                "email_root": str(self.scanner.root_dir),
                "ingest_directory": scan_directory_display,
            },
        )
        batch_id = str(batch["id"])
        summary.batch_id = batch_id

        profile_items: list[dict[str, Any]] = []
        stored_results = 0
        for file_ref, file_sha1 in candidates_to_process:
            record = self.dedup.create_processing_record(
                user_id=str(user["id"]),
                source=source_name,
                source_date=file_ref.source_date,
                file_ref=file_ref,
                file_sha1=file_sha1,
                scorecard_id=scorecard_id,
                task_id=str(task["id"]),
                trigger=trigger,
            )
            try:
                outcome = self._process_one_file(
                    user=user,
                    task_id=str(task["id"]),
                    batch_id=batch_id,
                    scorecard_id=scorecard_id,
                    source=source_name,
                    file_ref=file_ref,
                    file_sha1=file_sha1,
                    ingest_record=record,
                )
                profile_items.append(outcome["profile"])
                summary.processed_files += 1
                summary.results.append(outcome["result"])
                stored_results += 1
                decision = str(outcome["decision"])
                if decision == "recommend":
                    summary.recommend_count += 1
                elif decision == "review":
                    summary.review_count += 1
                else:
                    summary.reject_count += 1
            except Exception as exc:
                summary.ok = False
                summary.failed_count += 1
                summary.reject_count += 1
                summary.errors.append(str(exc))
                self.dedup.mark_failed(
                    str(record.get("id") or ""),
                    error=str(exc),
                    evidence={
                        "task_id": str(task["id"]),
                        "batch_id": batch_id,
                        "file_path": str(file_ref.file_path),
                        "file_sha1": file_sha1,
                    },
                    increment_retry=False,
                )
                failed_result = insert_resume_import_result(
                    batch_id,
                    {
                        "scorecard_id": scorecard_id,
                        "resume_profile_id": None,
                        "filename": file_ref.file_name,
                        "file_path": str(file_ref.file_path),
                        "parse_status": "failed",
                        "extracted_name": None,
                        "years_experience": None,
                        "education_level": None,
                        "location": None,
                        "total_score": 0.0,
                        "decision": "reject",
                        "hard_filter_pass": False,
                        "hard_filter_fail_reasons": [str(exc)],
                        "matched_terms": [],
                        "missing_terms": [],
                        "dimension_scores": {},
                        "summary": "解析失败",
                        "detail": {
                            "error": str(exc),
                            "file_sha1": file_sha1,
                            "ingest_record_id": str(record.get("id") or ""),
                            "source": source_name,
                        },
                    },
                )
                stored_results += 1
                add_log(
                    str(task["id"]),
                    "error",
                    "email.ingest.failed",
                    {
                        "ingest_record_id": str(record.get("id") or ""),
                        "filename": file_ref.file_name,
                        "error": str(exc),
                        "import_result_id": str(failed_result.get("id") or ""),
                    },
                )

        if profile_items:
            self.search_service.upsert_profiles(items=profile_items)

        finalize_resume_import_batch(
            batch_id,
            processed_files=stored_results,
            recommend_count=summary.recommend_count,
            review_count=summary.review_count,
            reject_count=summary.reject_count,
            summary={
                "source": source_name,
                "trigger": trigger,
                "user_id": str(user["id"]),
                "processed_files": summary.processed_files,
                "failed_count": summary.failed_count,
                "duplicate_files": summary.duplicate_files,
            },
        )
        self._touch_next_run(user, now=_utc_now())
        return asdict(summary)

    def _scan_user_files(
        self,
        *,
        user: dict[str, Any],
        max_files: int | None,
        ingest_directory: str | None,
    ) -> tuple[list[EmailResumeFile], str | None]:
        normalized_user_id = str(user.get("id") or "").strip()
        if not normalized_user_id:
            return [], None

        # Explicit directory (from UI run-once or saved config) takes highest priority.
        if ingest_directory:
            scanned = self.scanner.scan_user(
                normalized_user_id,
                limit=max_files,
                ingest_directory=ingest_directory,
            )
            return scanned, ingest_directory

        scanned = self.scanner.scan_user(normalized_user_id, limit=max_files, ingest_directory=None)
        if scanned:
            return scanned, None

        # Backward-compatible fallback for deployments where attachments are under username path.
        username = str(user.get("username") or "").strip()
        if username and username != normalized_user_id:
            scanned = self.scanner.scan_user(
                normalized_user_id,
                limit=max_files,
                ingest_directory=username,
            )
            if scanned:
                return scanned, username
        return [], None

    def retry_failed(
        self,
        *,
        user_id: str | None = None,
        max_retry: int = 3,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = self.dedup.list_failed_records(user_id=user_id, max_retry=max_retry, limit=limit)
        retried = 0
        succeeded = 0
        failed = 0
        details: list[dict[str, Any]] = []
        for row in rows:
            retried += 1
            file_path = Path(str(row.get("file_path") or ""))
            if not file_path.exists() or not file_path.is_file():
                failed += 1
                self.dedup.mark_failed(
                    str(row.get("id") or ""),
                    error="重试失败：文件不存在",
                    evidence={"file_path": str(file_path)},
                    increment_retry=True,
                )
                details.append(
                    {
                        "ingest_record_id": str(row.get("id") or ""),
                        "ok": False,
                        "error": "文件不存在",
                    }
                )
                continue
            file_ref = EmailResumeFile(
                user_id=str(row.get("user_id") or ""),
                source_date=str(row.get("source_date") or ""),
                file_path=file_path,
                file_name=str(row.get("file_name") or file_path.name),
                file_size=int(row.get("file_size") or file_path.stat().st_size or 0),
                modified_at=float(file_path.stat().st_mtime or 0.0),
            )
            user = self._require_ingest_user(str(row.get("user_id") or ""))
            task = self._get_or_create_email_task(
                user_id=str(user["id"]),
                scorecard_id=str(row.get("scorecard_id") or user.get("default_scorecard_id") or ""),
            )
            target_scorecard_id = str(row.get("scorecard_id") or user.get("default_scorecard_id") or "").strip()
            if not get_scoring_target(target_scorecard_id):
                failed += 1
                self.dedup.mark_failed(
                    str(row.get("id") or ""),
                    error=f"重试失败：评分卡不存在 {target_scorecard_id}",
                    evidence={"task_id": str(task.get("id") or "")},
                    increment_retry=True,
                )
                details.append(
                    {
                        "ingest_record_id": str(row.get("id") or ""),
                        "ok": False,
                        "error": f"评分卡不存在 {target_scorecard_id}",
                    }
                )
                continue
            batch = create_resume_import_batch(
                scorecard_id=target_scorecard_id,
                scorecard_name=str(get_scoring_target(target_scorecard_id).get("name") or target_scorecard_id),
                batch_name=f"邮箱采集重试-{user.get('username') or user.get('id')}",
                created_by=f"email_ingest_retry:{user.get('username') or user.get('id')}",
                total_files=1,
                summary={"retry": True, "ingest_record_id": str(row.get("id") or "")},
            )
            batch_id = str(batch["id"])
            processing_record = self.dedup.create_processing_record(
                user_id=str(user["id"]),
                source=EMAIL_INGEST_SOURCE,
                source_date=str(file_ref.source_date),
                file_ref=file_ref,
                file_sha1=str(row.get("file_sha1") or ""),
                scorecard_id=target_scorecard_id,
                task_id=str(task["id"]),
                trigger="retry",
                retry_count=int(row.get("retry_count") or 0) + 1,
                record_id=str(row.get("id") or ""),
            )
            try:
                outcome = self._process_one_file(
                    user=user,
                    task_id=str(task["id"]),
                    batch_id=batch_id,
                    scorecard_id=target_scorecard_id,
                    source=EMAIL_INGEST_SOURCE,
                    file_ref=file_ref,
                    file_sha1=str(row.get("file_sha1") or ""),
                    ingest_record=processing_record,
                )
                finalize_resume_import_batch(
                    batch_id,
                    processed_files=1,
                    recommend_count=1 if outcome["decision"] == "recommend" else 0,
                    review_count=1 if outcome["decision"] == "review" else 0,
                    reject_count=1 if outcome["decision"] == "reject" else 0,
                    summary={"retry": True, "decision": outcome["decision"]},
                )
                self.search_service.upsert_profiles(items=[outcome["profile"]])
                succeeded += 1
                details.append(
                    {
                        "ingest_record_id": str(row.get("id") or ""),
                        "ok": True,
                        "candidate_id": outcome["result"]["candidate_id"],
                        "decision": outcome["decision"],
                    }
                )
            except Exception as exc:
                failed += 1
                self.dedup.mark_failed(
                    str(row.get("id") or ""),
                    error=f"重试失败：{exc}",
                    evidence={"batch_id": batch_id, "task_id": str(task["id"])},
                    increment_retry=False,
                )
                finalize_resume_import_batch(
                    batch_id,
                    processed_files=1,
                    recommend_count=0,
                    review_count=0,
                    reject_count=1,
                    summary={"retry": True, "error": str(exc)},
                )
                details.append(
                    {
                        "ingest_record_id": str(row.get("id") or ""),
                        "ok": False,
                        "error": str(exc),
                    }
                )
        return {
            "ok": failed == 0,
            "retried": retried,
            "succeeded": succeeded,
            "failed": failed,
            "items": details,
        }

    def run_due_users(self) -> dict[str, Any]:
        users = list_email_ingest_users(due_only=True)
        runs: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for user in users:
            try:
                runs.append(
                    self.run_once(
                        user_id=str(user.get("id") or ""),
                        trigger="scheduler",
                    )
                )
            except Exception as exc:
                errors.append(
                    {
                        "user_id": str(user.get("id") or ""),
                        "username": str(user.get("username") or ""),
                        "error": str(exc),
                    }
                )
        return {
            "ok": not errors,
            "triggered": len(runs),
            "failed": len(errors),
            "runs": runs,
            "errors": errors,
        }

    def run_scheduler_loop(self, *, poll_seconds: int = 60, once: bool = False) -> dict[str, Any]:
        poll_seconds = max(5, int(poll_seconds))
        last_summary: dict[str, Any] = {"ok": True, "triggered": 0, "failed": 0, "runs": [], "errors": []}
        while True:
            last_summary = self.run_due_users()
            if once:
                return last_summary
            time.sleep(poll_seconds)

    def list_records(self, *, user_id: str | None = None, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return self.dedup.list_records(user_id=user_id, status=status, limit=limit)

    def get_record(self, *, record_id: str) -> dict[str, Any] | None:
        return self.dedup.get_record_by_id(record_id=record_id)

    def _process_one_file(
        self,
        *,
        user: dict[str, Any],
        task_id: str,
        batch_id: str,
        scorecard_id: str,
        source: str,
        file_ref: EmailResumeFile,
        file_sha1: str,
        ingest_record: dict[str, Any],
    ) -> dict[str, Any]:
        source_candidate_id = f"{batch_id}:{file_sha1}"
        profile, text = self.importer.import_file(
            file_ref=file_ref,
            file_sha1=file_sha1,
            source=source,
            source_candidate_id=source_candidate_id,
            raw_resume_entry={
                "source": source,
                "source_date": file_ref.source_date,
                "user_id": str(user.get("id") or ""),
                "file_path": str(file_ref.file_path),
                "ingest_record_id": str(ingest_record.get("id") or ""),
            },
        )
        score = self.scorer.score_profile(scorecard_id=scorecard_id, profile=profile)
        profile_id = f"{profile['source']}:{profile['external_id']}"
        candidate_id = insert_candidate(
            task_id,
            {
                "source": source,
                "external_id": profile.get("external_id"),
                "name": profile.get("name"),
                "age": None,
                "education_level": profile.get("education_level"),
                "major": None,
                "years_experience": profile.get("years_experience"),
                "current_company": profile.get("latest_company"),
                "current_title": profile.get("latest_title"),
                "expected_salary": None,
                "location": profile.get("city"),
                "last_active_time": None,
                "raw_summary": str((profile.get("raw_profile") or {}).get("summary") or "")[:1200],
                "normalized_fields": {},
            },
        )
        evidence_map = {
            "source": source,
            "ingest_record_id": str(ingest_record.get("id") or ""),
            "file_sha1": file_sha1,
            "file_path": str(file_ref.file_path),
            "source_date": file_ref.source_date,
            "resume_profile_id": profile_id,
        }
        insert_snapshot(
            candidate_id,
            "email_attachment_resume",
            str(file_ref.file_path),
            text,
            evidence_map,
        )
        insert_score(
            candidate_id,
            scorecard_id,
            {
                "hard_filter_pass": score.hard_filter_pass,
                "hard_filter_fail_reasons": score.hard_filter_fail_reasons,
                "dimension_scores": score.dimension_scores,
                "total_score": score.total_score,
                "decision": score.decision,
                "review_reasons": score.review_reasons,
            },
        )
        dispatch = self.dispatcher.dispatch(
            ingest_record_id=str(ingest_record.get("id") or ""),
            candidate_id=candidate_id,
            user=user,
            decision=score.decision,
            score=score.total_score,
            source=source,
        )
        import_result = insert_resume_import_result(
            batch_id,
            {
                "scorecard_id": scorecard_id,
                "resume_profile_id": profile_id,
                "filename": file_ref.file_name,
                "file_path": str(file_ref.file_path),
                "parse_status": "completed",
                "extracted_name": profile.get("name"),
                "years_experience": profile.get("years_experience"),
                "education_level": profile.get("education_level"),
                "location": profile.get("city"),
                "total_score": score.total_score,
                "decision": score.decision,
                "hard_filter_pass": score.hard_filter_pass,
                "hard_filter_fail_reasons": score.hard_filter_fail_reasons,
                "matched_terms": score.matched_terms,
                "missing_terms": score.missing_terms,
                "dimension_scores": score.dimension_scores,
                "summary": str((profile.get("raw_profile") or {}).get("summary") or "")[:280],
                "detail": {
                    "profile": profile,
                    "blocked_terms": score.blocked_terms,
                    "file_sha1": file_sha1,
                    "ingest_record_id": str(ingest_record.get("id") or ""),
                    "dispatch": dispatch,
                    "source": source,
                },
            },
        )
        self.dedup.mark_completed(
            str(ingest_record.get("id") or ""),
            batch_id=batch_id,
            import_result_id=str(import_result.get("id") or ""),
            candidate_id=candidate_id,
            resume_profile_id=profile_id,
            decision=score.decision,
            total_score=score.total_score,
            parse_status="completed",
            evidence={
                "source": source,
                "file_sha1": file_sha1,
                "candidate_id": candidate_id,
                "resume_profile_id": profile_id,
                "dispatch": dispatch,
            },
        )
        add_log(
            task_id,
            "info",
            "email.ingest.completed",
            {
                "ingest_record_id": str(ingest_record.get("id") or ""),
                "candidate_id": candidate_id,
                "decision": score.decision,
                "total_score": score.total_score,
                "import_result_id": str(import_result.get("id") or ""),
            },
        )
        add_candidate_timeline_event(
            candidate_id,
            "email_ingested",
            source,
            {
                "ingest_record_id": str(ingest_record.get("id") or ""),
                "batch_id": batch_id,
                "source": source,
                "scorecard_id": scorecard_id,
                "file_path": str(file_ref.file_path),
                "total_score": score.total_score,
                "decision": score.decision,
            },
        )
        return {
            "profile": profile,
            "decision": score.decision,
            "result": {
                "ingest_record_id": str(ingest_record.get("id") or ""),
                "candidate_id": candidate_id,
                "resume_profile_id": profile_id,
                "decision": score.decision,
                "total_score": score.total_score,
                "import_result_id": str(import_result.get("id") or ""),
            },
        }

    def _get_or_create_email_task(self, *, user_id: str, scorecard_id: str) -> dict[str, Any]:
        with connect() as conn:
            rows = conn.execute(
                """
                select *
                from screening_tasks
                where job_id = ? and search_mode = 'email_ingest'
                order by created_at desc
                limit 50
                """,
                (scorecard_id,),
            ).fetchall()
        for row in rows:
            item = dict(row)
            task = get_task(str(item.get("id") or ""))
            if not task:
                continue
            search_config = task.get("search_config") if isinstance(task.get("search_config"), dict) else {}
            if str(search_config.get("user_id") or "") == str(user_id):
                return task
        task_id = create_task(
            {
                "job_id": scorecard_id,
                "search_mode": "email_ingest",
                "sort_by": "manual",
                "max_candidates": 2000,
                "max_pages": 1,
                "search_config": {
                    "source": EMAIL_INGEST_SOURCE,
                    "user_id": user_id,
                    "channel": "email_resume_ingest",
                },
                "require_hr_confirmation": False,
            }
        )
        return get_task(task_id) or {"id": task_id}

    def _touch_next_run(self, user: dict[str, Any], *, now: datetime) -> None:
        interval = int(user.get("email_ingest_interval_minutes") or 60)
        interval = max(5, min(interval, 1440))
        next_run = now + timedelta(minutes=interval)
        mark_email_ingest_run(
            str(user.get("id") or ""),
            next_run_at=_to_sql(next_run),
            last_run_at=_to_sql(now),
        )

    @staticmethod
    def _require_ingest_user(user_id: str) -> dict[str, Any]:
        user = get_hr_user_by_id(str(user_id or "").strip())
        if not user:
            raise LookupError("用户不存在")
        if not bool(user.get("active")):
            raise ValueError("用户已停用")
        if not str(user.get("default_scorecard_id") or "").strip():
            raise ValueError("用户未配置默认评分卡")
        return user
