from __future__ import annotations

from typing import Any

from .jd_scorecard_repositories import (
    BUILTIN_SCORING_KIND,
    CUSTOM_SCORING_KIND,
    get_jd_scorecard,
    list_jd_scorecards,
)


def _target_from_row(item: dict[str, Any]) -> dict[str, Any]:
    scorecard = item.get("scorecard") if isinstance(item.get("scorecard"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or scorecard.get("name") or item.get("id") or "").strip(),
        "kind": str(item.get("scorecard_kind") or item.get("kind") or CUSTOM_SCORING_KIND),
        "schema_version": str(item.get("schema_version") or scorecard.get("schema_version") or "phase2_scorecard_v1"),
        "engine_type": str(item.get("engine_type") or ""),
        "supports_resume_import": bool(item.get("supports_resume_import")),
        "editable": bool(item.get("editable", True)),
        "system_managed": bool(item.get("system_managed")),
        "scorecard": scorecard,
        "jd_text": item.get("jd_text"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def is_builtin_scoring_target(job_id: str) -> bool:
    item = get_jd_scorecard(str(job_id or "").strip())
    return bool(item and item.get("scorecard_kind") == BUILTIN_SCORING_KIND)


def get_scoring_target(job_id: str) -> dict[str, Any] | None:
    normalized = str(job_id or "").strip()
    if not normalized:
        return None
    item = get_jd_scorecard(normalized)
    if not item:
        return None
    return _target_from_row(item)


def list_scoring_targets(*, custom_limit: int = 200) -> list[dict[str, Any]]:
    return [_target_from_row(item) for item in list_jd_scorecards(limit=max(1, custom_limit))]
