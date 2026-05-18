from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .candidate_heuristics import extract_years_experience
from .db import connect, dumps, loads
from .jd_scorecard_repositories import (
    CUSTOM_ENGINE_TYPE,
    CUSTOM_SCORING_KIND,
    get_jd_scorecard,
    list_jd_scorecards,
    upsert_jd_scorecard,
)


_RESUME_NAME_HEADINGS = {
    "基本信息",
    "个人信息",
    "工作经历",
    "项目经历",
    "教育经历",
    "教育背景",
    "自我评价",
    "技术背景",
    "求职意向",
}

_RESUME_NAME_STOPWORDS = (
    "工程师",
    "方向",
    "应届生",
    "基本信息",
    "工作经历",
    "项目经历",
    "教育经历",
    "求职意向",
    "个人简历",
    "简历",
    "毕业",
    "院校",
    "学校",
)


def _unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(text)
    return items


def _is_plausible_chinese_name(text: str) -> bool:
    candidate = re.sub(r"\s+", "", str(text or ""))
    if not re.fullmatch(r"[\u4e00-\u9fa5·]{2,8}", candidate):
        return False
    if candidate in _RESUME_NAME_HEADINGS:
        return False
    if any(stopword in candidate for stopword in _RESUME_NAME_STOPWORDS):
        return False
    return True


def _is_valid_display_name(name: Any) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    if _is_plausible_chinese_name(text):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", text):
        return True
    return False


def _extract_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    tokens = [token for token in re.split(r"[_\-\s]+", stem) if token]
    for token in reversed(tokens):
        candidate = re.sub(r"[^\u4e00-\u9fa5·]", "", token)
        if _is_plausible_chinese_name(candidate):
            return candidate
    for candidate in re.findall(r"[\u4e00-\u9fa5·]{2,8}", stem):
        if _is_plausible_chinese_name(candidate):
            return candidate
    return ""


def _infer_name_from_text(text: str, filename: str) -> str | None:
    explicit = re.search(r"姓\s*名\s*[:：]?\s*([\u4e00-\u9fa5· \t]{2,16})", text)
    if explicit:
        candidate = re.sub(r"\s+", "", explicit.group(1)).strip()
        if _is_plausible_chinese_name(candidate):
            return candidate
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines[:12]:
        age_prefixed = re.match(r"^([\u4e00-\u9fa5·]{2,8})\s*(?:\d{1,2}\s*岁|[（(])", line)
        if age_prefixed:
            candidate = age_prefixed.group(1).strip()
            if _is_plausible_chinese_name(candidate):
                return candidate
        candidate = re.sub(r"\s+", "", line.replace("个人简历", "").replace("简历", "").strip())
        if _is_plausible_chinese_name(candidate):
            return candidate
    fallback = _extract_name_from_filename(filename)
    return fallback or None


def _extract_years_from_filename(filename: str, resume_text: str) -> float | None:
    compact_name = re.sub(r"\s+", "", Path(filename).stem)
    if re.search(r"(应届|校招|毕业生)", compact_name) or re.search(r"(应届|校招|毕业生)", resume_text):
        return 0.0
    for match in re.finditer(r"(\d{1,2})\s*年(?:经验|工作经验|开发经验|测试经验)?", compact_name):
        try:
            years = float(match.group(1))
        except ValueError:
            continue
        if 0 <= years <= 20:
            return years
    return None


def _enrich_import_result(item: dict[str, Any]) -> dict[str, Any]:
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    profile = detail.get("profile") if isinstance(detail.get("profile"), dict) else {}
    raw_profile = profile.get("raw_profile") if isinstance(profile.get("raw_profile"), dict) else {}
    resume_text = str(raw_profile.get("raw_resume_text") or raw_profile.get("summary") or "").strip()
    filename = str(item.get("filename") or "")

    if not _is_valid_display_name(item.get("extracted_name")):
        inferred_name = _infer_name_from_text(resume_text, filename)
        if inferred_name:
            item["extracted_name"] = inferred_name

    if item.get("years_experience") in (None, ""):
        years = extract_years_experience(resume_text)
        if years is None:
            years = _extract_years_from_filename(filename, resume_text)
        if years is not None:
            item["years_experience"] = years

    if not item.get("matched_terms"):
        fallback_terms = _unique_texts(
            list(profile.get("skills") or []) + list(profile.get("industry_tags") or [])
        )[:8]
        if fallback_terms:
            item["matched_terms"] = fallback_terms

    return item


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
    return _enrich_import_result(item)


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
