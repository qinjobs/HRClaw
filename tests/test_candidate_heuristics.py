import unittest

from datetime import date

from src.screening.candidate_heuristics import (
    build_fallback_normalized_fields,
    extract_months_since_last_job_end,
    extract_years_experience,
    has_qa_testing_evidence,
)


class CandidateHeuristicsTests(unittest.TestCase):
    def test_extract_years_experience_supports_chinese_number(self):
        text = "工作经验：九年，测试工程师，负责功能和接口测试。"
        self.assertEqual(extract_years_experience(text), 9.0)

    def test_extract_years_experience_handles_ocr_bullet_artifact(self):
        text = "自我评价\n1.3年功能测试经验，熟悉测试流程。"
        self.assertEqual(extract_years_experience(text), 3.0)

    def test_has_qa_testing_evidence_with_role_history_fallback(self):
        summary = (
            "经历概览\n测试工程师 3年\n软件测试 2年\n"
            "项目经验\n测试工程师 1年\n"
        )
        self.assertTrue(has_qa_testing_evidence(summary))

    def test_build_fallback_normalized_fields_sets_role_history_flag(self):
        item = {
            "resume_summary": "经历概览 测试工程师 3年 软件测试 2年 项目经验 测试工程师 1年",
            "skills": [],
            "industry_tags": [],
        }
        normalized = build_fallback_normalized_fields("qa_test_engineer_v1", item)
        self.assertTrue(normalized["qa_role_history_evidence"])
        self.assertTrue(normalized["testing_evidence"])

    def test_extract_months_since_last_job_end_when_current_job_exists(self):
        text = "工作经历：2024.01 - 至今 测试工程师"
        self.assertEqual(extract_months_since_last_job_end(text), 0.0)

    def test_extract_months_since_last_job_end_from_range(self):
        text = "工作经历：2023.06 - 2025.01 软件测试工程师"
        months = extract_months_since_last_job_end(text)
        self.assertIsNotNone(months)
        today = date.today()
        expected = (today.year - 2025) * 12 + (today.month - 1)
        self.assertEqual(months, float(max(0, expected)))
