from __future__ import annotations

import uuid
from typing import Any

from .db import connect, dumps, loads


BUILTIN_SCORING_KIND = "builtin_phase1"
CUSTOM_SCORING_KIND = "custom_phase2"
BUILTIN_ENGINE_TYPE = "builtin_formula"
CUSTOM_ENGINE_TYPE = "generic_resume_match"


def _normalize_scorecard_row(row) -> dict[str, Any]:
    item = dict(row)
    item["scorecard"] = loads(item.get("scorecard")) or {}
    item["supports_resume_import"] = bool(item.get("supports_resume_import"))
    item["editable"] = bool(item.get("editable"))
    item["system_managed"] = bool(item.get("system_managed"))
    item["active"] = bool(item.get("active"))
    item["kind"] = item.get("scorecard_kind")
    return item


def list_jd_scorecards(
    *,
    limit: int = 200,
    scorecard_kinds: list[str] | None = None,
    engine_types: list[str] | None = None,
    supports_resume_import: bool | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if active_only:
        clauses.append("active = 1")
    if scorecard_kinds:
        placeholders = ",".join("?" for _ in scorecard_kinds)
        clauses.append(f"scorecard_kind in ({placeholders})")
        params.extend(scorecard_kinds)
    if engine_types:
        placeholders = ",".join("?" for _ in engine_types)
        clauses.append(f"engine_type in ({placeholders})")
        params.extend(engine_types)
    if supports_resume_import is not None:
        clauses.append("supports_resume_import = ?")
        params.append(1 if supports_resume_import else 0)
    where_clause = f"where {' and '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            select *
            from jd_scorecards
            {where_clause}
            order by system_managed asc, updated_at desc, created_at desc
            limit ?
            """,
            (*params, max(1, limit)),
        ).fetchall()
    return [_normalize_scorecard_row(row) for row in rows]


def get_jd_scorecard(scorecard_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            select *
            from jd_scorecards
            where id = ?
            """,
            (scorecard_id,),
        ).fetchone()
    if not row:
        return None
    return _normalize_scorecard_row(row)


def upsert_jd_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    scorecard = payload.get("scorecard")
    if not isinstance(scorecard, dict):
        raise ValueError("scorecard 必须是对象")
    scorecard_id = str(payload.get("id") or uuid.uuid4())
    scorecard_kind = str(payload.get("scorecard_kind") or CUSTOM_SCORING_KIND).strip() or CUSTOM_SCORING_KIND
    engine_type = str(payload.get("engine_type") or "").strip() or (
        BUILTIN_ENGINE_TYPE if scorecard_kind == BUILTIN_SCORING_KIND else CUSTOM_ENGINE_TYPE
    )
    default_schema_version = "phase1_builtin_v1" if scorecard_kind == BUILTIN_SCORING_KIND else "phase2_scorecard_v1"
    schema_version = str(payload.get("schema_version") or scorecard.get("schema_version") or default_schema_version).strip()
    name = str(payload.get("name") or scorecard.get("name") or scorecard_id).strip()
    if not name:
        raise ValueError("name 不能为空")
    jd_text = str(payload.get("jd_text") or scorecard.get("jd_text") or "").strip()
    created_by = str(payload.get("created_by") or "hr_ui").strip() or "hr_ui"
    supports_resume_import_value = payload.get("supports_resume_import")
    if supports_resume_import_value is None:
        supports_resume_import = engine_type == CUSTOM_ENGINE_TYPE
    else:
        supports_resume_import = bool(supports_resume_import_value)
    editable = bool(payload.get("editable", True))
    system_managed = bool(payload.get("system_managed", False))
    active = bool(payload.get("active", True))
    with connect() as conn:
        conn.execute(
            """
            insert into jd_scorecards (
                id, name, jd_text, scorecard, scorecard_kind, engine_type, schema_version,
                supports_resume_import, editable, system_managed, active, created_by, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            on conflict(id) do update set
                name = excluded.name,
                jd_text = excluded.jd_text,
                scorecard = excluded.scorecard,
                scorecard_kind = excluded.scorecard_kind,
                engine_type = excluded.engine_type,
                schema_version = excluded.schema_version,
                supports_resume_import = excluded.supports_resume_import,
                editable = excluded.editable,
                system_managed = excluded.system_managed,
                active = excluded.active,
                created_by = excluded.created_by,
                updated_at = current_timestamp
            """,
            (
                scorecard_id,
                name,
                jd_text,
                dumps(scorecard),
                scorecard_kind,
                engine_type,
                schema_version,
                1 if supports_resume_import else 0,
                1 if editable else 0,
                1 if system_managed else 0,
                1 if active else 0,
                created_by,
            ),
        )
    return get_jd_scorecard(scorecard_id) or {}
