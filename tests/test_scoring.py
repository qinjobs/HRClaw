import unittest
from unittest import mock

from src.screening.models import CandidateDecision
from src.screening.scoring import score_candidate


class ScoringTests(unittest.TestCase):
    def test_qa_candidate_recommend(self):
        score = score_candidate(
            "qa_test_engineer_v1",
            {
                "education_level": "本科",
                "years_experience": 6,
                "testing_evidence": True,
                "core_test_depth_level": 1.0,
                "tools": ["Linux", "adb", "Charles", "MySQL", "Postman", "JMeter"],
                "frontend_backend_test": True,
                "defect_closure_level": 0.9,
                "industry_tags": ["在线教育"],
                "analysis_logic_level": 0.8,
            },
        )
        self.assertTrue(score.hard_filter_pass)
        self.assertEqual(score.decision, CandidateDecision.RECOMMEND)
        self.assertGreaterEqual(score.total_score, 75)

    def test_qa_candidate_reject_on_hard_filter(self):
        score = score_candidate(
            "qa_test_engineer_v1",
            {
                "education_level": "本科",
                "years_experience": 2,
                "testing_evidence": True,
            },
        )
        self.assertFalse(score.hard_filter_pass)
        self.assertEqual(score.decision, CandidateDecision.REJECT)

    def test_qa_candidate_years_string_is_supported(self):
        score = score_candidate(
            "qa_test_engineer_v1",
            {
                "education_level": "本科",
                "years_experience": "4年8个月",
                "testing_evidence": True,
                "core_test_depth_level": 0.8,
                "tools": ["Linux", "Postman", "JMeter"],
                "frontend_backend_test": True,
                "defect_closure_level": 0.7,
                "industry_tags": ["在线教育"],
                "analysis_logic_level": 0.7,
            },
        )
        self.assertTrue(score.hard_filter_pass)
        self.assertIn(score.decision, {CandidateDecision.RECOMMEND, CandidateDecision.REVIEW})

    def test_qa_candidate_reject_on_last_job_leave_older_than_two_months(self):
        score = score_candidate(
            "qa_test_engineer_v1",
            {
                "education_level": "本科",
                "years_experience": 6,
                "testing_evidence": True,
                "months_since_last_job_end": 3,
                "core_test_depth_level": 0.9,
                "tools": ["Linux", "Postman", "JMeter", "Charles", "MySQL"],
                "frontend_backend_test": True,
                "defect_closure_level": 0.8,
                "industry_tags": ["在线教育"],
                "analysis_logic_level": 0.8,
            },
        )
        self.assertFalse(score.hard_filter_pass)
        self.assertIn("Last job end date is over 2 months ago.", score.hard_filter_fail_reasons)
        self.assertEqual(score.decision, CandidateDecision.REJECT)

    def test_custom_jd_scorecard_honors_age_range(self):
        custom_target = {
            "kind": "custom_phase2",
            "scorecard": {
                "name": "前端开发-年龄范围",
                "filters": {"age_min": 25, "age_max": 35},
                "weights": {
                    "must_have": 0,
                    "nice_to_have": 0,
                    "title_match": 0,
                    "industry_match": 0,
                    "experience": 0,
                    "education": 0,
                    "location": 0,
                },
                "thresholds": {"recommend_min": 75, "review_min": 55},
                "hard_filters": {"enforce_age": True, "must_have_ratio_min": 0},
                "must_have": [],
                "nice_to_have": [],
                "exclude": [],
                "titles": [],
                "industry": [],
            },
        }
        with mock.patch("src.screening.scoring.get_scoring_target", return_value=custom_target):
            score = score_candidate(
                "phase2_custom_age_card",
                {
                    "name": "张三",
                    "age": 24,
                    "education_level": "本科",
                    "years_experience": 5,
                },
            )

        self.assertFalse(score.hard_filter_pass)
        self.assertIn("年龄不在 25.0-35.0 岁范围内", score.hard_filter_fail_reasons)
        self.assertEqual(score.decision, CandidateDecision.REJECT)

    def test_custom_jd_scorecard_missing_age_is_review_signal_not_hard_reject(self):
        custom_target = {
            "kind": "custom_phase2",
            "scorecard": {
                "name": "AI应用开发工程师",
                "filters": {"age_min": 22, "age_max": 35},
                "weights": {
                    "must_have": 42,
                    "nice_to_have": 12,
                    "title_match": 12,
                    "industry_match": 8,
                    "experience": 14,
                    "education": 7,
                    "location": 5,
                },
                "thresholds": {"recommend_min": 60, "review_min": 40},
                "hard_filters": {"enforce_age": True, "must_have_ratio_min": 0.0},
                "must_have": ["JAVA", "AI"],
                "nice_to_have": [],
                "exclude": [],
                "titles": ["AI应用开发工程师"],
                "industry": ["AI"],
            },
        }
        with mock.patch("src.screening.scoring.get_scoring_target", return_value=custom_target):
            score = score_candidate(
                "phase2_custom_age_missing",
                {
                    "name": "张三",
                    "years_experience": 6,
                    "education_level": "本科",
                    "current_title": "AI应用开发工程师",
                    "raw_summary": "6年JAVA开发经验，做过AI应用开发和智能体落地。",
                },
            )

        self.assertTrue(score.hard_filter_pass)
        self.assertIn("年龄信息缺失，建议人工复核。", score.review_reasons)
        self.assertIn(score.decision, {CandidateDecision.RECOMMEND, CandidateDecision.REVIEW})

    def test_custom_jd_scorecard_ignores_gender_based_exclude_terms(self):
        custom_target = {
            "kind": "custom_phase2",
            "scorecard": {
                "name": "AI应用开发工程师",
                "filters": {},
                "weights": {
                    "must_have": 42,
                    "nice_to_have": 12,
                    "title_match": 12,
                    "industry_match": 8,
                    "experience": 14,
                    "education": 7,
                    "location": 5,
                },
                "thresholds": {"recommend_min": 60, "review_min": 40},
                "hard_filters": {"strict_exclude": True, "must_have_ratio_min": 0.0},
                "must_have": ["JAVA"],
                "nice_to_have": [],
                "exclude": ["女"],
                "titles": ["AI应用开发工程师"],
                "industry": [],
            },
        }
        with mock.patch("src.screening.scoring.get_scoring_target", return_value=custom_target):
            score = score_candidate(
                "phase2_custom_gender_exclude",
                {
                    "name": "李四",
                    "years_experience": 6,
                    "education_level": "本科",
                    "current_title": "AI应用开发工程师",
                    "raw_summary": "女，6年JAVA开发经验。",
                },
            )

        self.assertTrue(score.hard_filter_pass)
        self.assertNotIn("命中排除项", " ".join(score.hard_filter_fail_reasons))

    def test_caption_gender_bonus_forces_review(self):
        score = score_candidate(
            "caption_aesthetic_qc_v1",
            {
                "media_caption_evidence": True,
                "writing_sample": True,
                "aesthetic_writing_level": 1.0,
                "film_art_theory_level": 1.0,
                "ai_annotation_qc_level": 1.0,
                "visual_domain_tags": ["摄影", "光影", "服化道"],
                "watching_volume_level": 1.0,
                "english_level": 1.0,
                "portfolio_level": 1.0,
                "gender": "female",
            },
        )
        self.assertEqual(score.decision, CandidateDecision.REVIEW)
        self.assertTrue(score.review_reasons)

    def test_caption_ai_trainer_zhengzhou_recommend(self):
        score = score_candidate(
            "caption_ai_trainer_zhengzhou_v1",
            {
                "zhengzhou_intent": True,
                "age": 24,
                "education_level": "本科",
                "full_time_education": True,
                "graduation_year": 2024,
                "writing_naturalness_level": 0.95,
                "reading_rule_follow_level": 0.85,
                "visual_analysis_level": 0.8,
                "film_language_level": 0.7,
                "output_stability_level": 0.9,
                "ai_annotation_experience_level": 0.6,
                "long_term_stability_level": 0.8,
            },
        )
        self.assertTrue(score.hard_filter_pass)
        self.assertEqual(score.decision, CandidateDecision.RECOMMEND)
        self.assertGreaterEqual(score.total_score, 80)

    def test_caption_ai_trainer_zhengzhou_reject_on_hard_filter(self):
        score = score_candidate(
            "caption_ai_trainer_zhengzhou_v1",
            {
                "zhengzhou_intent": True,
                "age": 23,
                "education_level": "本科",
                "full_time_education": True,
                "graduation_year": 2026,
                "writing_naturalness_level": 1.0,
                "reading_rule_follow_level": 1.0,
                "visual_analysis_level": 1.0,
                "film_language_level": 1.0,
                "output_stability_level": 1.0,
                "ai_annotation_experience_level": 1.0,
                "long_term_stability_level": 1.0,
            },
        )
        self.assertFalse(score.hard_filter_pass)
        self.assertEqual(score.decision, CandidateDecision.REJECT)
