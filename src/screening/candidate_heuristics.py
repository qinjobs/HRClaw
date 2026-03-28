from __future__ import annotations

import re
from datetime import date
from typing import Any


QA_TOOLS = {
    "linux": "Linux",
    "shell": "Shell",
    "adb": "adb",
    "charles": "Charles",
    "fiddler": "Fiddler",
    "postman": "Postman",
    "jmeter": "JMeter",
    "metersphere": "MeterSphere",
    "pytest": "PyTest",
    "selenium": "Selenium",
    "appium": "Appium",
    "mysql": "MySQL",
    "postgres": "Postgres",
    "postgresql": "Postgres",
    "oracle": "Oracle",
    "sqlserver": "SQLServer",
    "sql server": "SQLServer",
    "数据库": "Database",
    "api": "API Testing",
    "接口测试": "API Testing",
    "jira": "Jira",
    "tapd": "TAPD",
    "ones": "ONES",
    "yapi": "YApi",
    "navicat": "Navicat",
    "swagger": "Swagger",
    "kubectl": "Kubernetes",
    "docker": "Docker",
    "grafana": "Grafana",
    "prometheus": "Prometheus",
    "testin": "Testin",
    "finalshell": "FinalShell",
    "canoe": "Canoe",
    "xmind": "XMind",
}

QA_PROCESS_VERBS = (
    "测试",
    "编写",
    "设计",
    "执行",
    "跟踪",
    "分析",
    "复现",
    "验证",
    "回归",
    "review",
    "execute",
    "track",
    "analy",
    "reproduc",
    "verify",
    "debug",
    "testing",
    "test",
)

QA_PROCESS_ARTIFACTS = (
    "用例",
    "test case",
    "case",
    "测试计划",
    "计划",
    "缺陷",
    "bug",
    "缺陷单",
    "报告",
    "回归报告",
    "测试报告",
    "测试经验",
    "接口测试",
    "功能测试",
    "自动化测试",
    "jira",
    "禅道",
)

QA_STRONG_COMBOS = (
    ("缺陷", "跟踪"),
    ("用例", "执行"),
    ("回归", "报告"),
    ("测试用例", "执行"),
)

QA_ROLE_SIGNALS = (
    "测试工程师",
    "软件测试",
    "测试开发",
    "qa",
    "quality assurance",
    "自动化测试",
    "功能测试",
)

QA_HISTORY_SECTIONS = (
    "经历概览",
    "工作经历",
    "项目经验",
    "项目描述",
    "项目职责",
)

PY_SKILLS = {
    "python": "Python",
    "java": "Java",
    "linux": "Linux",
    "shell": "Shell",
    "kafka": "kafka",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    "安全": "Security",
    "security": "Security",
}

CAP_VISUAL = {
    "摄影": "摄影",
    "光影": "光影",
    "服化道": "服化道",
    "电影": "电影",
    "构图": "构图",
    "caption": "caption",
    "标注": "标注",
}

CAPTION_TRAINER_TAGS = {
    "影视": "影视",
    "视频": "视频",
    "视听": "视听",
    "文案": "文案",
    "写作": "写作",
    "描述": "描述",
    "景别": "景别",
    "运镜": "运镜",
    "光线": "光线",
    "色彩": "色彩",
    "构图": "构图",
    "镜头": "镜头",
    "标注": "标注",
    "训练": "训练",
}

INDUSTRY_TAGS = {
    "在线教育": "在线教育",
    "教培": "在线教育",
    "k12": "在线教育",
    "鸿蒙": "鸿蒙",
    "harmony": "鸿蒙",
    "安全": "安全",
    "security": "安全",
    "视频": "视频",
    "图像": "图像",
    "ai": "AI",
}


CN_NUMBER_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_cn_number(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        try:
            return float(token)
        except ValueError:
            return None
    if token == "十":
        return 10.0
    if "十" in token:
        left, right = token.split("十", 1)
        tens = CN_NUMBER_MAP.get(left, 1 if left == "" else -1)
        if tens < 0:
            return None
        ones = 0
        if right:
            if right not in CN_NUMBER_MAP:
                return None
            ones = CN_NUMBER_MAP[right]
        return float(tens * 10 + ones)
    if token in CN_NUMBER_MAP:
        return float(CN_NUMBER_MAP[token])
    return None


def extract_years_experience(text: str) -> float | None:
    candidates: list[float] = []
    raw = str(text or "")

    # Prefer explicit experience fields first.
    explicit_patterns = (
        r"(?:工作经验|工作年限|测试经验|软件测试经验|开发或测试经验)\s*[:：]?\s*([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年",
        r"([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年(?:工作)?经验",
        r"([零一二三四五六七八九十两\d]+(?:\.\d+)?)\s*年以上",
    )
    for pattern in explicit_patterns:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
            token = match.group(1)
            value = _parse_cn_number(token)
            if value is not None and 0 <= value <= 40:
                candidates.append(value)

    # OCR often merges list numbering with year text, e.g. "1.3年功能测试经验" -> "3年".
    for match in re.finditer(r"(?:^|\n)\s*\d+\.(\d{1,2})\s*年(?:[^\n]{0,12}测试经验)?", raw):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if 0 <= value <= 40:
            candidates.append(value)

    if not candidates:
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:年(?:工作)?经验|年经验|年以上|年)", raw, flags=re.IGNORECASE):
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if 0 <= value <= 40:
                candidates.append(value)

    if not candidates:
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)(?:\s+of\s+experience)?", raw, flags=re.IGNORECASE):
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if 0 <= value <= 40:
                candidates.append(value)

    if not candidates:
        return None

    qualified = [value for value in candidates if value >= 2.0]
    if qualified:
        return max(qualified)
    return max(candidates)


def extract_age(text: str) -> int | None:
    match = re.search(r"([1-6]\d)\s*岁", text)
    return int(match.group(1)) if match else None


def extract_education_level(text: str) -> str | None:
    for token in ("博士", "硕士", "本科", "大专", "专科", "高中"):
        if token in text:
            return token
    lowered = text.lower()
    for token in ("phd", "master", "bachelor", "college"):
        if token in lowered:
            return token
    return None


def extract_salary(text: str) -> str | None:
    match = re.search(r"(\d{1,2}\s*[kK](?:\s*-\s*\d{1,2}\s*[kK])?)", text)
    return match.group(1).replace(" ", "") if match else None


def _extract_salary_ranges_k(text: str) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for match in re.finditer(r"(\d{1,2})(?:\s*[-~至到]\s*(\d{1,2}))?\s*[kK]", text):
        low = float(match.group(1))
        high = float(match.group(2) or match.group(1))
        if high < low:
            low, high = high, low
        ranges.append((low, high))
    return ranges


def _salary_in_4k_6k(text: str) -> bool:
    for low, high in _extract_salary_ranges_k(text):
        # Treat overlap with 4-6K band as acceptable.
        if high >= 4.0 and low <= 6.0:
            return True
    return False


def _extract_graduation_year(text: str) -> int | None:
    edu_tokens = ("大学", "学院", "本科", "大专", "专科", "硕士", "博士", "毕业", "学历")
    candidates: list[int] = []

    for match in re.finditer(r"(19\d{2}|20\d{2})\s*(?:[./年]\s*\d{1,2})?\s*[-~至到]\s*(19\d{2}|20\d{2})", text):
        year = int(match.group(2))
        span_start, span_end = match.span()
        context = text[max(0, span_start - 40): min(len(text), span_end + 40)]
        if any(token in context for token in edu_tokens):
            candidates.append(year)

    for match in re.finditer(r"(19\d{2}|20\d{2})\s*(?:届|年)?\s*毕业", text):
        year = int(match.group(1))
        candidates.append(year)

    valid = [year for year in candidates if 1980 <= year <= 2035]
    if not valid:
        return None
    return max(valid)


def extract_months_since_last_job_end(text: str) -> float | None:
    raw = str(text or "")
    lowered = raw.lower()
    if not raw.strip():
        return None

    # If the resume explicitly shows current employment, treat as 0 months since leaving.
    if any(token in raw for token in ("至今", "在职", "目前")) or any(token in lowered for token in ("present", "current")):
        return 0.0

    end_ym_candidates: list[tuple[int, int]] = []
    range_pattern = r"(19\d{2}|20\d{2})\s*[./年-]\s*(1[0-2]|0?[1-9])\s*[-~至到]\s*(19\d{2}|20\d{2})\s*[./年-]\s*(1[0-2]|0?[1-9])"
    for match in re.finditer(range_pattern, raw):
        end_year = int(match.group(3))
        end_month = int(match.group(4))
        if 1980 <= end_year <= 2035:
            end_ym_candidates.append((end_year, end_month))

    if not end_ym_candidates:
        return None

    end_year, end_month = max(end_ym_candidates)
    today = date.today()
    months = (today.year - end_year) * 12 + (today.month - end_month)
    return float(max(0, months))


def infer_candidate_item(job_id: str, text: str) -> dict[str, Any]:
    lowered = text.lower()
    if job_id == "qa_test_engineer_v1":
        tools = [label for token, label in QA_TOOLS.items() if token in lowered]
        industry_tags = [label for token, label in INDUSTRY_TAGS.items() if token in lowered and label in {"在线教育", "鸿蒙"}]
        return {
            "skills": list(dict.fromkeys(tools)),
            "industry_tags": list(dict.fromkeys(industry_tags)),
            "resume_summary": text[:1000],
            "project_keywords": [],
        }
    if job_id == "py_dev_engineer_v1":
        skills = [label for token, label in PY_SKILLS.items() if token in lowered]
        project_keywords = [label for token, label in INDUSTRY_TAGS.items() if token in lowered and label in {"安全", "AI"}]
        return {
            "skills": list(dict.fromkeys(skills)),
            "industry_tags": [tag for tag in project_keywords if tag == "安全"],
            "resume_summary": text[:1000],
            "project_keywords": list(dict.fromkeys(project_keywords)),
        }
    if job_id == "caption_ai_trainer_zhengzhou_v1":
        tags = [label for token, label in CAPTION_TRAINER_TAGS.items() if token in text]
        return {
            "skills": [],
            "industry_tags": list(dict.fromkeys(tags)),
            "resume_summary": text[:1000],
            "project_keywords": list(dict.fromkeys(tags)),
        }
    visual_tags = [label for token, label in CAP_VISUAL.items() if token in lowered]
    return {
        "skills": [],
        "industry_tags": list(dict.fromkeys(visual_tags)),
        "resume_summary": text[:1000],
        "project_keywords": list(dict.fromkeys(visual_tags)),
    }


def has_qa_testing_evidence(summary_text: str) -> bool:
    text = str(summary_text or "").lower()
    if not text:
        return False

    role_hits = sum(text.count(token) for token in QA_ROLE_SIGNALS)
    timeline_hits = len(re.findall(r"\d+\s*年(?:\d+\s*个月)?", text))
    section_hits = sum(1 for token in QA_HISTORY_SECTIONS if token in text)
    has_verb = any(token in text for token in QA_PROCESS_VERBS)
    has_artifact = any(token in text for token in QA_PROCESS_ARTIFACTS)
    has_combo = any(left in text and right in text for left, right in QA_STRONG_COMBOS)
    has_role_signal = any(token in text for token in QA_ROLE_SIGNALS)
    has_role_history = role_hits >= 2 and (timeline_hits >= 2 or section_hits >= 1)
    # Prefer strict "verb + artifact" evidence, but allow role-evidence fallback to reduce false negatives.
    return has_combo or (has_verb and has_artifact) or (has_role_signal and has_verb) or has_role_history


def build_fallback_normalized_fields(job_id: str, item: dict[str, Any]) -> dict[str, Any]:
    if job_id == "qa_test_engineer_v1":
        tools = item.get("skills", [])
        summary = str(item.get("resume_summary", "")).lower()
        months_since_last_job_end = extract_months_since_last_job_end(str(item.get("resume_summary", "")))
        role_hits = sum(summary.count(token) for token in QA_ROLE_SIGNALS)
        timeline_hits = len(re.findall(r"\d+\s*年(?:\d+\s*个月)?", summary))
        section_hits = sum(1 for token in QA_HISTORY_SECTIONS if token in summary)
        role_history_evidence = role_hits >= 2 and (timeline_hits >= 2 or section_hits >= 1)
        core_depth_base = min(
            1.0,
            0.4
            + 0.1
            * sum(
                token in summary
                for token in ("测试计划", "测试策略", "测试用例", "接口测试", "缺陷", "回归", "冒烟", "性能测试")
            ),
        )
        if role_history_evidence:
            core_depth_base = max(core_depth_base, min(0.82, 0.52 + 0.06 * min(role_hits, 4) + 0.04 * min(timeline_hits, 4)))
        return {
            "testing_evidence": has_qa_testing_evidence(summary),
            "qa_role_history_evidence": role_history_evidence,
            "core_test_depth_level": core_depth_base,
            "tools": tools,
            "frontend_backend_test": (
                any(token in summary for token in ("前端", "frontend", "web", "h5"))
                and any(token in summary for token in ("后端", "backend", "api", "接口"))
            ) or (
                any(token in summary for token in ("app", "小程序"))
                and any(token in summary for token in ("api", "接口", "后台"))
            ) or (
                any(token in summary for token in ("app", "安卓", "ios", "小程序"))
                and any(token in summary for token in ("web", "h5", "后台", "后端"))
            ),
            "defect_closure_level": (
                0.8
                if any(token in summary for token in ("缺陷", "bug", "闭环", "跟踪", "jira", "禅道", "tapd", "ones"))
                else (0.62 if role_history_evidence else 0.45)
            ),
            "months_since_last_job_end": months_since_last_job_end,
            "industry_tags": item.get("industry_tags", []),
            "analysis_logic_level": (
                0.75
                if any(token in summary for token in ("需求", "分析", "逻辑", "设计", "评审", "测试方案", "测试范围"))
                else (0.62 if role_history_evidence else 0.5)
            ),
        }
    if job_id == "py_dev_engineer_v1":
        merged = item.get("project_keywords", []) + item.get("skills", [])
        summary = str(item.get("resume_summary", "")).lower()
        return {
            "linux_experience": "linux" in summary or "shell" in summary,
            "python_engineering_level": 0.85 if "python" in summary else 0.45,
            "linux_shell_level": 0.8 if any(token in summary for token in ("linux", "shell")) else 0.3,
            "java_support_level": 0.6 if "java" in summary else 0.0,
            "middleware": [token for token in merged if str(token).lower() in {"kafka", "redis", "elasticsearch"}],
            "security_fit_level": 0.8 if any(token in summary for token in ("安全", "security")) else 0.3,
            "analysis_design_level": 0.7 if any(token in summary for token in ("设计", "架构", "需求")) else 0.4,
        }
    if job_id == "caption_ai_trainer_zhengzhou_v1":
        summary_raw = str(item.get("resume_summary", ""))
        summary = summary_raw.lower()
        location_text = " ".join(
            [
                str(item.get("location", "") or ""),
                summary_raw,
            ]
        )
        salary_text = " ".join(
            [
                str(item.get("expected_salary", "") or ""),
                summary_raw,
            ]
        )
        writing_tokens = ("写作", "文案", "描述", "稿件", "编辑", "内容创作", "文字", "脚本")
        rules_tokens = ("规则", "规范", "流程", "sop", "执行", "审核", "质检", "标注", "阅读理解")
        visual_tokens = ("画面", "镜头", "景别", "运镜", "光线", "色彩", "空间", "构图", "美感")
        film_tokens = ("影视", "视听", "景别", "运镜", "蒙太奇", "分镜", "镜头语言")
        stability_tokens = ("稳定", "长期", "持续", "日更", "高产", "耐心", "负责")
        ai_tokens = ("ai", "训练", "标注", "数据", "模型", "内容生成")
        zhengzhou_tokens = ("郑州", "河南", "henan", "zhengzhou")
        negative_edu_tokens = ("非全日制", "成人", "函授", "自考", "网络教育")
        full_time_tokens = ("统招", "全日制", "普通高校", "普通高等学校")
        degree_tokens = ("大专", "专科", "本科", "硕士", "博士", "college", "bachelor", "master", "phd")
        full_time_education = (
            any(token in summary_raw for token in full_time_tokens)
            or (any(token in summary for token in degree_tokens) and not any(token in summary_raw for token in negative_edu_tokens))
        )
        return {
            "zhengzhou_intent": any(token.lower() in location_text.lower() for token in zhengzhou_tokens),
            "expected_salary_in_range": _salary_in_4k_6k(salary_text),
            "writing_sample": any(token in summary_raw for token in writing_tokens),
            "rule_execution_evidence": any(token in summary for token in rules_tokens),
            "full_time_education": full_time_education,
            "graduation_year": _extract_graduation_year(summary_raw),
            "writing_naturalness_level": min(1.0, 0.35 + 0.12 * sum(token in summary_raw for token in writing_tokens)),
            "reading_rule_follow_level": min(1.0, 0.25 + 0.16 * sum(token in summary for token in rules_tokens)),
            "visual_analysis_level": min(1.0, 0.25 + 0.16 * sum(token in summary_raw for token in visual_tokens)),
            "film_language_level": min(1.0, 0.2 + 0.2 * sum(token in summary_raw for token in film_tokens)),
            "output_stability_level": min(1.0, 0.25 + 0.18 * sum(token in summary_raw for token in stability_tokens)),
            "ai_annotation_experience_level": min(1.0, 0.2 + 0.2 * sum(token in summary for token in ai_tokens)),
            "long_term_stability_level": 0.8 if any(token in summary_raw for token in ("长期", "稳定", "耐心", "负责")) else 0.35,
        }
    summary = str(item.get("resume_summary", "")).lower()
    visual_tags = item.get("industry_tags", []) or item.get("project_keywords", [])
    return {
        "media_caption_evidence": any(token in summary for token in ("视频", "图像", "caption", "标注")),
        "writing_sample": any(token in summary for token in ("文案", "描述", "作品", "portfolio", "report")),
        "aesthetic_writing_level": 0.85 if any(token in summary for token in ("美学", "镜头", "光影", "构图")) else 0.4,
        "film_art_theory_level": 0.7 if any(token in summary for token in ("电影", "影视", "艺术")) else 0.3,
        "ai_annotation_qc_level": 0.8 if any(token in summary for token in ("质检", "qc", "标注", "annotation")) else 0.3,
        "visual_domain_tags": visual_tags,
        "watching_volume_level": 0.7 if any(token in summary for token in ("观片", "片单", "影片")) else 0.2,
        "english_level": 1.0 if any(token in summary for token in ("cet-6", "专八", "ielts", "toefl")) else 0.2,
        "portfolio_level": 1.0 if any(token in summary for token in ("作品", "portfolio", "链接")) else 0.2,
        "gender": item.get("gender"),
    }
