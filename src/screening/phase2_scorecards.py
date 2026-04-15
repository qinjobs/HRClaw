from __future__ import annotations

import re
from typing import Any

from .search_service import EDUCATION_RANKS, KNOWN_INDUSTRIES, KNOWN_LOCATIONS, KNOWN_SKILLS, KNOWN_TITLES, SKILL_SYNONYMS


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


def _education_rank(value: str | None) -> int:
    if not value:
        return 0
    lowered = value.lower()
    best = 0
    for label, rank in EDUCATION_RANKS.items():
        if label in lowered:
            best = max(best, rank)
    return best


def _extract_years_min(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*年(?:以上|及以上|经验)?", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_education_min(text: str) -> str | None:
    lowered = text.lower()
    for label in EDUCATION_RANKS:
        if label in lowered:
            return label
    return None


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None


def _extract_age_range(text: str) -> tuple[float | None, float | None]:
    raw = str(text or "")
    compact = re.sub(r"\s+", "", raw)
    patterns: list[tuple[str, str]] = [
        (r"年龄[:：]?([1-6]?\d)(?:岁|周岁)?[-~—至到]([1-6]?\d)(?:岁|周岁)?", "range"),
        (r"([1-6]?\d)(?:岁|周岁)?[-~—至到]([1-6]?\d)(?:岁|周岁)?", "range"),
        (r"年龄[:：]?([1-6]?\d)(?:岁|周岁)?(?:及以上|以上|起|或以上)", "min"),
        (r"([1-6]?\d)(?:岁|周岁)?(?:及以上|以上|起|或以上)", "min"),
        (r"年龄[:：]?([1-6]?\d)(?:岁|周岁)?(?:及以下|以下|以内)", "max"),
        (r"([1-6]?\d)(?:岁|周岁)?(?:及以下|以下|以内)", "max"),
    ]
    for pattern, kind in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if not match:
            continue
        if kind == "range":
            age_min = _coerce_number(match.group(1))
            age_max = _coerce_number(match.group(2))
            if age_min is not None and age_max is not None and age_min > age_max:
                age_min, age_max = age_max, age_min
            return age_min, age_max
        if kind == "min":
            return _coerce_number(match.group(1)), None
        if kind == "max":
            return None, _coerce_number(match.group(1))
    return None, None


def _extract_role_title(text: str) -> str:
    lines = [line.strip(" -*\t") for line in str(text or "").splitlines() if line.strip()]
    for line in lines[:6]:
        if 2 <= len(line) <= 40:
            return line
    return "JD评分卡"


def _extract_marker_terms(text: str, markers: tuple[str, ...], candidate_terms: list[str]) -> list[str]:
    found: list[str] = []
    for marker in markers:
        start = text.find(marker)
        if start < 0:
            continue
        window = text[start : start + 120]
        lowered = window.lower()
        for term in candidate_terms:
            if term.lower() in lowered:
                found.append(term)
    return _unique_texts(found)


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _unique_texts(re.split(r"[\n,;；、]+", value))
    if isinstance(value, (list, tuple, set)):
        return _unique_texts(list(value))
    return _unique_texts([value])


_UNSAFE_EXCLUDE_TERMS = {
    "男",
    "女",
    "男性",
    "女性",
    "male",
    "female",
}


def _sanitize_exclude_terms(value: Any) -> list[str]:
    terms = _normalize_text_list(value)
    return [term for term in terms if str(term).strip().lower() not in _UNSAFE_EXCLUDE_TERMS]


def generate_scorecard_from_jd(jd_text: str, *, name: str | None = None) -> dict[str, Any]:
    raw_text = str(jd_text or "").strip()
    if not raw_text:
        raise ValueError("jd_text 不能为空")
    role_title = str(name or "").strip() or _extract_role_title(raw_text)
    location = next((city for city in KNOWN_LOCATIONS if city in raw_text), None)
    years_min = _extract_years_min(raw_text)
    age_min, age_max = _extract_age_range(raw_text)
    education_min = _extract_education_min(raw_text)
    titles = _unique_texts([term for term in KNOWN_TITLES if term.lower() in raw_text.lower()] + [role_title])
    industries = _unique_texts([term for term in KNOWN_INDUSTRIES if term.lower() in raw_text.lower()])
    must_have = _unique_texts(
        _extract_marker_terms(raw_text, ("任职要求", "岗位要求", "职位要求", "必须", "需要", "熟悉", "掌握", "精通"), KNOWN_SKILLS)
        + [term for term in KNOWN_SKILLS if term.lower() in raw_text.lower()]
    )
    nice_to_have = _unique_texts(
        _extract_marker_terms(raw_text, ("优先", "加分", "最好", "bonus"), KNOWN_SKILLS + KNOWN_INDUSTRIES)
    )
    exclude = _unique_texts(
        _extract_marker_terms(raw_text, ("不考虑", "排除", "不要", "exclude"), KNOWN_SKILLS + KNOWN_INDUSTRIES + KNOWN_TITLES)
    )
    scorecard_name = role_title if role_title else "JD评分卡"
    return normalize_phase2_scorecard(
        {
            "schema_version": "phase2_scorecard_v1",
            "name": scorecard_name,
            "jd_text": raw_text,
            "role_title": role_title,
            "filters": {
                "location": location,
                "years_min": years_min,
                "age_min": age_min,
                "age_max": age_max,
                "education_min": education_min,
            },
            "must_have": must_have,
            "nice_to_have": nice_to_have,
            "exclude": exclude,
            "titles": titles,
            "industry": industries,
            "weights": {
                "must_have": 42,
                "nice_to_have": 12,
                "title_match": 12,
                "industry_match": 8,
                "experience": 14,
                "education": 7,
                "location": 5,
            },
            "thresholds": {
                "recommend_min": 75,
                "review_min": 55,
            },
            "hard_filters": {
                "enforce_years": years_min is not None,
                "enforce_age": age_min is not None or age_max is not None,
                "enforce_education": education_min is not None,
                "enforce_location": False,
                "strict_exclude": bool(exclude),
                "must_have_ratio_min": 0.5 if must_have else 0.0,
            },
            "summary": "根据 JD 自动生成的初始评分卡，可由 HR 继续调整规则和权重。",
        }
    )


def normalize_phase2_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or payload.get("role_title") or "JD评分卡").strip()
    if not name:
        raise ValueError("评分卡名称不能为空")
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    weights = payload.get("weights") if isinstance(payload.get("weights"), dict) else {}
    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    hard_filters = payload.get("hard_filters") if isinstance(payload.get("hard_filters"), dict) else {}
    recommend_min = float(thresholds.get("recommend_min") or 75)
    review_min = float(thresholds.get("review_min") or 55)
    if review_min > recommend_min:
        raise ValueError("review_min 不能大于 recommend_min")
    age_min = _coerce_number(filters.get("age_min"))
    if age_min is None:
        age_min = _coerce_number(payload.get("age_min"))
    age_max = _coerce_number(filters.get("age_max"))
    if age_max is None:
        age_max = _coerce_number(payload.get("age_max"))
    if age_min is not None and age_max is not None and age_min > age_max:
        age_min, age_max = age_max, age_min
    normalized_exclude = _sanitize_exclude_terms(payload.get("exclude"))
    normalized = {
        "schema_version": "phase2_scorecard_v1",
        "name": name,
        "jd_text": str(payload.get("jd_text") or "").strip(),
        "role_title": str(payload.get("role_title") or name).strip(),
        "summary": str(payload.get("summary") or "").strip(),
        "filters": {
            "location": str(filters.get("location") or "").strip() or None,
            "years_min": float(filters["years_min"]) if filters.get("years_min") not in (None, "", False) else None,
            "age_min": age_min,
            "age_max": age_max,
            "education_min": str(filters.get("education_min") or "").strip() or None,
        },
        "must_have": _normalize_text_list(payload.get("must_have")),
        "nice_to_have": _normalize_text_list(payload.get("nice_to_have")),
        "exclude": normalized_exclude,
        "titles": _normalize_text_list(payload.get("titles")),
        "industry": _normalize_text_list(payload.get("industry")),
        "weights": {
            "must_have": max(0.0, float(weights.get("must_have") or 42)),
            "nice_to_have": max(0.0, float(weights.get("nice_to_have") or 12)),
            "title_match": max(0.0, float(weights.get("title_match") or 12)),
            "industry_match": max(0.0, float(weights.get("industry_match") or 8)),
            "experience": max(0.0, float(weights.get("experience") or 14)),
            "education": max(0.0, float(weights.get("education") or 7)),
            "location": max(0.0, float(weights.get("location") or 5)),
        },
        "thresholds": {
            "recommend_min": recommend_min,
            "review_min": review_min,
        },
        "hard_filters": {
            "enforce_years": bool(hard_filters.get("enforce_years", False)),
            "enforce_age": bool(hard_filters.get("enforce_age", False)),
            "enforce_education": bool(hard_filters.get("enforce_education", False)),
            "enforce_location": bool(hard_filters.get("enforce_location", False)),
            "strict_exclude": bool(hard_filters.get("strict_exclude", False)) and bool(normalized_exclude),
            "must_have_ratio_min": max(0.0, min(float(hard_filters.get("must_have_ratio_min") or 0.0), 1.0)),
        },
    }
    return normalized


def _contains_term(haystack: str, term: str) -> bool:
    if not term:
        return False
    lowered = haystack.lower()
    for candidate in _term_variants(term):
        if candidate.lower() in lowered:
            return True
    return False


def _term_variants(term: str) -> list[str]:
    raw = str(term or "").strip()
    if not raw:
        return []
    variants = [raw]
    without_brackets = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
    if without_brackets and without_brackets != raw:
        variants.append(without_brackets)
    stripped_suffix = re.sub(
        r"(?:相关)?(?:实战经验|项目经验|开发经验|工作经验|经验|背景|方向|工程师|岗位|职位)$",
        "",
        without_brackets or raw,
        flags=re.IGNORECASE,
    ).strip(" -_/|")
    if len(stripped_suffix) >= 2 and stripped_suffix not in variants:
        variants.append(stripped_suffix)
    return _unique_texts(SKILL_SYNONYMS.get(raw.lower(), []) + variants)


def _fraction(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return max(0.0, min(float(numerator) / float(denominator), 1.0))


def score_phase2_resume(scorecard: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    scorecard = normalize_phase2_scorecard(scorecard)
    filters = scorecard["filters"]
    weights = scorecard["weights"]
    hard_filters = scorecard["hard_filters"]
    thresholds = scorecard["thresholds"]
    combined_text = "\n".join(
        [
            str(profile.get("name") or ""),
            str(profile.get("city") or profile.get("location") or ""),
            str(profile.get("latest_title") or ""),
            str(profile.get("latest_company") or ""),
            " ".join(profile.get("skills") or []),
            " ".join(profile.get("industry_tags") or []),
            str((profile.get("raw_profile") or {}).get("raw_resume_text") or ""),
            str((profile.get("raw_profile") or {}).get("summary") or ""),
        ]
    ).lower()

    must_have = list(scorecard.get("must_have") or [])
    nice_to_have = list(scorecard.get("nice_to_have") or [])
    exclude = list(scorecard.get("exclude") or [])
    titles = list(scorecard.get("titles") or [])
    industries = list(scorecard.get("industry") or [])

    matched_must = [term for term in must_have if _contains_term(combined_text, term)]
    matched_bonus = [term for term in nice_to_have if _contains_term(combined_text, term)]
    matched_titles = [term for term in titles if _contains_term(combined_text, term)]
    matched_industry = [term for term in industries if _contains_term(combined_text, term)]
    blocked_terms = [term for term in exclude if _contains_term(combined_text, term)]

    years_value = profile.get("years_experience")
    try:
        years = float(years_value) if years_value is not None else None
    except (TypeError, ValueError):
        years = None
    age_value = profile.get("age")
    try:
        age = float(age_value) if age_value is not None else None
    except (TypeError, ValueError):
        age = None
    education = str(profile.get("education_level") or "")
    location = str(profile.get("city") or profile.get("location") or "")

    must_have_ratio = _fraction(len(matched_must), len(must_have))
    nice_to_have_ratio = _fraction(len(matched_bonus), len(nice_to_have))
    title_ratio = _fraction(len(matched_titles), len(titles))
    industry_ratio = _fraction(len(matched_industry), len(industries))

    soft_review_reasons: list[str] = []

    if filters.get("years_min") is None:
        experience_level = 1.0
    elif years is None:
        experience_level = 0.35
        soft_review_reasons.append("工作年限信息缺失，建议人工复核。")
    elif years >= float(filters["years_min"]):
        gap = years - float(filters["years_min"])
        experience_level = min(1.0, 1.0 if gap <= 0 else 0.9 + min(gap, 2.0) * 0.05)
    else:
        experience_level = max(0.0, min(years / max(float(filters["years_min"]), 1.0), 1.0) * 0.7)

    expected_education = filters.get("education_min")
    if not expected_education:
        education_level = 1.0
    else:
        expected_rank = _education_rank(expected_education)
        actual_rank = _education_rank(education)
        if not education.strip():
            education_level = 0.35
            soft_review_reasons.append("学历信息缺失，建议人工复核。")
        elif actual_rank >= expected_rank:
            education_level = 1.0
        elif actual_rank + 1 == expected_rank:
            education_level = 0.45
        else:
            education_level = 0.0

    expected_location = str(filters.get("location") or "").strip()
    if not expected_location:
        location_level = 1.0
    elif not location.strip():
        location_level = 0.35
        soft_review_reasons.append("地点信息缺失，建议人工复核。")
    else:
        location_level = 1.0 if expected_location.lower() in location.lower() else 0.0

    hard_filter_fail_reasons: list[str] = []
    if hard_filters.get("enforce_years") and filters.get("years_min") is not None:
        if years is not None and years < float(filters["years_min"]):
            hard_filter_fail_reasons.append(f"工作年限低于 {filters['years_min']} 年")
    expected_age_min = filters.get("age_min")
    expected_age_max = filters.get("age_max")
    if hard_filters.get("enforce_age") and (expected_age_min is not None or expected_age_max is not None):
        if age is None:
            soft_review_reasons.append("年龄信息缺失，建议人工复核。")
        elif expected_age_min is not None and expected_age_max is not None and not (
            float(expected_age_min) <= age <= float(expected_age_max)
        ):
            hard_filter_fail_reasons.append(f"年龄不在 {expected_age_min}-{expected_age_max} 岁范围内")
        elif expected_age_min is not None and age < float(expected_age_min):
            hard_filter_fail_reasons.append(f"年龄低于 {expected_age_min} 岁")
        elif expected_age_max is not None and age > float(expected_age_max):
            hard_filter_fail_reasons.append(f"年龄高于 {expected_age_max} 岁")
    if hard_filters.get("enforce_education") and expected_education:
        if education.strip() and _education_rank(education) < _education_rank(expected_education):
            hard_filter_fail_reasons.append(f"学历低于 {expected_education}")
    if hard_filters.get("enforce_location") and expected_location:
        if location.strip() and expected_location.lower() not in location.lower():
            hard_filter_fail_reasons.append(f"地点不符合：需要 {expected_location}")
    must_have_ratio_min = float(hard_filters.get("must_have_ratio_min") or 0.0)
    if must_have and must_have_ratio < must_have_ratio_min:
        if not matched_must:
            hard_filter_fail_reasons.append(
                f"核心技能命中率不足 {int(must_have_ratio_min * 100)}%"
            )
        else:
            soft_review_reasons.append(
                f"核心技能命中率低于 {int(must_have_ratio_min * 100)}%，建议人工复核。"
            )
    if hard_filters.get("strict_exclude") and blocked_terms:
        hard_filter_fail_reasons.append(f"命中排除项：{' / '.join(blocked_terms[:3])}")

    total_weight = max(sum(float(value) for value in weights.values()), 1.0)

    def weighted_points(weight: float, level: float) -> float:
        return round(max(0.0, float(weight)) * max(0.0, min(level, 1.0)) * 100.0 / total_weight, 2)

    dimension_scores = {
        "must_have_match": weighted_points(weights["must_have"], must_have_ratio),
        "nice_to_have_match": weighted_points(weights["nice_to_have"], nice_to_have_ratio),
        "title_match": weighted_points(weights["title_match"], title_ratio if titles else 1.0),
        "industry_match": weighted_points(weights["industry_match"], industry_ratio if industries else 1.0),
        "experience_fit": weighted_points(weights["experience"], experience_level),
        "education_fit": weighted_points(weights["education"], education_level),
        "location_fit": weighted_points(weights["location"], location_level),
    }
    total_score = round(sum(dimension_scores.values()), 2)
    hard_filter_pass = not hard_filter_fail_reasons
    if not hard_filter_pass:
        decision = "reject"
    elif total_score >= float(thresholds["recommend_min"]):
        decision = "recommend"
    elif total_score >= float(thresholds["review_min"]):
        decision = "review"
    else:
        decision = "reject"

    review_reasons: list[str] = list(dict.fromkeys(soft_review_reasons))
    if decision == "review":
        if must_have and must_have_ratio < 0.8:
            review_reasons.append("核心技能只命中部分，建议人工复核。")
        if expected_location and location_level < 1.0:
            review_reasons.append("地点信息不完整或存在偏差。")
        if expected_education and education_level < 1.0:
            review_reasons.append("学历信息存在不确定性。")
    return {
        "hard_filter_pass": hard_filter_pass,
        "hard_filter_fail_reasons": hard_filter_fail_reasons,
        "dimension_scores": dimension_scores,
        "total_score": total_score,
        "decision": decision,
        "review_reasons": review_reasons,
        "matched_terms": _unique_texts(matched_must + matched_bonus + matched_titles + matched_industry),
        "missing_terms": [term for term in must_have if term not in matched_must],
        "blocked_terms": blocked_terms,
    }
