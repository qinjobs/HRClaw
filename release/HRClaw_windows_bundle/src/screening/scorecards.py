from __future__ import annotations

from typing import Any


SCORECARDS: dict[str, dict] = {
    "qa_test_engineer_v1": {
        "name": "QA Test Engineer",
        "hard_filters": [
            {
                "id": "hf_qa_degree",
                "field": "education_level",
                "kind": "in_set",
                "value": ["bachelor", "master", "phd", "统招本科", "本科", "硕士", "博士"],
                "message": "Education below bachelor level.",
            },
            {
                "id": "hf_qa_years",
                "field": "years_experience",
                "kind": "min_number",
                "value": 3,
                "message": "Software testing or development experience below 3 years.",
            },
            {
                "id": "hf_qa_core",
                "field": "testing_evidence",
                "kind": "truthy",
                "message": "Missing core testing workflow evidence.",
            },
            {
                "id": "hf_qa_recent_leave",
                "field": "months_since_last_job_end",
                "kind": "max_number_if_present",
                "value": 2,
                "message": "Last job end date is over 2 months ago.",
            },
        ],
        # Calibrated on task dc0de2ea-2437-4d92-a3e5-fea11945e6fa (50 resumes):
        # target split priority/general/reject = 10/15/25 (20%/30%/50%).
        "thresholds": {"recommend_min": 57.62, "review_min": 39.78},
        "weights": {
            "core_test_depth": 22,
            "tools_coverage": 18,
            "frontend_backend": 12,
            "defect_closure": 16,
            "industry_fit": 8,
            "analysis_logic": 12,
            "experience_maturity": 12,
        },
    },
    "py_dev_engineer_v1": {
        "name": "Python Development Engineer",
        "hard_filters": [
            {
                "id": "hf_py_degree",
                "field": "education_level",
                "kind": "in_set",
                "value": ["bachelor", "master", "phd", "本科", "硕士", "博士"],
                "message": "Education below bachelor level.",
            },
            {
                "id": "hf_py_years",
                "field": "years_experience",
                "kind": "min_number",
                "value": 3,
                "message": "Python development experience below 3 years.",
            },
            {
                "id": "hf_py_linux",
                "field": "linux_experience",
                "kind": "truthy",
                "message": "Missing Linux or shell evidence.",
            },
        ],
        "thresholds": {"recommend_min": 82, "review_min": 62},
        "weights": {
            "python_engineering": 30,
            "linux_shell": 15,
            "java_support": 10,
            "middleware_stack": 20,
            "security_fit": 15,
            "analysis_design": 10,
        },
    },
    "caption_aesthetic_qc_v1": {
        "name": "Caption Aesthetic QC",
        "hard_filters": [
            {
                "id": "hf_cap_video",
                "field": "media_caption_evidence",
                "kind": "truthy",
                "message": "Missing video or image caption evidence.",
            },
            {
                "id": "hf_cap_text",
                "field": "writing_sample",
                "kind": "truthy",
                "message": "Missing writing sample or portfolio evidence.",
            },
        ],
        "thresholds": {"recommend_min": 80, "review_min": 60},
        "weights": {
            "aesthetic_writing": 30,
            "film_art_theory": 15,
            "ai_annotation_qc": 20,
            "visual_domain_coverage": 15,
            "watching_volume": 5,
            "english": 5,
            "portfolio": 5,
            "gender_bonus": 5,
        },
    },
    "caption_ai_trainer_zhengzhou_v1": {
        "name": "Caption AI Trainer (Zhengzhou)",
        "hard_filters": [
            {
                "id": "hf_caption_zz_city",
                "field": "zhengzhou_intent",
                "kind": "truthy",
                "message": "Target city mismatch: candidate is not aligned to Zhengzhou.",
            },
            {
                "id": "hf_caption_zz_age",
                "field": "age",
                "kind": "min_number",
                "value": 22,
                "message": "Age is below 22.",
            },
            {
                "id": "hf_caption_zz_edu_level",
                "field": "education_level",
                "kind": "in_set",
                "value": [
                    "统招大专",
                    "大专",
                    "专科",
                    "college",
                    "统招本科",
                    "本科",
                    "bachelor",
                    "统招硕士",
                    "硕士",
                    "master",
                    "博士",
                    "phd",
                ],
                "message": "Education is below full-time junior college level.",
            },
            {
                "id": "hf_caption_zz_full_time",
                "field": "full_time_education",
                "kind": "truthy",
                "message": "Missing full-time education evidence.",
            },
            {
                "id": "hf_caption_zz_grad_year",
                "field": "graduation_year",
                "kind": "max_number",
                "value": 2025,
                "message": "Graduation year is later than 2025.",
            },
        ],
        "thresholds": {"recommend_min": 80, "review_min": 65},
        "weights": {
            "writing_naturalness": 35,
            "reading_rule_follow": 20,
            "visual_analysis": 15,
            "film_language": 10,
            "output_stability": 10,
            "ai_annotation_experience": 5,
            "long_term_stability": 5,
        },
    },
}


def normalize_builtin_scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("scorecard 必须是对象")
    normalized = dict(payload)
    name = str(normalized.get("name") or "").strip()
    if not name:
        raise ValueError("评分卡名称不能为空")
    hard_filters = normalized.get("hard_filters")
    thresholds = normalized.get("thresholds")
    weights = normalized.get("weights")
    if not isinstance(hard_filters, list):
        raise ValueError("第一阶段评分卡的 hard_filters 必须是数组")
    if not isinstance(thresholds, dict):
        raise ValueError("第一阶段评分卡的 thresholds 必须是对象")
    if not isinstance(weights, dict):
        raise ValueError("第一阶段评分卡的 weights 必须是对象")
    normalized["name"] = name
    normalized["schema_version"] = str(normalized.get("schema_version") or "phase1_builtin_v1")
    return normalized


MOCK_CANDIDATES: dict[str, list[dict]] = {
    "qa_test_engineer_v1": [
        {
            "external_id": "boss-qa-001",
            "name": "Liu Qing",
            "age": 28,
            "education_level": "本科",
            "major": "计算机科学",
            "years_experience": 4,
            "current_company": "Blue Edu",
            "current_title": "测试工程师",
            "expected_salary": "12K",
            "location": "Beijing",
            "last_active_time": "1h",
            "raw_summary": "4 years QA, online education, Linux, adb, Charles, API testing.",
            "normalized_fields": {
                "testing_evidence": True,
                "core_test_depth_level": 0.9,
                "tools": ["Linux", "adb", "Charles", "MySQL"],
                "frontend_backend_test": True,
                "defect_closure_level": 0.8,
                "industry_tags": ["在线教育"],
                "analysis_logic_level": 0.7,
            },
            "evidence_map": {
                "years_experience": "顶部摘要显示 4年",
                "industry_tags": "经历提到在线教育平台",
            },
        },
        {
            "external_id": "boss-qa-002",
            "name": "Zhao Wei",
            "age": 25,
            "education_level": "本科",
            "major": "信息管理",
            "years_experience": 2,
            "current_company": "Retail App",
            "current_title": "测试专员",
            "expected_salary": "9K",
            "location": "Beijing",
            "last_active_time": "3h",
            "raw_summary": "2 years QA, manual tests, some Charles.",
            "normalized_fields": {
                "testing_evidence": True,
                "core_test_depth_level": 0.5,
                "tools": ["Charles"],
                "frontend_backend_test": False,
                "defect_closure_level": 0.4,
                "industry_tags": [],
                "analysis_logic_level": 0.5,
            },
            "evidence_map": {"years_experience": "顶部摘要显示 2年"},
        },
    ],
    "py_dev_engineer_v1": [
        {
            "external_id": "boss-py-001",
            "name": "Wang Hao",
            "age": 31,
            "education_level": "本科",
            "major": "软件工程",
            "years_experience": 6,
            "current_company": "Secure Cloud",
            "current_title": "Python开发工程师",
            "expected_salary": "28K",
            "location": "Hangzhou",
            "last_active_time": "30m",
            "raw_summary": "Python, Java, Linux, Kafka, Redis, Elasticsearch, web security.",
            "normalized_fields": {
                "linux_experience": True,
                "python_engineering_level": 0.9,
                "linux_shell_level": 0.8,
                "java_support_level": 0.7,
                "middleware": ["kafka", "redis", "elasticsearch"],
                "security_fit_level": 0.8,
                "analysis_design_level": 0.7,
            },
            "evidence_map": {"middleware": "项目经历列出 Kafka Redis Elasticsearch"},
        }
    ],
    "caption_aesthetic_qc_v1": [
        {
            "external_id": "boss-cap-001",
            "name": "Chen Yu",
            "age": 27,
            "education_level": "本科",
            "major": "戏剧影视美术设计",
            "years_experience": 3,
            "current_company": "Vision Label",
            "current_title": "视频标注质检",
            "expected_salary": "15K",
            "location": "Shanghai",
            "last_active_time": "2h",
            "raw_summary": "AI video annotation, strong aesthetic writing, portfolio available.",
            "normalized_fields": {
                "media_caption_evidence": True,
                "writing_sample": True,
                "aesthetic_writing_level": 0.9,
                "film_art_theory_level": 0.8,
                "ai_annotation_qc_level": 0.9,
                "visual_domain_tags": ["摄影", "光影", "服化道"],
                "watching_volume_level": 1.0,
                "english_level": 1.0,
                "portfolio_level": 1.0,
                "gender": "female",
            },
            "evidence_map": {"portfolio_level": "简历附作品集链接"},
        }
    ],
}
