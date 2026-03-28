import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.repositories import (
    add_candidate_tag,
    add_candidate_timeline_event,
    create_task,
    insert_candidate,
    insert_candidate_action,
    insert_score,
    insert_snapshot,
    upsert_candidate_pipeline_state,
    upsert_extension_candidate_binding,
)


class HrWorkbenchApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        self.api = api
        self.api.init_db()

        self.task_id = create_task(
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "recommend",
                "sort_by": "active",
                "max_candidates": 1,
                "max_pages": 1,
                "search_config": {"keyword": "测试工程师", "city": "北京"},
                "require_hr_confirmation": True,
            }
        )
        self.candidate_id = insert_candidate(
            self.task_id,
            {
                "external_id": "boss-workbench-001",
                "name": "候选人B",
                "age": 30,
                "education_level": "本科",
                "years_experience": 6,
                "current_company": "Blue Demo",
                "current_title": "测试工程师",
                "expected_salary": "20K",
                "location": "北京",
                "last_active_time": "今日活跃",
                "raw_summary": "负责接口测试、自动化测试与线上问题排查。",
                "normalized_fields": {"testing_evidence": True},
            },
        )
        screenshot_path = Path(self.tmpdir.name) / "workbench.png"
        screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        insert_snapshot(
            self.candidate_id,
            "candidate_detail",
            str(screenshot_path),
            "候选人具备接口测试和自动化测试经验，熟悉北京互联网项目。",
            {"gpt_extraction_used": True},
        )
        insert_score(
            self.candidate_id,
            "qa_test_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"core": 62},
                "total_score": 86.0,
                "decision": "recommend",
                "review_reasons": ["Recommend-level score below strong-pass band. Manual spot-check advised."],
            },
        )
        insert_candidate_action(
            self.candidate_id,
            "send_greeting",
            "success",
            {"reason": "auto_greet"},
        )
        upsert_candidate_pipeline_state(
            self.candidate_id,
            owner="hr_a",
            current_stage="to_review",
            reason_code="skills_match",
            reason_notes="先看项目细节再决定是否邀约",
            final_decision="review",
            next_follow_up_at="2026-03-20T10:00",
            reusable_flag=True,
        )
        add_candidate_tag(self.candidate_id, "在线教育测试", "hr_a")
        add_candidate_timeline_event(
            self.candidate_id,
            "seeded",
            "system",
            {"source": "unit_test"},
        )

    def _make_handler(self, method: str, path: str, payload: dict | None = None):
        raw = json.dumps(payload or {}).encode("utf-8")
        handler = type("Handler", (), {})()
        handler.command = method
        handler.headers = {"Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = mock.Mock()
        handler.rfile.read = mock.Mock(return_value=raw)
        return handler

    def _login_and_get_cookie(self) -> str:
        handler = self._make_handler("POST", "/api/login", {"username": "admin", "password": "admin"})
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        cookie_header = headers.get("Set-Cookie", "")
        self.assertIn("screening_session=", cookie_header)
        return cookie_header.split(";", 1)[0]

    def test_hr_workbench_api_returns_items(self):
        handler = self._make_handler("GET", "/api/hr/workbench?stage=to_review&reusable_only=1&limit=10")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["items"][0]["candidate_id"], self.candidate_id)
        self.assertEqual(payload["items"][0]["pipeline_state"]["current_stage"], "to_review")
        self.assertTrue(payload["items"][0]["pipeline_state"]["reusable_flag"])
        self.assertIn("在线教育测试", payload["items"][0]["tags"])

    def test_hr_workbench_candidate_detail_returns_state_tags_and_timeline(self):
        handler = self._make_handler("GET", f"/api/hr/workbench/candidates/{self.candidate_id}")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["candidate"]["id"], self.candidate_id)
        self.assertEqual(payload["pipeline_state"]["owner"], "hr_a")
        self.assertEqual(payload["tags"][0]["tag"], "在线教育测试")
        self.assertEqual(payload["timeline"][0]["event_type"], "seeded")

    def test_workbench_stage_tag_and_followup_endpoints(self):
        stage_handler = self._make_handler(
            "POST",
            f"/api/candidates/{self.candidate_id}/stage",
            {
                "operator": "hr_ui",
                "owner": "hr_b",
                "current_stage": "to_contact",
                "reason_code": "candidate_positive",
                "reason_notes": "可以直接沟通邀约",
                "final_decision": "recommend",
                "review_action": "approve",
                "reusable_flag": True,
                "next_follow_up_at": "2026-03-21T14:00",
            },
        )
        status, body = self.api.handle_request(stage_handler)
        self.assertEqual(status, 200)
        stage_payload = json.loads(body)
        self.assertEqual(stage_payload["state"]["current_stage"], "to_contact")
        self.assertEqual(stage_payload["state"]["owner"], "hr_b")

        tag_handler = self._make_handler(
            "POST",
            f"/api/candidates/{self.candidate_id}/tags",
            {"tag": "北京自动化测试", "created_by": "hr_ui"},
        )
        status, body = self.api.handle_request(tag_handler)
        self.assertEqual(status, 201)
        self.assertTrue(json.loads(body)["tag_id"])

        followup_handler = self._make_handler(
            "POST",
            f"/api/candidates/{self.candidate_id}/follow-up",
            {
                "operator": "hr_ui",
                "next_follow_up_at": "2026-03-22T09:30",
                "last_contact_result": "候选人愿意沟通",
                "comment": "等对方确认面试时间",
            },
        )
        status, body = self.api.handle_request(followup_handler)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"]["current_stage"], "needs_followup")

        timeline_handler = self._make_handler("GET", f"/api/candidates/{self.candidate_id}/timeline")
        status, body = self.api.handle_request(timeline_handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        event_types = {item["event_type"] for item in items}
        self.assertIn("stage_updated", event_types)
        self.assertIn("tag_added", event_types)
        self.assertIn("follow_up_scheduled", event_types)

    def test_hr_workbench_page_requires_login(self):
        handler = self._make_handler("GET", "/hr/workbench")
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 303)
        self.assertIn("/login", headers.get("Location", ""))

    def test_hr_workbench_page_returns_html_after_login(self):
        cookie = self._login_and_get_cookie()
        handler = self._make_handler("GET", "/hr/workbench")
        handler.headers["Cookie"] = cookie
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("推荐处理台", body.decode("utf-8"))

    def test_hr_workbench_filters_invalid_extension_candidates(self):
        invalid_candidate_id = insert_candidate(
            self.task_id,
            {
                "source": "boss_extension",
                "external_id": None,
                "name": "职位管理",
                "age": None,
                "education_level": None,
                "years_experience": None,
                "current_company": None,
                "current_title": "BOSS直聘",
                "expected_salary": None,
                "location": None,
                "last_active_time": None,
                "raw_summary": "职位管理\n推荐牛人\n搜索\n沟通",
                "normalized_fields": {},
            },
        )
        upsert_extension_candidate_binding(
            candidate_id=invalid_candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=self.task_id,
            source="boss_extension_v1",
            source_candidate_key="bad-shell",
            external_id=None,
            page_url="https://www.zhipin.com/web/chat/recommend",
            latest_text_hash="bad-shell-hash",
        )

        handler = self._make_handler("GET", "/api/hr/workbench?limit=20")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        candidate_ids = [item["candidate_id"] for item in payload["items"]]
        self.assertIn(self.candidate_id, candidate_ids)
        self.assertNotIn(invalid_candidate_id, candidate_ids)

    def test_hr_workbench_dedupes_same_candidate_with_multiple_bindings(self):
        upsert_extension_candidate_binding(
            candidate_id=self.candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=self.task_id,
            source="boss_extension_v1",
            source_candidate_key="binding-a",
            external_id="boss-workbench-001",
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=qa",
            latest_text_hash="hash-a",
        )
        upsert_extension_candidate_binding(
            candidate_id=self.candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=self.task_id,
            source="boss_extension_v1",
            source_candidate_key="binding-b",
            external_id="boss-workbench-001",
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=qa",
            latest_text_hash="hash-b",
        )

        handler = self._make_handler("GET", "/api/hr/workbench?limit=20")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        candidate_ids = [item["candidate_id"] for item in payload["items"]]
        self.assertEqual(candidate_ids.count(self.candidate_id), 1)

    def test_hr_workbench_dedupes_duplicate_extension_candidates_and_keeps_manual_state(self):
        primary_candidate_id = insert_candidate(
            self.task_id,
            {
                "source": "boss_extension",
                "external_id": None,
                "name": "付伟",
                "age": 34,
                "education_level": "本科",
                "years_experience": 8,
                "current_company": None,
                "current_title": "推荐牛人",
                "expected_salary": "面议",
                "location": "北京",
                "last_active_time": None,
                "raw_summary": (
                    "付伟\n面议\n付伟\n34岁 6年 本科 离职-随时到岗\n"
                    "最近关注\n北京 测试工程师\n优势\n熟悉使用Xmind、禅道、Linux、Selenium、Appium。\n"
                    "继续沟通\n经历概览\n收藏\n举报\n转发牛人"
                ),
                "normalized_fields": {},
            },
        )
        duplicate_candidate_id = insert_candidate(
            self.task_id,
            {
                "source": "boss_extension",
                "external_id": None,
                "name": "付伟",
                "age": 34,
                "education_level": "本科",
                "years_experience": 6,
                "current_company": None,
                "current_title": "推荐牛人",
                "expected_salary": "面议",
                "location": "北京",
                "last_active_time": None,
                "raw_summary": (
                    "付伟\n面议\n付伟\n34岁 6年 本科 离职-随时到岗\n"
                    "最近关注\n北京 测试工程师\n优势\n熟悉使用Xmind、禅道、Linux、Selenium、Appium。\n"
                    "打招呼\n经历概览\n经历概览\n小米科技有限责任公司\n2024.10 - 2026.01"
                ),
                "normalized_fields": {},
            },
        )
        insert_score(
            primary_candidate_id,
            "qa_test_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"core": 55},
                "total_score": 73.9,
                "decision": "review",
                "review_reasons": ["需要人工复核"],
            },
        )
        insert_score(
            duplicate_candidate_id,
            "qa_test_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"core": 62},
                "total_score": 81.9,
                "decision": "recommend",
                "review_reasons": ["建议沟通"],
            },
        )
        upsert_candidate_pipeline_state(
            primary_candidate_id,
            current_stage="contacted",
            owner="hr_1",
            manual_stage_locked=True,
            last_contact_result="已沟通",
        )
        upsert_candidate_pipeline_state(
            duplicate_candidate_id,
            current_stage="scored",
            owner=None,
            manual_stage_locked=False,
        )
        upsert_extension_candidate_binding(
            candidate_id=primary_candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=self.task_id,
            source="boss_extension_v1",
            source_candidate_key="dup-a",
            external_id=None,
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=dup",
            latest_text_hash="dup-a",
        )
        upsert_extension_candidate_binding(
            candidate_id=duplicate_candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=self.task_id,
            source="boss_extension_v1",
            source_candidate_key="dup-b",
            external_id=None,
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=dup",
            latest_text_hash="dup-b",
        )

        handler = self._make_handler("GET", "/api/hr/workbench?source=boss_extension&limit=20")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        items = [item for item in payload["items"] if item["name"] == "付伟"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["candidate_id"], primary_candidate_id)
        self.assertTrue(items[0]["pipeline_state"]["manual_stage_locked"])

    def test_hr_workbench_dedupes_cross_job_extension_candidates_and_keeps_latest_job(self):
        older_task_id = create_task(
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "extension_inbox",
                "sort_by": "manual",
                "max_candidates": 10,
                "max_pages": 1,
                "search_config": {"source": "boss_extension"},
                "require_hr_confirmation": False,
            }
        )
        latest_task_id = create_task(
            {
                "job_id": "py_dev_engineer_v1",
                "search_mode": "extension_inbox",
                "sort_by": "manual",
                "max_candidates": 10,
                "max_pages": 1,
                "search_config": {"source": "boss_extension"},
                "require_hr_confirmation": False,
            }
        )
        raw_summary = (
            "李元龙\n13-14K\n李元龙\n26岁 6年 本科 离职-随时到岗\n"
            "最近关注\n北京 测试工程师\n优势\n熟悉 Postman、Pytest、Charles、ADB。\n"
            "继续沟通\n经历概览\n收藏\n举报\n转发牛人"
        )
        older_candidate_id = insert_candidate(
            older_task_id,
            {
                "source": "boss_extension",
                "external_id": None,
                "name": "李元龙",
                "age": 26,
                "education_level": "本科",
                "years_experience": 6,
                "current_company": None,
                "current_title": "推荐牛人",
                "expected_salary": "14K",
                "location": "北京",
                "last_active_time": None,
                "raw_summary": raw_summary,
                "normalized_fields": {},
            },
        )
        latest_candidate_id = insert_candidate(
            latest_task_id,
            {
                "source": "boss_extension",
                "external_id": None,
                "name": "李元龙",
                "age": 26,
                "education_level": "本科",
                "years_experience": 6,
                "current_company": None,
                "current_title": "推荐牛人",
                "expected_salary": "14K",
                "location": "北京",
                "last_active_time": None,
                "raw_summary": raw_summary,
                "normalized_fields": {},
            },
        )
        insert_score(
            older_candidate_id,
            "qa_test_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"core": 88.46},
                "total_score": 88.46,
                "decision": "recommend",
                "review_reasons": [],
            },
        )
        insert_score(
            latest_candidate_id,
            "py_dev_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"core": 85.86},
                "total_score": 85.86,
                "decision": "recommend",
                "review_reasons": [],
            },
        )
        upsert_candidate_pipeline_state(
            older_candidate_id,
            current_stage="scored",
            final_decision="recommend",
            manual_stage_locked=False,
        )
        upsert_candidate_pipeline_state(
            latest_candidate_id,
            current_stage="scored",
            final_decision="recommend",
            manual_stage_locked=False,
        )
        upsert_extension_candidate_binding(
            candidate_id=older_candidate_id,
            job_id="qa_test_engineer_v1",
            task_id=older_task_id,
            source="boss_extension_v1",
            source_candidate_key="same-person-key",
            external_id=None,
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=dup",
            latest_text_hash="dup-old",
            scored=True,
        )
        upsert_extension_candidate_binding(
            candidate_id=latest_candidate_id,
            job_id="py_dev_engineer_v1",
            task_id=latest_task_id,
            source="boss_extension_v1",
            source_candidate_key="same-person-key",
            external_id=None,
            page_url="https://www.zhipin.com/web/frame/recommend/?jobid=dup",
            latest_text_hash="dup-new",
            scored=True,
        )
        with db.connect() as conn:
            conn.execute(
                """
                update extension_candidate_bindings
                set last_seen_at = ?, last_scored_at = ?, updated_at = ?
                where candidate_id = ?
                """,
                ("2026-03-22 15:12:00", "2026-03-22 15:12:00", "2026-03-22 15:12:00", older_candidate_id),
            )
            conn.execute(
                """
                update extension_candidate_bindings
                set last_seen_at = ?, last_scored_at = ?, updated_at = ?
                where candidate_id = ?
                """,
                ("2026-03-22 15:13:00", "2026-03-22 15:13:00", "2026-03-22 15:13:00", latest_candidate_id),
            )
            conn.execute(
                """
                update candidate_pipeline_state
                set updated_at = ?
                where candidate_id = ?
                """,
                ("2026-03-22 15:12:00", older_candidate_id),
            )
            conn.execute(
                """
                update candidate_pipeline_state
                set updated_at = ?
                where candidate_id = ?
                """,
                ("2026-03-22 15:13:00", latest_candidate_id),
            )

        handler = self._make_handler("GET", "/api/hr/workbench?source=boss_extension&limit=20")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        items = [item for item in payload["items"] if item["name"] == "李元龙"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["candidate_id"], latest_candidate_id)
        self.assertEqual(items[0]["job_id"], "py_dev_engineer_v1")
        self.assertEqual(items[0]["extension_source_candidate_key"], "same-person-key")
