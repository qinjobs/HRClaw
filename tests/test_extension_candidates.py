import tempfile
import unittest
from pathlib import Path

from src.screening import db
from src.screening.extension_candidates import ExtensionCandidateIngestService
from src.screening.phase2_repositories import upsert_custom_scorecard
from src.screening.repositories import get_candidate_pipeline_state, save_candidate_stage_action


class FakeScoreService:
    def score_candidate_page(self, **kwargs):
        return {
            "audit_event_id": "evt-1",
            "job_id": kwargs["job_id"],
            "external_id": "geek-001",
            "score": 88.5,
            "decision": "recommend",
            "hard_filter_pass": True,
            "dimension_scores": {"tools_coverage": 18.0},
            "hard_filter_fail_reasons": [],
            "review_reasons": ["测试证据充分"],
            "extracted_fields": {"name": "张三"},
            "fallback_used": False,
            "model_usage": {"total_tokens": 12},
            "scored_at": "2026-03-19T09:00:00Z",
        }


class ExtensionCandidateIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_db_path = db.DB_PATH
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._previous_db_path

    def test_upsert_creates_extension_candidate_snapshot_and_binding(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())

        result = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试、Selenium、Postman。",
            candidate_name="张三",
            source="boss_extension_v1",
            context_key="ctx-001",
        )

        self.assertTrue(result["created_new"])
        self.assertEqual(result["pipeline_state"]["current_stage"], "new")
        self.assertFalse(result["manual_stage_locked"])

        with db.connect() as conn:
            candidates = conn.execute("select * from candidates").fetchall()
            bindings = conn.execute("select * from extension_candidate_bindings").fetchall()
            snapshots = conn.execute("select * from candidate_snapshots").fetchall()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source"], "boss_extension")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["external_id"], "geek-001")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["page_type"], "boss_resume_detail")

    def test_upsert_reuses_same_candidate_for_same_job(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())
        first = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
            candidate_name="张三",
            source="boss_extension_v1",
        )
        second = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试、Postman。",
            candidate_name="张三",
            source="boss_extension_v1",
        )

        self.assertTrue(first["created_new"])
        self.assertFalse(second["created_new"])
        self.assertEqual(first["candidate_id"], second["candidate_id"])

        with db.connect() as conn:
            candidates = conn.execute("select * from candidates").fetchall()
            bindings = conn.execute("select * from extension_candidate_bindings").fetchall()
            snapshots = conn.execute("select * from candidate_snapshots").fetchall()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(len(snapshots), 2)

    def test_upsert_reuses_existing_candidate_without_external_id_when_identity_matches(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())
        first = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=qa",
            page_title="推荐牛人",
            page_text=(
                "付伟\n面议\n付伟\n34岁 6年 本科 离职-随时到岗\n"
                "最近关注\n北京 测试工程师\n优势\n熟悉接口测试、Selenium、Appium。\n"
                "继续沟通\n经历概览\n收藏\n举报\n转发牛人"
            ),
            candidate_name="付伟",
            source="boss_extension_v1",
            source_candidate_key="legacy-a",
        )
        second = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=qa",
            page_title="推荐牛人",
            page_text=(
                "付伟\n面议\n付伟\n34岁 6年 本科 离职-随时到岗\n"
                "最近关注\n北京 测试工程师\n优势\n熟悉接口测试、Selenium、Appium。\n"
                "打招呼\n经历概览\n经历概览\n小米科技有限责任公司\n2024.10 - 2026.01"
            ),
            candidate_name="付伟",
            source="boss_extension_v1",
            source_candidate_key="legacy-b",
        )

        self.assertTrue(first["created_new"])
        self.assertFalse(second["created_new"])
        self.assertEqual(first["candidate_id"], second["candidate_id"])

        with db.connect() as conn:
            candidates = conn.execute("select * from candidates").fetchall()
            bindings = conn.execute("select * from extension_candidate_bindings").fetchall()
            snapshots = conn.execute("select * from candidate_snapshots").fetchall()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["source_candidate_key"], "legacy-a")
        self.assertEqual(len(snapshots), 2)

    def test_score_advances_new_candidate_to_scored(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())
        ingest = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
            candidate_name="张三",
            source="boss_extension_v1",
        )

        result = service.score_candidate(
            candidate_id=ingest["candidate_id"],
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
            candidate_hint="张三",
            source="boss_extension_v1",
        )

        self.assertEqual(result["candidate_id"], ingest["candidate_id"])
        self.assertEqual(result["pipeline_state"]["current_stage"], "scored")
        self.assertFalse(result["state_transition"]["skipped"])

        with db.connect() as conn:
            scores = conn.execute("select * from candidate_scores").fetchall()
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["decision"], "recommend")

    def test_score_does_not_override_manual_stage_lock(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())
        ingest = service.upsert_candidate_page(
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
            candidate_name="张三",
            source="boss_extension_v1",
        )
        save_candidate_stage_action(
            ingest["candidate_id"],
            operator="hr_ui",
            current_stage="to_review",
            reason_code="resume_incomplete",
            reason_notes="需要再看项目深度",
            final_decision="review",
            owner="hr_1",
            reusable_flag=None,
            do_not_contact=None,
            talent_pool_status=None,
            last_contacted_at=None,
            last_contact_result=None,
            next_follow_up_at=None,
        )

        result = service.score_candidate(
            candidate_id=ingest["candidate_id"],
            job_id="qa_test_engineer_v1",
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
            page_title="测试工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
            candidate_hint="张三",
            source="boss_extension_v1",
        )

        state = get_candidate_pipeline_state(ingest["candidate_id"])
        self.assertTrue(state["manual_stage_locked"])
        self.assertEqual(state["current_stage"], "to_review")
        self.assertTrue(result["state_transition"]["skipped"])

    def test_upsert_rejects_non_resume_shell_page(self):
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())

        with self.assertRaisesRegex(ValueError, "可入库的候选人详情页"):
            service.upsert_candidate_page(
                job_id="qa_test_engineer_v1",
                page_url="https://www.zhipin.com/web/chat/recommend",
                page_title="BOSS直聘",
                page_text="职位管理\n推荐牛人\n搜索\n沟通\n孙剑\n27岁 7年 本科",
                candidate_name="职位管理",
                source="boss_extension_v1",
            )

    def test_upsert_accepts_custom_phase2_scorecard(self):
        custom = upsert_custom_scorecard(
            {
                "name": "后端初筛卡",
                "scorecard": {
                    "name": "后端初筛卡",
                    "role_title": "Python开发工程师",
                    "jd_text": "Python开发工程师，北京，本科，3年以上，熟悉 Python、Linux、Redis",
                },
            }
        )
        service = ExtensionCandidateIngestService(scorer=FakeScoreService())
        result = service.upsert_candidate_page(
            job_id=custom["id"],
            page_url="https://www.zhipin.com/web/frame/c-resume/?geekId=geek-009",
            page_title="Python开发工程师",
            page_text="张三\n26岁 5年 本科\n工作经历\n熟悉 Python、Linux、Redis。",
            candidate_name="张三",
            source="boss_extension_v1",
        )

        self.assertTrue(result["created_new"])
