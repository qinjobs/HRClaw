from __future__ import annotations

import hashlib
import re
from typing import Any

from .candidate_heuristics import (
    build_fallback_normalized_fields,
    extract_age,
    extract_education_level,
    extract_salary,
    extract_years_experience,
    infer_candidate_item,
)
from .extension_scoring import ExtensionScoreService
from .repositories import (
    add_candidate_timeline_event,
    advance_candidate_stage_if_unlocked,
    find_extension_candidate_binding_by_identity,
    get_candidate_pipeline_state,
    get_extension_candidate_binding,
    get_extension_candidate_binding_by_candidate_id,
    get_extension_candidate_binding_by_external_id,
    get_or_create_extension_task,
    insert_candidate,
    insert_score,
    insert_snapshot,
    update_candidate,
    upsert_candidate_pipeline_state,
    upsert_extension_candidate_binding,
)
from .scoring_targets import BUILTIN_SCORING_KIND, get_scoring_target

_INVALID_INGEST_URL_PARTS = (
    "/web/chat/recommend",
    "/bzl-office/pdf-viewer-b",
)
_INVALID_NAME_TOKENS = {
    "职位管理",
    "速览",
    "个人资料",
    "推荐牛人",
    "BOSS直聘",
    "PDF预览",
}
_IDENTITY_STOP_LINES = {
    "经历概览",
    "其他相似经历的牛人",
    "其他名企大厂经历牛人",
}
_IDENTITY_NOISE_LINES = {
    "打招呼",
    "继续沟通",
    "收藏",
    "举报",
    "转发牛人",
    "不合适",
    "推荐牛人",
    "最近关注",
}


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _normalize_candidate_name(value: Any) -> str:
    return _clean_text(value).replace("♂", "").replace("♀", "")


def _looks_like_person_name(value: Any) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fa5·*]{2,8}", _normalize_candidate_name(value)))


def _extract_candidate_name_from_text(page_text: str) -> str:
    normalized = _clean_text(page_text)
    if not normalized:
        return ""
    explicit_match = re.search(r"姓\s*名[:：]?\s*([\u4e00-\u9fa5·*]{2,8})", normalized)
    if explicit_match and _looks_like_person_name(explicit_match.group(1)):
        return explicit_match.group(1)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    profile_line_pattern = re.compile(r"(岁|年|本科|硕士|博士|大专|专科|到岗|离职|在职)")
    for index in range(min(len(lines), 18)):
        current = _normalize_candidate_name(lines[index])
        next_line = _normalize_candidate_name(lines[index + 1]) if index + 1 < len(lines) else ""
        if _looks_like_person_name(current) and (
            profile_line_pattern.search(next_line) or "活跃" in current or "在线" in current
        ):
            return current
    for line in lines[:8]:
        candidate = _normalize_candidate_name(line)
        if _looks_like_person_name(candidate):
            return candidate
    return ""


def _looks_like_ingestable_detail(*, page_url: str, page_text: str, candidate_name: str) -> bool:
    normalized_url = str(page_url or "").strip().lower()
    normalized_text = _clean_text(page_text)
    normalized_name = _normalize_candidate_name(candidate_name)
    if not normalized_text or len(normalized_text) < 20:
        return False
    if any(part in normalized_url for part in _INVALID_INGEST_URL_PARTS):
        return False
    if normalized_text.startswith("JD 速览") or normalized_text.startswith("职位管理"):
        return False
    if normalized_text.startswith("!function(){var e=document"):
        return False
    if normalized_name in _INVALID_NAME_TOKENS:
        return False
    inferred_name = normalized_name if _looks_like_person_name(normalized_name) else _extract_candidate_name_from_text(normalized_text)
    if not _looks_like_person_name(inferred_name):
        return False
    if not any(keyword in normalized_text for keyword in ("工作经历", "项目经历", "教育经历", "期望职位", "在线简历")):
        if not re.search(r"(岁|年)\s*[^\n]{0,12}(本科|硕士|博士|大专|专科)", normalized_text):
            return False
    return True


def _extract_external_id(page_url: str) -> str | None:
    if not page_url:
        return None
    detail_match = re.search(r"/([A-Za-z0-9_-]{6,})\.html", page_url)
    if detail_match:
        return detail_match.group(1)
    query_match = re.search(r"(?:[?&])(geekId|gid|uid|id)=([A-Za-z0-9_-]{4,})", page_url, flags=re.IGNORECASE)
    if query_match:
        return query_match.group(2)
    return None


def _hash_text(value: str) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()


def _normalize_page_text_for_identity(page_text: str) -> str:
    normalized = _clean_text(page_text)
    if not normalized:
        return ""
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line in _IDENTITY_STOP_LINES:
            break
        if line in _IDENTITY_NOISE_LINES:
            continue
        if line.startswith("!function(){var e=document"):
            continue
        lines.append(line)
        if len(lines) >= 32 or sum(len(item) for item in lines) >= 1600:
            break
    return "\n".join(lines)


def _build_source_candidate_key(
    *,
    job_id: str,
    page_url: str,
    page_title: str,
    page_text: str,
    candidate_name: str,
    external_id: str | None,
) -> str:
    if external_id:
        return str(external_id).strip()
    identity_text = _normalize_page_text_for_identity(page_text) or _clean_text(page_text)
    payload = "\n".join(
        [
            str(job_id or "").strip(),
            str(page_url or "").split("#", 1)[0].strip(),
            _normalize_candidate_name(candidate_name),
            _clean_text(page_title),
            _hash_text(identity_text),
        ]
    )
    return _hash_text(payload)


def _build_candidate_seed(
    *,
    job_id: str,
    page_text: str,
    page_title: str,
    candidate_name: str,
    external_id: str | None,
    enable_builtin_normalized_fields: bool,
) -> dict[str, Any]:
    fallback_item = infer_candidate_item(job_id, page_text)
    fallback_item.update(
        {
            "age": extract_age(page_text),
            "education_level": extract_education_level(page_text),
            "years_experience": extract_years_experience(page_text),
            "expected_salary": extract_salary(page_text),
            "resume_summary": fallback_item.get("resume_summary") or page_text[:1000],
        }
    )
    normalized_fields = build_fallback_normalized_fields(job_id, fallback_item) if enable_builtin_normalized_fields else {}
    normalized_name = _normalize_candidate_name(candidate_name)
    if not _looks_like_person_name(normalized_name):
        normalized_name = _extract_candidate_name_from_text(page_text)
    return {
        "source": "boss_extension",
        "external_id": external_id,
        "name": normalized_name if _looks_like_person_name(normalized_name) else None,
        "age": fallback_item.get("age"),
        "education_level": fallback_item.get("education_level"),
        "major": None,
        "years_experience": fallback_item.get("years_experience"),
        "current_company": None,
        "current_title": page_title or None,
        "expected_salary": fallback_item.get("expected_salary"),
        "location": None,
        "last_active_time": None,
        "raw_summary": fallback_item.get("resume_summary") or page_text[:1000],
        "normalized_fields": normalized_fields,
    }


class ExtensionCandidateIngestService:
    def __init__(self, *, scorer: ExtensionScoreService | None = None) -> None:
        self.scorer = scorer or ExtensionScoreService()

    def upsert_candidate_page(
        self,
        *,
        job_id: str,
        page_url: str,
        page_title: str = "",
        page_text: str,
        candidate_name: str = "",
        source: str = "boss_extension_v1",
        source_candidate_key: str | None = None,
        external_id: str | None = None,
        page_type: str = "boss_resume_detail",
        observed_at: str | None = None,
        context_key: str | None = None,
        quick_fit_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = get_scoring_target(job_id)
        if not target:
            raise KeyError(f"Unknown job_id: {job_id}")
        enable_builtin_normalized_fields = target["kind"] == BUILTIN_SCORING_KIND
        normalized_page_text = _clean_text(page_text)
        if not normalized_page_text:
            raise ValueError("page_text 不能为空")

        normalized_page_url = _clean_text(page_url)
        normalized_page_title = _clean_text(page_title)
        normalized_candidate_name = _normalize_candidate_name(candidate_name)
        if not _looks_like_person_name(normalized_candidate_name):
            normalized_candidate_name = _extract_candidate_name_from_text(normalized_page_text)
        if not _looks_like_ingestable_detail(
            page_url=normalized_page_url,
            page_text=normalized_page_text,
            candidate_name=normalized_candidate_name,
        ):
            raise ValueError("当前页面不是可入库的候选人详情页")
        normalized_external_id = _clean_text(external_id) or _extract_external_id(normalized_page_url)
        normalized_source_key = _clean_text(source_candidate_key) or _build_source_candidate_key(
            job_id=job_id,
            page_url=normalized_page_url,
            page_title=normalized_page_title,
            page_text=normalized_page_text,
            candidate_name=normalized_candidate_name,
            external_id=normalized_external_id,
        )
        text_hash = _hash_text(normalized_page_text)
        task = get_or_create_extension_task(job_id, source="boss_extension")

        binding = None
        if normalized_external_id:
            binding = get_extension_candidate_binding_by_external_id(
                job_id=job_id,
                source=source,
                external_id=normalized_external_id,
            )
        if not binding:
            binding = get_extension_candidate_binding(
                job_id=job_id,
                source=source,
                source_candidate_key=normalized_source_key,
            )
        if not binding:
            binding = find_extension_candidate_binding_by_identity(
                job_id=job_id,
                source=source,
                candidate_name=normalized_candidate_name,
                raw_summary=normalized_page_text,
            )
        elif binding.get("source_candidate_key"):
            normalized_source_key = str(binding["source_candidate_key"])
        if binding and binding.get("source_candidate_key"):
            normalized_source_key = str(binding["source_candidate_key"])

        candidate_seed = _build_candidate_seed(
            job_id=job_id,
            page_text=normalized_page_text,
            page_title=normalized_page_title,
            candidate_name=normalized_candidate_name,
            external_id=normalized_external_id,
            enable_builtin_normalized_fields=enable_builtin_normalized_fields,
        )
        evidence_map = {
            "source": source,
            "job_id": job_id,
            "page_url": normalized_page_url,
            "page_title": normalized_page_title,
            "candidate_name": normalized_candidate_name,
            "source_candidate_key": normalized_source_key,
            "external_id": normalized_external_id,
            "context_key": _clean_text(context_key),
            "observed_at": _clean_text(observed_at),
            "quick_fit_payload": quick_fit_payload or {},
            "ingest_mode": "extension_auto_upsert",
        }

        created_new = False
        if binding:
            candidate_id = str(binding["candidate_id"])
            update_candidate(candidate_id, candidate_seed)
        else:
            candidate_id = insert_candidate(task["id"], candidate_seed)
            created_new = True

        snapshot_id = insert_snapshot(
            candidate_id,
            page_type,
            "",
            normalized_page_text,
            evidence_map,
        )
        binding = upsert_extension_candidate_binding(
            candidate_id=candidate_id,
            job_id=job_id,
            task_id=task["id"],
            source=source,
            source_candidate_key=normalized_source_key,
            external_id=normalized_external_id,
            page_url=normalized_page_url,
            latest_text_hash=text_hash,
        )
        state = get_candidate_pipeline_state(candidate_id)
        if created_new or not state.get("created_at"):
            state = upsert_candidate_pipeline_state(candidate_id, current_stage="new", manual_stage_locked=False)
        event_type = "extension_ingested" if created_new else "extension_snapshot_updated"
        add_candidate_timeline_event(
            candidate_id,
            event_type,
            source,
            {
                "job_id": job_id,
                "task_id": task["id"],
                "page_url": normalized_page_url,
                "external_id": normalized_external_id,
                "source_candidate_key": normalized_source_key,
                "context_key": _clean_text(context_key),
                "snapshot_id": snapshot_id,
                "created_new": created_new,
            },
        )
        return {
            "candidate_id": candidate_id,
            "task_id": task["id"],
            "created_new": created_new,
            "pipeline_state": state,
            "latest_snapshot_id": snapshot_id,
            "manual_stage_locked": bool(state.get("manual_stage_locked")),
            "binding": binding,
        }

    def score_candidate(
        self,
        *,
        candidate_id: str,
        job_id: str,
        page_url: str,
        page_title: str = "",
        page_text: str,
        candidate_hint: str = "",
        source: str = "boss_extension_v1",
    ) -> dict[str, Any]:
        result = self.scorer.score_candidate_page(
            job_id=job_id,
            page_url=page_url,
            page_title=page_title,
            page_text=page_text,
            candidate_hint=candidate_hint,
            source=source,
        )
        insert_score(
            candidate_id,
            job_id,
            {
                "hard_filter_pass": result["hard_filter_pass"],
                "hard_filter_fail_reasons": result["hard_filter_fail_reasons"],
                "dimension_scores": result["dimension_scores"],
                "total_score": result["score"],
                "decision": result["decision"],
                "review_reasons": result["review_reasons"],
            },
        )
        existing_binding = get_extension_candidate_binding_by_candidate_id(candidate_id)
        binding_key = str((existing_binding or {}).get("source_candidate_key") or _build_source_candidate_key(
            job_id=job_id,
            page_url=page_url,
            page_title=page_title,
            page_text=page_text,
            candidate_name=candidate_hint,
            external_id=result.get("external_id"),
        ))
        binding = upsert_extension_candidate_binding(
            candidate_id=candidate_id,
            job_id=job_id,
            task_id=str((existing_binding or {}).get("task_id") or get_or_create_extension_task(job_id, source="boss_extension")["id"]),
            source=source,
            source_candidate_key=binding_key,
            external_id=result.get("external_id"),
            page_url=page_url,
            latest_text_hash=_hash_text(_clean_text(page_text)),
            scored=True,
        )
        before_state = get_candidate_pipeline_state(candidate_id)
        updated_state = advance_candidate_stage_if_unlocked(
            candidate_id,
            current_stage="scored",
            final_decision=result.get("decision"),
            operator=source,
        )
        state_transition = {
            "from": before_state.get("current_stage") or "new",
            "to": updated_state.get("current_stage") or "new",
            "skipped": bool(before_state.get("manual_stage_locked")) or (updated_state.get("current_stage") != "scored"),
        }
        add_candidate_timeline_event(
            candidate_id,
            "extension_scored",
            source,
            {
                "job_id": job_id,
                "score": result["score"],
                "decision": result["decision"],
                "fallback_used": bool(result["fallback_used"]),
                "audit_event_id": result.get("audit_event_id"),
            },
        )
        return {
            **result,
            "candidate_id": candidate_id,
            "pipeline_state": updated_state,
            "manual_stage_locked": bool(updated_state.get("manual_stage_locked")),
            "binding": binding,
            "state_transition": state_transition,
        }
