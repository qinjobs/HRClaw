from __future__ import annotations

import uuid
from typing import Any

from .db import connect, dumps, loads
from .jd_scorecard_repositories import (
    CUSTOM_ENGINE_TYPE,
    CUSTOM_SCORING_KIND,
    get_jd_scorecard,
    list_jd_scorecards,
    upsert_jd_scorecard,
)


def _normalize_scorecard_row(row) -> dict[str, Any]:
    item = dict(row)
    item["scorecard"] = loads(item.get("scorecard")) or {}
    return item


def list_custom_scorecards(*, limit: int = 100) -> list[dict[str, Any]]:
    return list_jd_scorecards(limit=limit, scorecard_kinds=[CUSTOM_SCORING_KIND])


def get_custom_scorecard(scorecard_id: str) -> dict[str, Any] | None:
    item = get_jd_scorecard(scorecard_id)
    if not item or item.get("scorecard_kind") != CUSTOM_SCORING_KIND:
        return None
    return item


def upsert_custom_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    scorecard = payload.get("scorecard")
    if not isinstance(scorecard, dict):
        raise ValueError("scorecard 必须是对象")
    return upsert_jd_scorecard(
        {
            "id": str(payload.get("id") or uuid.uuid4()),
            "name": str(payload.get("name") or scorecard.get("name") or "").strip() or scorecard.get("name"),
            "jd_text": str(payload.get("jd_text") or scorecard.get("jd_text") or "").strip(),
            "scorecard": scorecard,
            "scorecard_kind": CUSTOM_SCORING_KIND,
            "engine_type": CUSTOM_ENGINE_TYPE,
            "schema_version": str(scorecard.get("schema_version") or "phase2_scorecard_v1"),
            "supports_resume_import": True,
            "editable": True,
            "system_managed": False,
            "active": True,
            "created_by": str(payload.get("created_by") or "hr_ui").strip() or "hr_ui",
        }
    )


def create_resume_import_batch(
    *,
    scorecard_id: str,
    scorecard_name: str,
    batch_name: str,
    created_by: str,
    total_files: int,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into resume_import_batches (
                id, scorecard_id, scorecard_name, batch_name, created_by, total_files, summary
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                scorecard_id,
                scorecard_name,
                batch_name,
                created_by,
                max(0, int(total_files)),
                dumps(summary or {}),
            ),
        )
    return get_resume_import_batch(batch_id) or {}


def finalize_resume_import_batch(
    batch_id: str,
    *,
    processed_files: int,
    recommend_count: int,
    review_count: int,
    reject_count: int,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            update resume_import_batches
            set processed_files = ?,
                recommend_count = ?,
                review_count = ?,
                reject_count = ?,
                summary = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (
                max(0, int(processed_files)),
                max(0, int(recommend_count)),
                max(0, int(review_count)),
                max(0, int(reject_count)),
                dumps(summary or {}),
                batch_id,
            ),
        )
    return get_resume_import_batch(batch_id) or {}


def _normalize_import_batch_row(row) -> dict[str, Any]:
    item = dict(row)
    item["summary"] = loads(item.get("summary")) or {}
    return item


def get_resume_import_batch(batch_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "select * from resume_import_batches where id = ?",
            (batch_id,),
        ).fetchone()
    if not row:
        return None
    return _normalize_import_batch_row(row)


def list_resume_import_batches(*, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from resume_import_batches
            order by created_at desc
            limit ?
            """,
            (max(1, limit),),
        ).fetchall()
    return [_normalize_import_batch_row(row) for row in rows]


def insert_resume_import_result(
    batch_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result_id = str(payload.get("id") or uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into resume_import_results (
                id, batch_id, scorecard_id, resume_profile_id, filename, file_path, parse_status,
                extracted_name, years_experience, education_level, location,
                total_score, decision, hard_filter_pass, hard_filter_fail_reasons,
                matched_terms, missing_terms, dimension_scores, summary, detail
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                batch_id,
                str(payload.get("scorecard_id") or ""),
                payload.get("resume_profile_id"),
                str(payload.get("filename") or ""),
                str(payload.get("file_path") or ""),
                str(payload.get("parse_status") or "completed"),
                payload.get("extracted_name"),
                payload.get("years_experience"),
                payload.get("education_level"),
                payload.get("location"),
                payload.get("total_score"),
                payload.get("decision"),
                1 if payload.get("hard_filter_pass") else 0,
                dumps(payload.get("hard_filter_fail_reasons") or []),
                dumps(payload.get("matched_terms") or []),
                dumps(payload.get("missing_terms") or []),
                dumps(payload.get("dimension_scores") or {}),
                str(payload.get("summary") or ""),
                dumps(payload.get("detail") or {}),
            ),
        )
    return get_resume_import_result(result_id) or {}


def _normalize_import_result_row(row) -> dict[str, Any]:
    item = dict(row)
    item["hard_filter_pass"] = bool(item.get("hard_filter_pass"))
    item["hard_filter_fail_reasons"] = loads(item.get("hard_filter_fail_reasons")) or []
    item["matched_terms"] = loads(item.get("matched_terms")) or []
    item["missing_terms"] = loads(item.get("missing_terms")) or []
    item["dimension_scores"] = loads(item.get("dimension_scores")) or {}
    item["detail"] = loads(item.get("detail")) or {}
    return item


def get_resume_import_result(result_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "select * from resume_import_results where id = ?",
            (result_id,),
        ).fetchone()
    if not row:
        return None
    return _normalize_import_result_row(row)


def list_resume_import_results(batch_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from resume_import_results
            where batch_id = ?
            order by
                case decision
                    when 'recommend' then 3
                    when 'review' then 2
                    when 'reject' then 1
                    else 0
                end desc,
                total_score desc,
                created_at asc
            """,
            (batch_id,),
        ).fetchall()
    return [_normalize_import_result_row(row) for row in rows]
