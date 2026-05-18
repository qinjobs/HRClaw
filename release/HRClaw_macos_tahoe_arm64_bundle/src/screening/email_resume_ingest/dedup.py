from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from ..db import connect, dumps, loads
from .models import EmailResumeFile


class EmailResumeDeduplicator:
    @staticmethod
    def file_sha1(file_path: Path) -> str:
        digest = hashlib.sha1()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def get_record_by_hash(self, *, user_id: str, file_sha1: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                """
                select *
                from email_resume_ingest_records
                where user_id = ? and file_sha1 = ?
                limit 1
                """,
                (str(user_id or "").strip(), str(file_sha1 or "").strip()),
            ).fetchone()
        return None if not row else self._normalize_row(dict(row))

    def get_record_by_id(self, *, record_id: str) -> dict[str, Any] | None:
        normalized_record_id = str(record_id or "").strip()
        if not normalized_record_id:
            return None
        with connect() as conn:
            row = conn.execute(
                """
                select *
                from email_resume_ingest_records
                where id = ?
                limit 1
                """,
                (normalized_record_id,),
            ).fetchone()
        return None if not row else self._normalize_row(dict(row))

    def create_processing_record(
        self,
        *,
        user_id: str,
        source: str,
        source_date: str,
        file_ref: EmailResumeFile,
        file_sha1: str,
        scorecard_id: str,
        task_id: str,
        trigger: str,
        retry_count: int = 0,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_id = str(record_id or uuid.uuid4())
        evidence = {
            "trigger": str(trigger or "manual"),
            "source_root": str(file_ref.file_path.parent),
            "file_name": file_ref.file_name,
        }
        with connect() as conn:
            conn.execute(
                """
                insert into email_resume_ingest_records (
                    id, user_id, source, source_date, file_name, file_path, file_sha1, file_size,
                    status, retry_count, task_id, scorecard_id, evidence, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    status = 'processing',
                    error = null,
                    user_id = excluded.user_id,
                    source = excluded.source,
                    source_date = excluded.source_date,
                    file_name = excluded.file_name,
                    file_path = excluded.file_path,
                    file_sha1 = excluded.file_sha1,
                    file_size = excluded.file_size,
                    retry_count = excluded.retry_count,
                    task_id = excluded.task_id,
                    scorecard_id = excluded.scorecard_id,
                    evidence = excluded.evidence,
                    updated_at = current_timestamp
                """,
                (
                    normalized_id,
                    str(user_id or "").strip(),
                    str(source or "").strip(),
                    str(source_date or "").strip(),
                    file_ref.file_name,
                    str(file_ref.file_path),
                    file_sha1,
                    int(file_ref.file_size or 0),
                    max(0, int(retry_count)),
                    str(task_id or "").strip() or None,
                    str(scorecard_id or "").strip() or None,
                    dumps(evidence),
                ),
            )
            row = conn.execute(
                "select * from email_resume_ingest_records where id = ?",
                (normalized_id,),
            ).fetchone()
        return self._normalize_row(dict(row)) if row else {}

    def mark_completed(
        self,
        record_id: str,
        *,
        batch_id: str,
        import_result_id: str,
        candidate_id: str | None,
        resume_profile_id: str | None,
        decision: str,
        total_score: float,
        parse_status: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """
                update email_resume_ingest_records
                set status = 'completed',
                    error = null,
                    batch_id = ?,
                    import_result_id = ?,
                    candidate_id = ?,
                    resume_profile_id = ?,
                    decision = ?,
                    total_score = ?,
                    parse_status = ?,
                    evidence = ?,
                    processed_at = current_timestamp,
                    updated_at = current_timestamp
                where id = ?
                """,
                (
                    str(batch_id or "").strip() or None,
                    str(import_result_id or "").strip() or None,
                    str(candidate_id or "").strip() or None,
                    str(resume_profile_id or "").strip() or None,
                    str(decision or "").strip() or None,
                    float(total_score or 0.0),
                    str(parse_status or "").strip() or None,
                    dumps(evidence or {}),
                    str(record_id or "").strip(),
                ),
            )

    def mark_failed(self, record_id: str, *, error: str, evidence: dict[str, Any] | None = None, increment_retry: bool = False) -> None:
        with connect() as conn:
            conn.execute(
                """
                update email_resume_ingest_records
                set status = 'failed',
                    error = ?,
                    retry_count = case when ? = 1 then retry_count + 1 else retry_count end,
                    evidence = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                (
                    str(error or "").strip() or "unknown error",
                    1 if increment_retry else 0,
                    dumps(evidence or {}),
                    str(record_id or "").strip(),
                ),
            )

    def list_failed_records(
        self,
        *,
        user_id: str | None = None,
        max_retry: int = 3,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses = ["status = 'failed'", "retry_count < ?"]
        params: list[Any] = [max(1, int(max_retry))]
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            clauses.append("user_id = ?")
            params.append(normalized_user_id)
        where_clause = " and ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select *
                from email_resume_ingest_records
                where {where_clause}
                order by updated_at asc, created_at asc
                limit ?
                """,
                (*params, max(1, int(limit))),
            ).fetchall()
        return [self._normalize_row(dict(row)) for row in rows]

    def list_records(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id:
            clauses.append("user_id = ?")
            params.append(normalized_user_id)
        normalized_status = str(status or "").strip()
        if normalized_status:
            clauses.append("status = ?")
            params.append(normalized_status)
        where_clause = " and ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                f"""
                select *
                from email_resume_ingest_records
                where {where_clause}
                order by created_at desc
                limit ?
                """,
                (*params, max(1, int(limit))),
            ).fetchall()
        return [self._normalize_row(dict(row)) for row in rows]

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
        row["retry_count"] = int(row.get("retry_count") or 0)
        row["file_size"] = int(row.get("file_size") or 0)
        row["total_score"] = float(row.get("total_score") or 0.0) if row.get("total_score") is not None else None
        row["evidence"] = loads(row.get("evidence")) or {}
        return row
