from __future__ import annotations

import re

from .jd_scorecard_repositories import BUILTIN_SCORING_KIND, get_jd_scorecard
from .models import CandidateDecision, ScoreResult
from .phase2_scorecards import score_phase2_resume
from .scorecards import SCORECARDS
from .scoring_targets import get_scoring_target


def _score_truthy(value: bool, weight: float) -> float:
    return weight if value else 0.0


def _score_level(level: float | int | None, weight: float) -> float:
    if level is None:
        return 0.0
    level = max(0.0, min(float(level), 1.0))
    return round(weight * level, 2)


def _coerce_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        chunks = re.split(r"[,\n;/|]+", value)
        return [chunk.strip() for chunk in chunks if chunk.strip()]
    return []


def _builtin_scorecard(job_id: str) -> dict:
    item = get_jd_scorecard(job_id)
    if item and item.get("scorecard_kind") == BUILTIN_SCORING_KIND and isinstance(item.get("scorecard"), dict):
        return item["scorecard"]
    return SCORECARDS[job_id]


def _scorecard_age_range(scorecard: dict) -> tuple[float | None, float | None]:
    filters = scorecard.get("filters") if isinstance(scorecard.get("filters"), dict) else {}
    age_min = _coerce_number(scorecard.get("age_min"))
    age_max = _coerce_number(scorecard.get("age_max"))
    if age_min is None:
        age_min = _coerce_number(filters.get("age_min"))
    if age_max is None:
        age_max = _coerce_number(filters.get("age_max"))
    age_range = scorecard.get("age_range") if isinstance(scorecard.get("age_range"), dict) else {}
    if age_min is None and isinstance(age_range, dict):
        age_min = _coerce_number(age_range.get("min"))
    if age_max is None and isinstance(age_range, dict):
        age_max = _coerce_number(age_range.get("max"))
    if age_min is not None and age_max is not None and age_min > age_max:
        age_min, age_max = age_max, age_min
    return age_min, age_max


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "-"
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


def _append_age_range_failures(scorecard: dict, fields: dict, hard_filter_fail_reasons: list[str]) -> None:
    age_min, age_max = _scorecard_age_range(scorecard)
    if age_min is None and age_max is None:
        return
    age = _coerce_number(fields.get("age"))
    if age is None:
        hard_filter_fail_reasons.append("年龄信息缺失")
        return
    if age_min is not None and age_max is not None:
        if not (age_min <= age <= age_max):
            hard_filter_fail_reasons.append(f"年龄不在 {_format_number(age_min)}-{_format_number(age_max)} 岁范围内")
        return
    if age_min is not None and age < age_min:
        hard_filter_fail_reasons.append(f"年龄低于 {_format_number(age_min)} 岁")
    if age_max is not None and age > age_max:
        hard_filter_fail_reasons.append(f"年龄高于 {_format_number(age_max)} 岁")


def _phase2_profile_from_fields(fields: dict) -> dict:
    raw_resume_text = str(
        fields.get("raw_summary")
        or fields.get("resume_summary")
        or fields.get("summary")
        or fields.get("page_text")
        or ""
    )
    return {
        "name": str(fields.get("name") or ""),
        "city": str(fields.get("city") or fields.get("location") or ""),
        "location": str(fields.get("location") or fields.get("city") or ""),
        "latest_title": str(fields.get("current_title") or fields.get("latest_title") or ""),
        "latest_company": str(fields.get("current_company") or fields.get("latest_company") or ""),
        "skills": _coerce_list(fields.get("skills") or fields.get("tools") or fields.get("project_keywords") or []),
        "industry_tags": _coerce_list(fields.get("industry_tags") or fields.get("project_keywords") or []),
        "years_experience": fields.get("years_experience"),
        "education_level": str(fields.get("education_level") or ""),
        "age": fields.get("age"),
        "raw_profile": {
            "raw_resume_text": raw_resume_text,
            "summary": raw_resume_text,
        },
    }


def _score_custom_target(scorecard: dict, fields: dict) -> ScoreResult:
    score_payload = score_phase2_resume(scorecard, _phase2_profile_from_fields(fields))
    dimension_scores = {
        str(key): float(value)
        for key, value in dict(score_payload.get("dimension_scores") or {}).items()
    }
    decision_value = str(score_payload.get("decision") or CandidateDecision.REJECT.value)
    try:
        decision = CandidateDecision(decision_value)
    except ValueError:
        decision = CandidateDecision.REJECT
    return ScoreResult(
        hard_filter_pass=bool(score_payload.get("hard_filter_pass")),
        hard_filter_fail_reasons=list(score_payload.get("hard_filter_fail_reasons") or []),
        dimension_scores=dimension_scores,
        total_score=float(score_payload.get("total_score") or 0.0),
        decision=decision,
        review_reasons=list(score_payload.get("review_reasons") or []),
    )


def _qa_experience_level(fields: dict) -> float:
    years = _coerce_number(fields.get("years_experience"))
    if years is None:
        months = _coerce_number(fields.get("total_work_months"))
        if months is not None:
            years = months / 12.0
    if years is None:
        return 0.0
    if years >= 8:
        return 1.0
    if years >= 3:
        return min(1.0, 0.45 + (years - 3.0) * (0.55 / 5.0))
    return max(0.0, min(years / 3.0 * 0.45, 0.45))


def score_candidate(job_id: str, fields: dict) -> ScoreResult:
    target = get_scoring_target(job_id)
    if target and target.get("kind") != BUILTIN_SCORING_KIND and isinstance(target.get("scorecard"), dict):
        return _score_custom_target(target["scorecard"], fields)

    scorecard = _builtin_scorecard(job_id)
    hard_filter_fail_reasons: list[str] = []

    for rule in scorecard["hard_filters"]:
        value = fields.get(rule["field"])
        kind = rule["kind"]
        if kind == "min_number":
            numeric = _coerce_number(value)
            if numeric is None or numeric < float(rule["value"]):
                hard_filter_fail_reasons.append(rule["message"])
        elif kind == "max_number":
            numeric = _coerce_number(value)
            if numeric is None or numeric > float(rule["value"]):
                hard_filter_fail_reasons.append(rule["message"])
        elif kind == "max_number_if_present":
            numeric = _coerce_number(value)
            if numeric is not None and numeric > float(rule["value"]):
                hard_filter_fail_reasons.append(rule["message"])
        elif kind == "truthy":
            if job_id == "qa_test_engineer_v1" and rule["field"] == "testing_evidence":
                qa_proxy_evidence = bool(value) or bool(fields.get("qa_role_history_evidence")) or bool(fields.get("has_test_engineer_experience"))
                if not qa_proxy_evidence:
                    hard_filter_fail_reasons.append(rule["message"])
            elif not value:
                hard_filter_fail_reasons.append(rule["message"])
        elif kind == "in_set" and value not in rule["value"]:
            hard_filter_fail_reasons.append(rule["message"])

    _append_age_range_failures(scorecard, fields, hard_filter_fail_reasons)

    hard_filter_pass = not hard_filter_fail_reasons
    weights = scorecard["weights"]

    if job_id == "qa_test_engineer_v1":
        tools = _coerce_list(fields.get("tools", []))
        tools_level = min(len(set(tools)) / 6.0, 1.0)
        if tools_level == 0.0 and (
            fields.get("testing_evidence")
            or fields.get("qa_role_history_evidence")
            or fields.get("has_test_engineer_experience")
        ):
            tools_level = 0.28
        if fields.get("has_api_testing_experience") or fields.get("has_app_testing_experience") or fields.get("has_web_testing_experience"):
            tools_level = max(tools_level, 0.4)

        frontend_backend_signal = bool(fields.get("frontend_backend_test")) or (
            bool(fields.get("has_app_testing_experience"))
            and (bool(fields.get("has_web_testing_experience")) or bool(fields.get("has_api_testing_experience")))
        )
        dimension_scores = {
            "core_test_depth": _score_level(fields.get("core_test_depth_level"), weights["core_test_depth"]),
            "tools_coverage": round(tools_level * weights["tools_coverage"], 2),
            "frontend_backend": _score_truthy(frontend_backend_signal, weights["frontend_backend"]),
            "defect_closure": _score_level(fields.get("defect_closure_level"), weights["defect_closure"]),
            "industry_fit": round(
                min(len(fields.get("industry_tags", [])), 1) * weights["industry_fit"], 2
            ),
            "analysis_logic": _score_level(fields.get("analysis_logic_level"), weights["analysis_logic"]),
            "experience_maturity": _score_level(_qa_experience_level(fields), weights["experience_maturity"]),
        }
    elif job_id == "py_dev_engineer_v1":
        dimension_scores = {
            "python_engineering": _score_level(fields.get("python_engineering_level"), weights["python_engineering"]),
            "linux_shell": _score_level(fields.get("linux_shell_level"), weights["linux_shell"]),
            "java_support": _score_level(fields.get("java_support_level"), weights["java_support"]),
            "middleware_stack": round(
                min(len(fields.get("middleware", [])) / 3.0, 1.0) * weights["middleware_stack"], 2
            ),
            "security_fit": _score_level(fields.get("security_fit_level"), weights["security_fit"]),
            "analysis_design": _score_level(fields.get("analysis_design_level"), weights["analysis_design"]),
        }
    elif job_id == "caption_aesthetic_qc_v1":
        dimension_scores = {
            "aesthetic_writing": _score_level(fields.get("aesthetic_writing_level"), weights["aesthetic_writing"]),
            "film_art_theory": _score_level(fields.get("film_art_theory_level"), weights["film_art_theory"]),
            "ai_annotation_qc": _score_level(fields.get("ai_annotation_qc_level"), weights["ai_annotation_qc"]),
            "visual_domain_coverage": round(
                min(len(fields.get("visual_domain_tags", [])) / 3.0, 1.0) * weights["visual_domain_coverage"], 2
            ),
            "watching_volume": _score_level(fields.get("watching_volume_level"), weights["watching_volume"]),
            "english": _score_level(fields.get("english_level"), weights["english"]),
            "portfolio": _score_level(fields.get("portfolio_level"), weights["portfolio"]),
            "gender_bonus": weights["gender_bonus"] if fields.get("gender") == "female" else 0.0,
        }
    elif job_id == "caption_ai_trainer_zhengzhou_v1":
        dimension_scores = {
            "writing_naturalness": _score_level(fields.get("writing_naturalness_level"), weights["writing_naturalness"]),
            "reading_rule_follow": _score_level(fields.get("reading_rule_follow_level"), weights["reading_rule_follow"]),
            "visual_analysis": _score_level(fields.get("visual_analysis_level"), weights["visual_analysis"]),
            "film_language": _score_level(fields.get("film_language_level"), weights["film_language"]),
            "output_stability": _score_level(fields.get("output_stability_level"), weights["output_stability"]),
            "ai_annotation_experience": _score_level(
                fields.get("ai_annotation_experience_level"),
                weights["ai_annotation_experience"],
            ),
            "long_term_stability": _score_level(fields.get("long_term_stability_level"), weights["long_term_stability"]),
        }
    else:
        raise KeyError(f"Unknown job_id: {job_id}")

    total_score = round(sum(dimension_scores.values()), 2)
    review_reasons: list[str] = []

    if not hard_filter_pass:
        decision = CandidateDecision.REJECT
    else:
        thresholds = scorecard["thresholds"]
        if total_score >= thresholds["recommend_min"]:
            decision = CandidateDecision.RECOMMEND
        elif total_score >= thresholds["review_min"]:
            decision = CandidateDecision.REVIEW
        else:
            decision = CandidateDecision.REJECT

    if job_id == "caption_aesthetic_qc_v1" and dimension_scores["gender_bonus"] > 0:
        review_reasons.append("Gender bonus applied. Require HR review before external action.")
        if decision == CandidateDecision.RECOMMEND:
            decision = CandidateDecision.REVIEW

    if decision == CandidateDecision.RECOMMEND and total_score < 85:
        review_reasons.append("Recommend-level score below strong-pass band. Manual spot-check advised.")

    return ScoreResult(
        hard_filter_pass=hard_filter_pass,
        hard_filter_fail_reasons=hard_filter_fail_reasons,
        dimension_scores=dimension_scores,
        total_score=total_score,
        decision=decision,
        review_reasons=review_reasons,
    )
