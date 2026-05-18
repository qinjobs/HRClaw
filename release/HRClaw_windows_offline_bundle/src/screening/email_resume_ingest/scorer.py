from __future__ import annotations

from typing import Any

from ..candidate_heuristics import build_fallback_normalized_fields, has_qa_testing_evidence, infer_candidate_item
from ..phase2_scorecards import score_phase2_resume
from ..scoring import score_candidate
from ..scoring_targets import BUILTIN_SCORING_KIND, get_scoring_target
from .models import EmailIngestDecision


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


class EmailResumeScorer:
    def score_profile(self, *, scorecard_id: str, profile: dict[str, Any]) -> EmailIngestDecision:
        target = get_scoring_target(str(scorecard_id or "").strip())
        if not target:
            raise KeyError(f"Unknown scorecard_id: {scorecard_id}")
        if target["kind"] == BUILTIN_SCORING_KIND:
            return self._score_builtin(job_id=str(target["id"]), profile=profile)
        return self._score_custom(scorecard=target["scorecard"], profile=profile)

    def _score_custom(self, *, scorecard: dict[str, Any], profile: dict[str, Any]) -> EmailIngestDecision:
        payload = score_phase2_resume(scorecard, profile)
        return EmailIngestDecision(
            decision=str(payload.get("decision") or "reject"),
            total_score=float(payload.get("total_score") or 0.0),
            hard_filter_pass=bool(payload.get("hard_filter_pass")),
            hard_filter_fail_reasons=list(payload.get("hard_filter_fail_reasons") or []),
            dimension_scores={str(k): float(v) for k, v in dict(payload.get("dimension_scores") or {}).items()},
            review_reasons=list(payload.get("review_reasons") or []),
            matched_terms=list(payload.get("matched_terms") or []),
            missing_terms=list(payload.get("missing_terms") or []),
            blocked_terms=list(payload.get("blocked_terms") or []),
        )

    def _score_builtin(self, *, job_id: str, profile: dict[str, Any]) -> EmailIngestDecision:
        raw_profile = profile.get("raw_profile") if isinstance(profile.get("raw_profile"), dict) else {}
        raw_resume_text = str(raw_profile.get("raw_resume_text") or raw_profile.get("summary") or "")
        fallback_item = infer_candidate_item(job_id, raw_resume_text)
        fallback_item.update(
            {
                "name": profile.get("name"),
                "location": profile.get("city"),
                "education_level": profile.get("education_level"),
                "years_experience": profile.get("years_experience"),
                "skills": profile.get("skills") or [],
                "industry_tags": profile.get("industry_tags") or [],
                "resume_summary": raw_resume_text[:1200],
            }
        )
        normalized_fields = build_fallback_normalized_fields(job_id, fallback_item)
        if job_id == "qa_test_engineer_v1":
            normalized_fields["testing_evidence"] = has_qa_testing_evidence(raw_resume_text)

        fields = dict(normalized_fields)
        fields.update(
            {
                "name": profile.get("name"),
                "location": profile.get("city"),
                "city": profile.get("city"),
                "education_level": profile.get("education_level"),
                "years_experience": profile.get("years_experience"),
                "current_company": profile.get("latest_company"),
                "latest_company": profile.get("latest_company"),
                "current_title": profile.get("latest_title"),
                "latest_title": profile.get("latest_title"),
                "skills": list(profile.get("skills") or []),
                "industry_tags": list(profile.get("industry_tags") or []),
                "raw_summary": raw_resume_text,
                "resume_summary": raw_resume_text,
                "summary": raw_resume_text[:1200],
            }
        )
        raw_score = score_candidate(job_id, fields)
        matched_terms = _unique_texts(list(profile.get("skills") or []) + list(profile.get("industry_tags") or []))[:8]
        return EmailIngestDecision(
            decision=raw_score.decision.value,
            total_score=float(raw_score.total_score),
            hard_filter_pass=bool(raw_score.hard_filter_pass),
            hard_filter_fail_reasons=list(raw_score.hard_filter_fail_reasons or []),
            dimension_scores={str(k): float(v) for k, v in dict(raw_score.dimension_scores or {}).items()},
            review_reasons=list(raw_score.review_reasons or []),
            matched_terms=matched_terms,
            missing_terms=[],
            blocked_terms=[],
        )

