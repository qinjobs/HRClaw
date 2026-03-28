import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.gpt54_adapter import MockBrowserAgent
from src.screening.orchestrator import ScreeningOrchestrator
from src.screening.pipeline_service import CollectionPipelineService
from src.screening.search_service import ResumeSearchService


class HrUsersApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_qdrant_path = os.environ.get("SCREENING_SEARCH_QDRANT_PATH")
        self._previous_qdrant_url = os.environ.get("SCREENING_SEARCH_QDRANT_URL")
        self._previous_sync = os.environ.get("SCREENING_SEARCH_SYNC_EXPLAIN")
        self._previous_embedding_provider = os.environ.get("SCREENING_SEARCH_EMBEDDING_PROVIDER")
        os.environ["SCREENING_SEARCH_QDRANT_PATH"] = str(Path(self.tmpdir.name) / "qdrant")
        os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = "1"
        os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = "hash"

        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        self.api = api
        self.api.init_db()
        self.api.SEARCH_SERVICE = ResumeSearchService()
        self.api.ORCHESTRATOR = ScreeningOrchestrator(
            browser_agent=MockBrowserAgent(),
            search_service=self.api.SEARCH_SERVICE,
        )
        self.api.PIPELINE_SERVICE = CollectionPipelineService(
            orchestrator=ScreeningOrchestrator(
                browser_agent=MockBrowserAgent(),
                search_service=self.api.SEARCH_SERVICE,
            ),
            search_service=self.api.SEARCH_SERVICE,
        )

    def tearDown(self):
        close = getattr(getattr(self, "api", None), "SEARCH_SERVICE", None)
        if close is not None and hasattr(close, "close"):
            close.close()
        if self._previous_qdrant_path is None:
            os.environ.pop("SCREENING_SEARCH_QDRANT_PATH", None)
        else:
            os.environ["SCREENING_SEARCH_QDRANT_PATH"] = self._previous_qdrant_path
        if self._previous_qdrant_url is None:
            os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        else:
            os.environ["SCREENING_SEARCH_QDRANT_URL"] = self._previous_qdrant_url
        if self._previous_sync is None:
            os.environ.pop("SCREENING_SEARCH_SYNC_EXPLAIN", None)
        else:
            os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = self._previous_sync
        if self._previous_embedding_provider is None:
            os.environ.pop("SCREENING_SEARCH_EMBEDDING_PROVIDER", None)
        else:
            os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = self._previous_embedding_provider

    def _make_handler(self, method: str, path: str, payload: dict | None = None):
        raw = json.dumps(payload or {}).encode("utf-8")
        handler = type("Handler", (), {})()
        handler.command = method
        handler.headers = {"Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = mock.Mock()
        handler.rfile.read = mock.Mock(return_value=raw)
        return handler

    def _login_cookie(self, username: str = "admin", password: str = "admin") -> str:
        handler = self._make_handler("POST", "/api/login", {"username": username, "password": password})
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_admin_can_create_and_list_users(self):
        cookie = self._login_cookie()

        list_handler = self._make_handler("GET", "/api/hr/users")
        list_handler.headers["Cookie"] = cookie
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(any(item["username"] == "admin" for item in payload["items"]))

        create_handler = self._make_handler(
            "POST",
            "/api/hr/users",
            {
                "username": "hr.zhang",
                "display_name": "张三",
                "password": "secret123",
                "role": "hr",
                "notes": "招聘专员",
            },
        )
        create_handler.headers["Cookie"] = cookie
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        created = json.loads(body)["user"]
        self.assertEqual(created["username"], "hr.zhang")
        self.assertTrue(created["active"])

        list_handler = self._make_handler("GET", "/api/hr/users")
        list_handler.headers["Cookie"] = cookie
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(any(item["username"] == "hr.zhang" for item in payload["items"]))

    def test_hr_user_cannot_access_user_management(self):
        admin_cookie = self._login_cookie()
        create_handler = self._make_handler(
            "POST",
            "/api/hr/users",
            {
                "username": "hr.li",
                "display_name": "李四",
                "password": "secret123",
                "role": "hr",
            },
        )
        create_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)

        hr_cookie = self._login_cookie("hr.li", "secret123")

        list_handler = self._make_handler("GET", "/api/hr/users")
        list_handler.headers["Cookie"] = hr_cookie
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 403)
        self.assertIn("管理员", json.loads(body)["error"])

        page_handler = self._make_handler("GET", "/hr/users")
        page_handler.headers["Cookie"] = hr_cookie
        result = self.api.handle_request(page_handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 403)
        self.assertIn("text/html", content_type)
        self.assertIn("用户管理", body.decode("utf-8"))

    def test_disabled_user_cannot_login(self):
        admin_cookie = self._login_cookie()
        create_handler = self._make_handler(
            "POST",
            "/api/hr/users",
            {
                "username": "hr.wang",
                "display_name": "王五",
                "password": "secret123",
                "role": "hr",
            },
        )
        create_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        user_id = json.loads(body)["user"]["id"]

        update_handler = self._make_handler(
            "POST",
            f"/api/hr/users/{user_id}",
            {
                "display_name": "王五",
                "role": "hr",
                "active": False,
                "notes": "已停用",
            },
        )
        update_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(update_handler)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["user"]["active"])

        login_handler = self._make_handler("POST", "/api/login", {"username": "hr.wang", "password": "secret123"})
        status, body = self.api.handle_request(login_handler)
        self.assertEqual(status, 401)
        self.assertIn("停用", json.loads(body)["error"])

    def test_last_admin_cannot_be_disabled(self):
        cookie = self._login_cookie()
        list_handler = self._make_handler("GET", "/api/hr/users")
        list_handler.headers["Cookie"] = cookie
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        admin_id = next(item["id"] for item in json.loads(body)["items"] if item["username"] == "admin")

        update_handler = self._make_handler(
            "POST",
            f"/api/hr/users/{admin_id}",
            {
                "display_name": "admin",
                "role": "admin",
                "active": False,
                "notes": "",
            },
        )
        update_handler.headers["Cookie"] = cookie
        status, body = self.api.handle_request(update_handler)
        self.assertEqual(status, 400)
        self.assertIn("管理员", json.loads(body)["error"])
