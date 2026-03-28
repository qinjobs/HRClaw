import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.gpt54_adapter import MockBrowserAgent
from src.screening.orchestrator import ScreeningOrchestrator
from src.screening.repositories import add_log


class LogApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        self.api = api
        self.api.init_db()
        self.api.ORCHESTRATOR = ScreeningOrchestrator(browser_agent=MockBrowserAgent())

    def _make_handler(self, method: str, path: str, payload: dict | None = None):
        raw = json.dumps(payload or {}).encode("utf-8")
        handler = type("Handler", (), {})()
        handler.command = method
        handler.headers = {"Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = mock.Mock()
        handler.rfile.read = mock.Mock(return_value=raw)
        return handler

    def test_task_logs_route(self):
        create_handler = self._make_handler(
            "POST",
            "/api/tasks",
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "deep_search",
                "sort_by": "active",
                "max_candidates": 1,
            },
        )
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        task_id = json.loads(body)["task_id"]
        add_log(task_id, "info", "probe", {"step": "ready"})

        logs_handler = self._make_handler("GET", f"/api/tasks/{task_id}/logs")
        status, body = self.api.handle_request(logs_handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        self.assertEqual(items[0]["event_type"], "probe")
        self.assertEqual(items[0]["payload"]["step"], "ready")
