from __future__ import annotations

import os
from dataclasses import asdict

from .gpt54_adapter import MockBrowserAgent, OpenAIComputerAgent
from .models import TaskStatus
from .playwright_agent import PlaywrightLocalAgent
from .repositories import (
    add_log,
    get_task,
    insert_candidate_action,
    insert_candidate,
    insert_score,
    insert_snapshot,
    mark_task_finished,
    mark_task_started,
    update_task_token_usage,
    update_task_status,
)
from .scoring import score_candidate
from .search_service import ResumeSearchService
from .state_machine import assert_transition


class ScreeningOrchestrator:
    def __init__(self, browser_agent=None, *, search_service: ResumeSearchService | None = None) -> None:
        if browser_agent is not None:
            self.browser_agent = browser_agent
        elif os.getenv("SCREENING_BROWSER_AGENT", "mock").lower() == "playwright":
            self.browser_agent = PlaywrightLocalAgent()
        elif os.getenv("SCREENING_BROWSER_AGENT", "mock").lower() == "openai":
            self.browser_agent = OpenAIComputerAgent()
        else:
            self.browser_agent = MockBrowserAgent()
        self.search_service = search_service or ResumeSearchService()

    def _transition(self, task_id: str, current: str, target: TaskStatus) -> str:
        assert_transition(current, target.value)
        update_task_status(task_id, target.value)
        add_log(task_id, "info", "task.status", {"status": target.value})
        return target.value

    def run_task(self, task_id: str) -> dict:
        task = get_task(task_id)
        if not task:
            raise KeyError(f"Task not found: {task_id}")

        mark_task_started(task_id)
        current_status = task["status"]
        session_id = None
        processed = []
        processed_candidate_ids: list[str] = []
        token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
            "candidates_with_usage": 0,
        }
        try:
            for status in (
                TaskStatus.BOOTING_BROWSER,
                TaskStatus.LOGGING_IN,
                TaskStatus.OPENING_SEARCH_PAGE,
                TaskStatus.CONFIGURING_FILTERS,
                TaskStatus.SCANNING_CANDIDATE_LIST,
            ):
                current_status = self._transition(task_id, current_status, status)

            session_id = self.browser_agent.start_session()
            update_task_status(task_id, current_status, browser_session_id=session_id)
            add_log(task_id, "info", "browser.session", {"browser_session_id": session_id})

            for candidate in self.browser_agent.collect_candidates(
                task["job_id"],
                task["max_candidates"],
                search_mode=task.get("search_mode"),
                search_config=task.get("search_config", {}),
                sort_by=task.get("sort_by"),
                max_pages=task.get("max_pages", 1),
            ):
                current_status = self._transition(task_id, current_status, TaskStatus.OPENING_CANDIDATE)
                add_log(task_id, "info", "candidate.open", {"external_id": candidate.external_id})

                current_status = self._transition(task_id, current_status, TaskStatus.CAPTURING_SNAPSHOT)
                candidate_id = insert_candidate(task_id, asdict(candidate))
                processed_candidate_ids.append(candidate_id)
                snapshot_id = insert_snapshot(
                    candidate_id,
                    "candidate_detail",
                    candidate.screenshot_path,
                    candidate.raw_summary or "",
                    candidate.evidence_map,
                )

                current_status = self._transition(task_id, current_status, TaskStatus.EXTRACTING_FIELDS)
                add_log(task_id, "info", "candidate.extract", {"candidate_id": candidate_id, "snapshot_id": snapshot_id})

                current_status = self._transition(task_id, current_status, TaskStatus.SCORING_CANDIDATE)
                score = score_candidate(
                    task["job_id"],
                    candidate.normalized_fields
                    | {
                        "name": candidate.name,
                        "age": candidate.age,
                        "years_experience": candidate.years_experience,
                        "education_level": candidate.education_level,
                        "major": candidate.major,
                        "current_company": candidate.current_company,
                        "latest_company": candidate.current_company,
                        "current_title": candidate.current_title,
                        "latest_title": candidate.current_title,
                        "expected_salary": candidate.expected_salary,
                        "location": candidate.location,
                        "city": candidate.location,
                        "last_active_time": candidate.last_active_time,
                        "raw_summary": candidate.raw_summary,
                        "resume_summary": candidate.raw_summary,
                        "summary": candidate.raw_summary,
                    },
                )
                insert_score(
                    candidate_id,
                    task["job_id"],
                    {
                        "hard_filter_pass": score.hard_filter_pass,
                        "hard_filter_fail_reasons": score.hard_filter_fail_reasons,
                        "dimension_scores": score.dimension_scores,
                        "total_score": score.total_score,
                        "decision": score.decision.value,
                        "review_reasons": score.review_reasons,
                    },
                )
                if candidate.evidence_map.get("auto_greet_attempted") or candidate.evidence_map.get("auto_greet_clicked"):
                    greeting_status = "success" if candidate.evidence_map.get("auto_greet_clicked") else "skipped"
                    insert_candidate_action(
                        candidate_id,
                        "send_greeting",
                        greeting_status,
                        {
                            "reason": candidate.evidence_map.get("auto_greet_reason"),
                            "threshold": candidate.evidence_map.get("auto_greet_threshold"),
                            "score": candidate.evidence_map.get("auto_greet_score"),
                            "enabled": candidate.evidence_map.get("auto_greet_enabled"),
                        },
                    )
                    add_log(
                        task_id,
                        "info",
                        "candidate.greet_action",
                        {
                            "candidate_id": candidate_id,
                            "status": greeting_status,
                            "reason": candidate.evidence_map.get("auto_greet_reason"),
                        },
                    )
                processed.append({"candidate_id": candidate_id, "decision": score.decision.value, "total_score": score.total_score})
                add_log(task_id, "info", "candidate.scored", processed[-1])

                usage = candidate.evidence_map.get("model_usage")
                if isinstance(usage, dict):
                    token_usage["candidates_with_usage"] += 1
                    token_usage["calls"] += 1
                    token_usage["prompt_tokens"] += self._safe_int(usage.get("prompt_tokens"))
                    token_usage["completion_tokens"] += self._safe_int(usage.get("completion_tokens"))
                    total = self._safe_int(usage.get("total_tokens"))
                    if total == 0:
                        total = self._safe_int(usage.get("prompt_tokens")) + self._safe_int(usage.get("completion_tokens"))
                    token_usage["total_tokens"] += total

            search_index_sync = self._sync_candidates_to_search_index(task_id, processed_candidate_ids)
            current_status = self._transition(task_id, current_status, TaskStatus.AWAITING_HR_REVIEW)
            add_log(
                task_id,
                "info",
                "task.review_ready",
                {"processed_count": len(processed), "search_index_sync": search_index_sync},
            )
            assert_transition(current_status, TaskStatus.COMPLETED.value)
            update_task_token_usage(task_id, token_usage)
            mark_task_finished(task_id, TaskStatus.COMPLETED.value)
            add_log(task_id, "info", "task.token_usage", token_usage)
            add_log(
                task_id,
                "info",
                "task.completed",
                {
                    "processed_count": len(processed),
                    "token_usage": token_usage,
                    "search_index_sync": search_index_sync,
                },
            )
            return {
                "task_id": task_id,
                "browser_session_id": session_id,
                "processed": processed,
                "token_usage": token_usage,
                "search_index_sync": search_index_sync,
            }
        except Exception as exc:
            mark_task_finished(task_id, TaskStatus.FAILED.value)
            add_log(task_id, "error", "task.failed", {"error": str(exc)})
            raise
        finally:
            if hasattr(self.browser_agent, "stop_session"):
                self.browser_agent.stop_session()

    def _sync_candidates_to_search_index(self, task_id: str, candidate_ids: list[str]) -> dict:
        if not candidate_ids:
            summary = {
                "ok": True,
                "task_id": task_id,
                "synced_candidates": 0,
                "upserted_profiles": 0,
                "upserted_chunks": 0,
                "degraded": [],
                "duration_ms": 0,
            }
            add_log(task_id, "info", "search.index_sync", summary)
            return summary
        try:
            summary = {
                "ok": True,
                **self.search_service.sync_candidates(task_id=task_id, candidate_ids=candidate_ids),
            }
            add_log(task_id, "info", "search.index_sync", summary)
            return summary
        except Exception as exc:
            summary = {
                "ok": False,
                "task_id": task_id,
                "synced_candidates": len(candidate_ids),
                "error": str(exc),
            }
            add_log(task_id, "warning", "search.index_sync_failed", summary)
            return summary

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value) if value is not None else 0
        except Exception:
            return 0
