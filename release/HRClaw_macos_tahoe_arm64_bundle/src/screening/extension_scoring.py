from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .candidate_heuristics import (
    build_fallback_normalized_fields,
    extract_age,
    extract_education_level,
    extract_salary,
    extract_years_experience,
    has_qa_testing_evidence,
    infer_candidate_item,
)
from .gpt_extractor import GPTFieldExtractor
from .phase2_imports import build_resume_profile_from_text
from .phase2_scorecards import score_phase2_resume
from .repositories import insert_extension_score_event
from .scoring import score_candidate
from .scoring_targets import BUILTIN_SCORING_KIND, get_scoring_target


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


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


def _build_resume_text(page_text: str, page_title: str, candidate_hint: str) -> str:
    chunks = [page_text]
    if page_title and page_title not in page_text:
        chunks.append(f"页面标题：{page_title}")
    if candidate_hint and candidate_hint not in page_text:
        chunks.append(f"候选人提示：{candidate_hint}")
    return "\n\n".join(chunk for chunk in chunks if chunk)


def _normalize_candidate_name(value: Any) -> str:
    return _clean_text(value).replace("♂", "").replace("♀", "")


def _looks_like_person_name(value: Any) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fa5·*]{2,8}", _normalize_candidate_name(value)))


def _merge_with_fallback(
    job_id: str,
    extracted: dict[str, Any],
    fallback_item: dict[str, Any],
    *,
    candidate_name_hint: str = "",
    enable_builtin_normalized_fields: bool = True,
) -> dict[str, Any]:
    merged = dict(extracted or {})
    hinted_name = _normalize_candidate_name(candidate_name_hint)
    extracted_name = _normalize_candidate_name(merged.get("name"))
    if _looks_like_person_name(hinted_name):
        merged["name"] = hinted_name
    elif _looks_like_person_name(extracted_name):
        merged["name"] = extracted_name
    merged.setdefault("skills", fallback_item.get("skills", []))
    merged.setdefault("industry_tags", fallback_item.get("industry_tags", []))
    merged.setdefault("project_keywords", fallback_item.get("project_keywords", []))
    merged.setdefault("resume_summary", fallback_item.get("resume_summary"))
    merged.setdefault("evidence_map", {})

    fallback_seed = dict(fallback_item)
    fallback_seed.update(
        {
            "skills": merged.get("skills", []),
            "industry_tags": merged.get("industry_tags", []),
            "project_keywords": merged.get("project_keywords", []),
            "resume_summary": merged.get("resume_summary"),
            "location": merged.get("location") or fallback_item.get("location"),
        }
    )
    if enable_builtin_normalized_fields:
        merged["normalized_fields"] = merged.get("normalized_fields") or build_fallback_normalized_fields(job_id, fallback_seed)
    else:
        merged["normalized_fields"] = merged.get("normalized_fields") if isinstance(merged.get("normalized_fields"), dict) else {}
    if enable_builtin_normalized_fields and job_id == "qa_test_engineer_v1":
        normalized_fields = dict(merged.get("normalized_fields") or {})
        normalized_fields["testing_evidence"] = has_qa_testing_evidence(str(merged.get("resume_summary") or ""))
        merged["normalized_fields"] = normalized_fields
    return merged


def _merge_text_list(*groups: Any) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for value in group:
            text = _clean_text(value)
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            items.append(text)
    return items


def _build_phase2_extension_profile(
    *,
    job_id: str,
    merged_fields: dict[str, Any],
    fallback_item: dict[str, Any],
    extraction_text: str,
    external_id: str | None,
    page_url: str,
    page_title: str,
    candidate_hint: str,
    source: str,
) -> dict[str, Any]:
    normalized_external_id = _clean_text(external_id) or f"extension:{abs(hash(extraction_text))}"
    profile = build_resume_profile_from_text(
        external_id=normalized_external_id,
        source_candidate_id=normalized_external_id,
        filename=f"{job_id}.txt",
        text=extraction_text,
        source="boss_extension",
        raw_resume_entry={
            "source": "boss_extension",
            "job_id": job_id,
            "page_url": page_url,
            "page_title": page_title,
            "candidate_hint": candidate_hint,
            "extension_source": source,
        },
    )
    if merged_fields.get("name"):
        profile["name"] = merged_fields.get("name")
    if merged_fields.get("location"):
        profile["city"] = merged_fields.get("location")
    if merged_fields.get("years_experience") is not None:
        profile["years_experience"] = merged_fields.get("years_experience")
    if merged_fields.get("education_level"):
        profile["education_level"] = merged_fields.get("education_level")
    profile["latest_title"] = (
        merged_fields.get("current_title")
        or merged_fields.get("latest_title")
        or profile.get("latest_title")
        or page_title
    )
    if merged_fields.get("current_company"):
        profile["latest_company"] = merged_fields.get("current_company")
    profile["skills"] = _merge_text_list(profile.get("skills"), merged_fields.get("skills"), fallback_item.get("skills"))
    profile["industry_tags"] = _merge_text_list(
        profile.get("industry_tags"),
        merged_fields.get("industry_tags"),
        fallback_item.get("industry_tags"),
        fallback_item.get("project_keywords"),
    )
    raw_profile = dict(profile.get("raw_profile") or {})
    raw_profile["summary"] = str(merged_fields.get("resume_summary") or raw_profile.get("summary") or extraction_text[:1200])
    raw_profile["experience"] = extraction_text
    raw_profile["skills"] = profile.get("skills") or []
    raw_profile["education"] = profile.get("education_level")
    raw_profile["raw_resume_text"] = extraction_text
    profile["raw_profile"] = raw_profile
    return profile


def _normalize_model_usage(extractor: Any) -> dict[str, Any]:
    usage = getattr(extractor, "last_usage", None)
    if not isinstance(usage, dict):
        usage = {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or 0) or (prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "provider": usage.get("provider") or getattr(extractor, "provider", None),
        "model": usage.get("model") or getattr(extractor, "model", None),
    }


class ExtensionScoreService:
    def __init__(self, *, extractor: Any | None = None) -> None:
        self.extractor = extractor or GPTFieldExtractor()

    def score_candidate_page(
        self,
        *,
        job_id: str,
        page_url: str,
        page_title: str = "",
        page_text: str,
        candidate_hint: str = "",
        source: str = "boss_extension_v1",
    ) -> dict[str, Any]:
        target = get_scoring_target(job_id)
        if not target:
            raise KeyError(f"Unknown job_id: {job_id}")
        is_builtin_target = target["kind"] == BUILTIN_SCORING_KIND

        normalized_page_text = _clean_text(page_text)
        if not normalized_page_text:
            raise ValueError("page_text 不能为空")

        normalized_page_url = _clean_text(page_url)
        normalized_page_title = _clean_text(page_title)
        normalized_candidate_hint = _clean_text(candidate_hint)
        extraction_text = _build_resume_text(
            normalized_page_text,
            normalized_page_title,
            normalized_candidate_hint,
        )
        external_id = _extract_external_id(normalized_page_url)

        fallback_item = infer_candidate_item(job_id, extraction_text)
        fallback_item.update(
            {
                "age": extract_age(extraction_text),
                "education_level": extract_education_level(extraction_text),
                "years_experience": extract_years_experience(extraction_text),
                "expected_salary": extract_salary(extraction_text),
                "resume_summary": fallback_item.get("resume_summary") or normalized_page_text[:1000],
            }
        )

        extracted_fields: dict[str, Any] = {}
        extraction_error: str | None = None
        fallback_used = False
        try:
            extracted_fields = self.extractor.extract_candidate(job_id, extraction_text)
            if not extracted_fields:
                fallback_used = True
        except Exception as exc:
            extraction_error = str(exc)
            fallback_used = True

        merged_fields = _merge_with_fallback(
            job_id,
            extracted_fields,
            fallback_item,
            candidate_name_hint=normalized_candidate_hint,
            enable_builtin_normalized_fields=is_builtin_target,
        )
        evidence_map = dict(merged_fields.get("evidence_map") or {})
        evidence_map.update(
            {
                "extension_source": source,
                "page_url": normalized_page_url,
                "candidate_hint": normalized_candidate_hint,
            }
        )
        if extraction_error:
            evidence_map["extension_extraction_error"] = extraction_error
        merged_fields["evidence_map"] = evidence_map

        if is_builtin_target:
            score_input = dict(merged_fields.get("normalized_fields") or {})
            score_input.update(
                {
                    "age": merged_fields.get("age") or fallback_item.get("age"),
                    "years_experience": merged_fields.get("years_experience") or fallback_item.get("years_experience"),
                    "education_level": merged_fields.get("education_level") or fallback_item.get("education_level"),
                }
            )
            raw_score = score_candidate(job_id, score_input)
            score_payload = {
                "total_score": raw_score.total_score,
                "decision": raw_score.decision.value,
                "hard_filter_pass": raw_score.hard_filter_pass,
                "dimension_scores": raw_score.dimension_scores,
                "hard_filter_fail_reasons": raw_score.hard_filter_fail_reasons,
                "review_reasons": raw_score.review_reasons,
                "matched_terms": [],
                "missing_terms": [],
                "blocked_terms": [],
            }
        else:
            profile = _build_phase2_extension_profile(
                job_id=job_id,
                merged_fields=merged_fields,
                fallback_item=fallback_item,
                extraction_text=extraction_text,
                external_id=external_id,
                page_url=normalized_page_url,
                page_title=normalized_page_title,
                candidate_hint=normalized_candidate_hint,
                source=source,
            )
            score_payload = score_phase2_resume(target["scorecard"], profile)
        model_usage = _normalize_model_usage(self.extractor)
        scored_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        audit_event_id = insert_extension_score_event(
            job_id=job_id,
            page_url=normalized_page_url,
            external_id=external_id,
            source=source,
            page_title=normalized_page_title,
            candidate_hint=normalized_candidate_hint,
            decision=score_payload["decision"],
            total_score=score_payload["total_score"],
            fallback_used=fallback_used,
            model_usage=model_usage,
        )

        return {
            "audit_event_id": audit_event_id,
            "job_id": job_id,
            "scorecard_name": target["name"],
            "scorecard_kind": target["kind"],
            "external_id": external_id,
            "score": score_payload["total_score"],
            "decision": score_payload["decision"],
            "hard_filter_pass": score_payload["hard_filter_pass"],
            "dimension_scores": score_payload["dimension_scores"],
            "hard_filter_fail_reasons": score_payload["hard_filter_fail_reasons"],
            "review_reasons": score_payload["review_reasons"],
            "matched_terms": score_payload.get("matched_terms") or [],
            "missing_terms": score_payload.get("missing_terms") or [],
            "blocked_terms": score_payload.get("blocked_terms") or [],
            "extracted_fields": merged_fields,
            "fallback_used": fallback_used,
            "model_usage": model_usage,
            "scored_at": scored_at,
        }
