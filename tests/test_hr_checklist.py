import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.repositories import (
    add_review_action,
    create_task,
    insert_candidate,
    insert_candidate_action,
    insert_score,
    insert_snapshot,
)


class HrChecklistApiTests(unittest.TestCase):
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
                "search_mode": "deep_search",
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
                "external_id": "boss-123",
                "name": "候选人A",
                "age": 28,
                "education_level": "本科",
                "years_experience": 5,
                "current_company": "Demo Co",
                "current_title": "测试工程师",
                "expected_salary": "15K",
                "location": "北京",
                "last_active_time": "刚刚活跃",
                "raw_summary": "demo",
                "normalized_fields": {"testing_evidence": True},
            },
        )
        screenshot_path = Path(self.tmpdir.name) / "shot.png"
        screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        insert_snapshot(
            self.candidate_id,
            "candidate_detail",
            str(screenshot_path),
            "snapshot text",
            {"gpt_extraction_used": False, "gpt_extraction_error": "insufficient_quota"},
        )
        insert_score(
            self.candidate_id,
            "qa_test_engineer_v1",
            {
                "hard_filter_pass": True,
                "hard_filter_fail_reasons": [],
                "dimension_scores": {"a": 60},
                "total_score": 60.0,
                "decision": "review",
                "review_reasons": ["manual"],
            },
        )
        add_review_action(
            self.candidate_id,
            "hr_1",
            "mark_reviewed",
            "ok",
            "keep_in_pool",
        )
        insert_candidate_action(
            self.candidate_id,
            "send_greeting",
            "success",
            {"reason": "test"},
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

    def test_hr_checklist_api_returns_rows(self):
        handler = self._make_handler("GET", f"/api/hr/checklist?task_id={self.task_id}&limit=10")
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 2)
        status, body = result
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["tasks"])
        self.assertEqual(payload["items"][0]["candidate_id"], self.candidate_id)
        self.assertEqual(payload["items"][0]["gpt_extraction_used"], False)
        self.assertIn("quota", payload["items"][0]["gpt_extraction_error"])
        self.assertEqual(payload["items"][0]["greet_status"], "success")

    def test_candidate_screenshot_route_returns_binary(self):
        handler = self._make_handler("GET", f"/api/candidates/{self.candidate_id}/screenshot")
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("image/png", content_type)
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_hr_checklist_page_route_returns_html(self):
        cookie = self._login_and_get_cookie()
        handler = self._make_handler("GET", "/hr/checklist")
        handler.headers["Cookie"] = cookie
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("HR", body.decode("utf-8"))

    def test_hr_checklist_page_redirects_without_login(self):
        handler = self._make_handler("GET", "/hr/checklist")
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 303)
        self.assertIn("/login", headers.get("Location", ""))
