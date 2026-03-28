from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import init_db
from .orchestrator import ScreeningOrchestrator
from .repositories import (
    create_task,
    finish_collection_pipeline_run,
    get_collection_pipeline,
    get_system_state,
    insert_collection_pipeline_run,
    list_collection_pipeline_runs,
    list_due_collection_pipelines,
    list_collection_pipelines,
    mark_collection_pipeline_finished,
    mark_collection_pipeline_running,
    set_system_state,
    upsert_collection_pipeline,
)
from .search_service import ResumeSearchService


UTC = timezone.utc
VECTOR_REBUILD_STATE_KEY = "search.vector_rebuild"


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _dt_to_sql(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _sql_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


class CollectionPipelineService:
    def __init__(
        self,
        *,
        orchestrator: ScreeningOrchestrator | None = None,
        search_service: ResumeSearchService | None = None,
    ) -> None:
        init_db()
        self.search_service = search_service or ResumeSearchService()
        self.orchestrator = orchestrator or ScreeningOrchestrator(search_service=self.search_service)

    def upsert_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = upsert_collection_pipeline(payload)
        return self.get_pipeline(pipeline_id) or {"id": pipeline_id}

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any] | None:
        return get_collection_pipeline(pipeline_id)

    def list_pipelines(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        items = list_collection_pipelines(active_only=active_only)
        for item in items:
            item["recent_runs"] = list_collection_pipeline_runs(item["id"], limit=5)
        return items

    def run_due_pipelines(self) -> dict[str, Any]:
        due = list_due_collection_pipelines()
        runs: list[dict[str, Any]] = []
        for pipeline in due:
            runs.append(self.run_pipeline(pipeline["id"], force=True))
        return {
            "ok": True,
            "triggered": len(runs),
            "runs": runs,
        }

    def run_scheduler_loop(self, *, poll_seconds: int = 60, once: bool = False) -> dict[str, Any]:
        poll_seconds = max(5, int(poll_seconds))
        last_summary: dict[str, Any] = {"ok": True, "triggered": 0, "runs": []}
        while True:
            last_summary = self.run_due_pipelines()
            if once:
                return last_summary
            time.sleep(poll_seconds)

    def run_pipeline(self, pipeline_id: str, *, force: bool = False) -> dict[str, Any]:
        pipeline = get_collection_pipeline(pipeline_id)
        if not pipeline:
            raise KeyError(f"Pipeline not found: {pipeline_id}")
        if not pipeline.get("enabled") and not force:
            raise RuntimeError(f"Pipeline is disabled: {pipeline_id}")

        mark_collection_pipeline_running(pipeline_id)
        run_id = insert_collection_pipeline_run(pipeline_id, status="running")
        task_ids: list[str] = []
        task_summaries: list[dict[str, Any]] = []
        total_processed = 0
        total_profiles = 0
        total_chunks = 0
        total_tokens = 0
        started_at = _utc_now()
        summary: dict[str, Any] = {}
        last_task_id: str | None = None
        try:
            search_configs = pipeline.get("search_configs") or [{}]
            runtime_options = pipeline.get("runtime_options") or {}
            for config in search_configs:
                payload = self._build_task_payload(pipeline, config if isinstance(config, dict) else {}, runtime_options)
                task_id = create_task(payload)
                last_task_id = task_id
                task_ids.append(task_id)
                result = self.orchestrator.run_task(task_id)
                processed = len(result.get("processed") or [])
                total_processed += processed
                sync = result.get("search_index_sync") or {}
                total_profiles += int(sync.get("upserted_profiles") or 0)
                total_chunks += int(sync.get("upserted_chunks") or 0)
                total_tokens += int((result.get("token_usage") or {}).get("total_tokens") or 0)
                task_summaries.append(
                    {
                        "task_id": task_id,
                        "job_id": payload["job_id"],
                        "search_mode": payload["search_mode"],
                        "search_config": payload.get("search_config") or {},
                        "processed_count": processed,
                        "search_index_sync": sync,
                        "token_usage": result.get("token_usage") or {},
                    }
                )

            rebuild_summary = self._maybe_rebuild_vector_store(runtime_options)
            next_run_at = started_at + timedelta(minutes=max(1, int(pipeline.get("schedule_minutes") or 60)))
            summary = {
                "ok": True,
                "pipeline_id": pipeline_id,
                "pipeline_name": pipeline.get("name"),
                "run_id": run_id,
                "started_at": _dt_to_sql(started_at),
                "finished_at": _dt_to_sql(_utc_now()),
                "task_ids": task_ids,
                "tasks": task_summaries,
                "processed_count": total_processed,
                "upserted_profiles": total_profiles,
                "upserted_chunks": total_chunks,
                "token_usage": {"total_tokens": total_tokens},
                "vector_rebuild": rebuild_summary,
                "next_run_at": _dt_to_sql(next_run_at),
            }
            finish_collection_pipeline_run(run_id, status="completed", task_ids=task_ids, summary=summary)
            mark_collection_pipeline_finished(
                pipeline_id,
                status="completed",
                next_run_at=_dt_to_sql(next_run_at),
                last_task_id=last_task_id,
            )
            return summary
        except Exception as exc:
            next_run_at = started_at + timedelta(minutes=max(1, int(pipeline.get("schedule_minutes") or 60)))
            summary = {
                "ok": False,
                "pipeline_id": pipeline_id,
                "pipeline_name": pipeline.get("name"),
                "run_id": run_id,
                "task_ids": task_ids,
                "tasks": task_summaries,
                "processed_count": total_processed,
                "upserted_profiles": total_profiles,
                "upserted_chunks": total_chunks,
                "error": str(exc),
                "next_run_at": _dt_to_sql(next_run_at),
            }
            finish_collection_pipeline_run(run_id, status="failed", task_ids=task_ids, summary=summary, error=str(exc))
            mark_collection_pipeline_finished(
                pipeline_id,
                status="failed",
                next_run_at=_dt_to_sql(next_run_at),
                last_task_id=last_task_id,
                last_error=str(exc),
            )
            raise

    def _build_task_payload(
        self,
        pipeline: dict[str, Any],
        search_config: dict[str, Any],
        runtime_options: dict[str, Any],
    ) -> dict[str, Any]:
        merged_search_config = dict(search_config or {})
        for key, value in runtime_options.items():
            if key in {"rebuild_interval_hours", "run_full_rebuild_after_batch", "scheduler_poll_seconds"}:
                continue
            merged_search_config.setdefault(key, value)
        return {
            "job_id": pipeline["job_id"],
            "search_mode": pipeline.get("search_mode") or "recommend",
            "sort_by": pipeline.get("sort_by") or "active",
            "max_candidates": max(1, int(pipeline.get("max_candidates") or 50)),
            "max_pages": max(1, int(pipeline.get("max_pages") or 10)),
            "search_config": merged_search_config,
            "require_hr_confirmation": False,
        }

    def _maybe_rebuild_vector_store(self, runtime_options: dict[str, Any]) -> dict[str, Any]:
        if runtime_options.get("run_full_rebuild_after_batch"):
            summary = self.search_service.rebuild_vector_store()
            set_system_state(VECTOR_REBUILD_STATE_KEY, {"last_run_at": _dt_to_sql(_utc_now()), "summary": summary})
            return summary

        interval_hours = runtime_options.get("rebuild_interval_hours")
        if interval_hours in (None, "", 0, "0"):
            return {"ok": True, "skipped": True, "reason": "incremental_only"}
        try:
            interval_hours = float(interval_hours)
        except Exception:
            return {"ok": False, "skipped": True, "reason": "invalid_rebuild_interval"}
        if interval_hours <= 0:
            return {"ok": True, "skipped": True, "reason": "incremental_only"}

        state = get_system_state(VECTOR_REBUILD_STATE_KEY) or {}
        state_value = {}
        if state.get("value"):
            try:
                state_value = json.loads(state["value"])
            except Exception:
                state_value = {}
        last_run_at = _sql_to_dt(state_value.get("last_run_at"))
        now = _utc_now()
        if last_run_at is not None and (now - last_run_at) < timedelta(hours=interval_hours):
            return {
                "ok": True,
                "skipped": True,
                "reason": "interval_not_due",
                "last_run_at": state_value.get("last_run_at"),
            }
        summary = self.search_service.rebuild_vector_store()
        set_system_state(VECTOR_REBUILD_STATE_KEY, {"last_run_at": _dt_to_sql(now), "summary": summary})
        return summary


__all__ = ["CollectionPipelineService", "VECTOR_REBUILD_STATE_KEY"]
