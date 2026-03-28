import tempfile
import unittest
from pathlib import Path

from src.screening import db
from src.screening.extension_scoring import ExtensionScoreService
from src.screening.phase2_repositories import upsert_custom_scorecard
from src.screening.repositories import list_extension_score_events


class FakeExtractor:
    provider = "fake"
    model = "fake-model"
    last_usage = {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "provider": "fake",
        "model": "fake-model",
    }

    def extract_candidate(self, job_id: str, page_text: str):
        return {
            "name": "张三",
            "education_level": "本科",
            "years_experience": 5,
            "skills": ["Linux", "Postman", "JMeter"],
            "industry_tags": ["在线教育"],
            "project_keywords": [],
            "resume_summary": page_text[:500],
            "normalized_fields": {
                "testing_evidence": True,
                "core_test_depth_level": 0.92,
                "tools": ["Linux", "Postman", "JMeter"],
                "frontend_backend_test": True,
                "defect_closure_level": 0.8,
                "industry_tags": ["在线教育"],
                "analysis_logic_level": 0.7,
            },
            "evidence_map": {"model": "fake"},
        }


class FakeFailingExtractor:
    provider = "fake"
    model = "fake-model"
    last_usage = None

    def extract_candidate(self, job_id: str, page_text: str):
        raise RuntimeError("provider unavailable")


class FakeWrongNameExtractor(FakeExtractor):
    def extract_candidate(self, job_id: str, page_text: str):
        payload = super().extract_candidate(job_id, page_text)
        payload["name"] = "马聪博"
        return payload


class ExtensionScoreServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_db_path = db.DB_PATH
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._previous_db_path

    def test_scores_candidate_page_and_records_audit(self):
        service = ExtensionScoreService(extractor=FakeExtractor())
        result = service.score_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/geek/job-recommend/abc123.html",
            page_title="测试工程师 - BOSS直聘",
            candidate_hint="张三 / 测试工程师",
            page_text="5年测试经验，本科，熟悉 Linux、Postman、JMeter，做过接口测试和回归测试。",
        )

        self.assertEqual(result["decision"], "recommend")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["external_id"], "abc123")
        self.assertEqual(result["model_usage"]["total_tokens"], 20)
        self.assertIn("dimension_scores", result)

        events = list_extension_score_events(limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["job_id"], "qa_test_engineer_v1")
        self.assertEqual(events[0]["page_url"], "https://www.zhipin.com/web/geek/job-recommend/abc123.html")
        self.assertEqual(events[0]["external_id"], "abc123")
        self.assertFalse(events[0]["fallback_used"])

    def test_falls_back_to_heuristics_when_extractor_fails(self):
        service = ExtensionScoreService(extractor=FakeFailingExtractor())
        result = service.score_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/geek/job-recommend/fallback001.html",
            page_title="测试工程师",
            candidate_hint="李四 / QA",
            page_text="3年测试工程师经验，本科，负责接口测试、功能测试、缺陷跟踪和回归。",
        )

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["model_usage"]["total_tokens"], 0)
        self.assertIn(result["decision"], {"review", "recommend"})
        self.assertTrue(result["extracted_fields"]["normalized_fields"]["testing_evidence"])

        events = list_extension_score_events(limit=10)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["fallback_used"])

    def test_prefers_page_candidate_name_hint_over_model_name(self):
        service = ExtensionScoreService(extractor=FakeWrongNameExtractor())
        result = service.score_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/recommend/?jobId=123",
            page_title="测试工程师",
            candidate_hint="朱浩瀚",
            page_text="朱浩瀚\n26岁 6年 本科 在职-月内到岗\n工作经历\n熟悉软件测试流程。",
        )

        self.assertEqual(result["extracted_fields"]["name"], "朱浩瀚")

    def test_scores_custom_phase2_scorecard(self):
        custom = upsert_custom_scorecard(
            {
                "name": "Python开发-北京",
                "scorecard": {
                    "name": "Python开发-北京",
                    "role_title": "Python开发工程师",
                    "jd_text": "Python开发工程师，北京，本科，3年以上，熟悉 Python、Linux、Redis",
                    "filters": {"location": "北京", "years_min": 3, "education_min": "本科"},
                    "must_have": ["Python", "Linux", "Redis"],
                    "nice_to_have": [],
                    "exclude": [],
                    "titles": ["Python开发工程师"],
                    "industry": [],
                    "weights": {
                        "must_have": 50,
                        "nice_to_have": 0,
                        "title_match": 15,
                        "industry_match": 0,
                        "experience": 20,
                        "education": 10,
                        "location": 5,
                    },
                    "thresholds": {"recommend_min": 70, "review_min": 50},
                    "hard_filters": {
                        "enforce_years": True,
                        "enforce_education": True,
                        "enforce_location": False,
                        "strict_exclude": False,
                        "must_have_ratio_min": 0.5,
                    },
                },
            }
        )
        service = ExtensionScoreService(extractor=FakeExtractor())
        result = service.score_candidate_page(
            job_id=custom["id"],
            page_url="https://www.zhipin.com/web/geek/job-recommend/abc123.html",
            page_title="Python开发工程师 - BOSS直聘",
            candidate_hint="张三 / Python",
            page_text="张三\n现居住地：北京\n求职意向：Python开发工程师\n5年工作经验\n本科\n熟悉 Python Linux Redis Kafka。",
        )

        self.assertEqual(result["decision"], "recommend")
        self.assertEqual(result["scorecard_kind"], "custom_phase2")
        self.assertIn("Python", result["matched_terms"])
        self.assertIn("Linux", result["matched_terms"])

    def test_rejects_unknown_job(self):
        service = ExtensionScoreService(extractor=FakeExtractor())
        with self.assertRaises(KeyError):
            service.score_candidate_page(
                job_id="unknown_job",
                page_url="https://www.zhipin.com/web/geek/job-recommend/unknown.html",
                page_text="测试工程师",
            )

    def test_rejects_empty_page_text(self):
        service = ExtensionScoreService(extractor=FakeExtractor())
        with self.assertRaisesRegex(ValueError, "page_text"):
            service.score_candidate_page(
                job_id="qa_test_engineer_v1",
                page_url="https://www.zhipin.com/web/geek/job-recommend/empty.html",
                page_text="   ",
            )
