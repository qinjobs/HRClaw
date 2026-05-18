import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.db import connect
from src.screening.email_resume_ingest.scanner import EmailResumeScanner
from src.screening.email_resume_ingest.service import EmailResumeIngestService
from src.screening.hr_users import create_hr_user
from src.screening.jd_scorecard_repositories import upsert_jd_scorecard
from src.screening.search_service import ResumeSearchService


def _build_docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                + "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
                + "</w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def _build_scorecard_payload(scorecard_id: str) -> dict:
    return {
        "id": scorecard_id,
        "name": "邮箱采集测试评分卡",
        "jd_text": "Python开发工程师，熟悉 Python",
        "scorecard": {
            "name": "邮箱采集测试评分卡",
            "schema_version": "phase2_scorecard_v1",
            "role_title": "Python开发工程师",
            "jd_text": "Python开发工程师，熟悉 Python",
            "filters": {
                "location": None,
                "years_min": None,
                "age_min": None,
                "age_max": None,
                "education_min": None,
            },
            "must_have": ["Python"],
            "nice_to_have": [],
            "exclude": [],
            "titles": ["Python开发工程师"],
            "industry": [],
            "weights": {
                "must_have": 100.0,
                "nice_to_have": 0.0,
                "title_match": 0.0,
                "industry_match": 0.0,
                "experience": 0.0,
                "education": 0.0,
                "location": 0.0,
            },
            "thresholds": {
                "recommend_min": 60.0,
                "review_min": 30.0,
            },
            "hard_filters": {
                "enforce_years": False,
                "enforce_age": False,
                "enforce_education": False,
                "enforce_location": False,
                "strict_exclude": False,
                "must_have_ratio_min": 0.0,
            },
        },
        "scorecard_kind": "custom_phase2",
        "engine_type": "generic_resume_match",
        "schema_version": "phase2_scorecard_v1",
        "supports_resume_import": True,
        "editable": True,
        "system_managed": False,
        "active": True,
        "created_by": "tests",
    }


class EmailResumeIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.email_root = Path(self.tmpdir.name) / "email"
        self.email_root.mkdir(parents=True, exist_ok=True)
        self._previous_env = {
            "SCREENING_EMAIL_RESUME_ROOT": os.environ.get("SCREENING_EMAIL_RESUME_ROOT"),
            "SCREENING_SEARCH_QDRANT_PATH": os.environ.get("SCREENING_SEARCH_QDRANT_PATH"),
            "SCREENING_SEARCH_QDRANT_URL": os.environ.get("SCREENING_SEARCH_QDRANT_URL"),
            "SCREENING_SEARCH_EMBEDDING_PROVIDER": os.environ.get("SCREENING_SEARCH_EMBEDDING_PROVIDER"),
            "SCREENING_SEARCH_SYNC_EXPLAIN": os.environ.get("SCREENING_SEARCH_SYNC_EXPLAIN"),
        }
        os.environ["SCREENING_EMAIL_RESUME_ROOT"] = str(self.email_root)
        os.environ["SCREENING_SEARCH_QDRANT_PATH"] = str(Path(self.tmpdir.name) / "qdrant")
        os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = "hash"
        os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = "1"

        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        self.api = api
        self.api.init_db()
        if hasattr(self.api.SEARCH_SERVICE, "close"):
            self.api.SEARCH_SERVICE.close()
        self.api.SEARCH_SERVICE = ResumeSearchService()
        self.api._AUTH_SESSIONS.clear()

        scorecard = upsert_jd_scorecard(_build_scorecard_payload("email_ingest_python_test"))
        self.scorecard_id = str(scorecard["id"])
        self.user = create_hr_user(
            username="hr.email",
            password="secret123",
            display_name="邮箱采集HR",
            role="hr",
            active=True,
            default_scorecard_id=self.scorecard_id,
            email_ingest_enabled=True,
            email_ingest_interval_minutes=30,
            notes="",
            operator="tests",
        )
        user_root = self.email_root / str(self.user["id"]) / "20260423"
        user_root.mkdir(parents=True, exist_ok=True)
        (user_root / "candidate.docx").write_bytes(
            _build_docx_bytes(
                "\n".join(
                    [
                        "姓名：张三",
                        "Python开发工程师",
                        "5年工作经验",
                        "熟悉 Python、FastAPI、Linux",
                    ]
                )
            )
        )

    def tearDown(self):
        if hasattr(self.api.SEARCH_SERVICE, "close"):
            self.api.SEARCH_SERVICE.close()
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _make_handler(self, method: str, path: str, payload: dict | None = None):
        raw = json.dumps(payload or {}).encode("utf-8")
        handler = type("Handler", (), {})()
        handler.command = method
        handler.headers = {"Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = mock.Mock()
        handler.rfile.read = mock.Mock(return_value=raw)
        return handler

    def _login_cookie(self, username: str, password: str) -> str:
        handler = self._make_handler("POST", "/api/login", {"username": username, "password": password})
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_service_run_once_reuses_existing_pipeline_and_dedups(self):
        service = EmailResumeIngestService(
            scanner=EmailResumeScanner(root_dir=self.email_root),
            search_service=self.api.SEARCH_SERVICE,
        )

        summary1 = service.run_once(user_id=str(self.user["id"]), trigger="unit")
        self.assertTrue(summary1["ok"])
        self.assertEqual(summary1["processed_files"], 1)
        self.assertEqual(summary1["failed_count"], 0)
        self.assertEqual(summary1["source"], "email_import")
        self.assertEqual(summary1["scorecard_id"], self.scorecard_id)
        self.assertEqual(summary1["recommend_count"] + summary1["review_count"] + summary1["reject_count"], 1)
        self.assertEqual(len(summary1["results"]), 1)

        with connect() as conn:
            rows = conn.execute(
                "select status, source, decision from email_resume_ingest_records where user_id = ?",
                (str(self.user["id"]),),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(dict(rows[0])["status"], "completed")
        self.assertEqual(dict(rows[0])["source"], "email_import")

        summary2 = service.run_once(user_id=str(self.user["id"]), trigger="unit")
        self.assertTrue(summary2["ok"])
        self.assertEqual(summary2["processed_files"], 0)
        self.assertEqual(summary2["duplicate_files"], 1)
        self.assertEqual(summary2["new_files"], 0)

    def test_api_run_once_records_and_retry_failed(self):
        admin_cookie = self._login_cookie("admin", "admin")

        run_handler = self._make_handler(
            "POST",
            "/api/email-ingest/run-once",
            {"user_id": str(self.user["id"]), "trigger": "api_test"},
        )
        run_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(run_handler)
        self.assertEqual(status, 200)
        result = json.loads(body)["result"]
        self.assertEqual(result["processed_files"], 1)
        self.assertEqual(result["source"], "email_import")
        self.assertTrue(str(result.get("scan_directory") or "").endswith(str(self.user["id"])))

        records_handler = self._make_handler(
            "GET",
            f"/api/email-ingest/records?user_id={self.user['id']}&limit=20",
        )
        records_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(records_handler)
        self.assertEqual(status, 200)
        records = json.loads(body)["items"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["source"], "email_import")
        record_id = str(records[0]["id"])

        file_handler = self._make_handler(
            "GET",
            f"/api/email-ingest/records/{record_id}/file",
        )
        file_handler.headers["Cookie"] = admin_cookie
        file_result = self.api.handle_request(file_handler)
        self.assertIn(len(file_result), (3, 4))
        self.assertEqual(file_result[0], 200)
        self.assertTrue(len(file_result[1]) > 0)

        retry_handler = self._make_handler(
            "POST",
            "/api/email-ingest/retry-failed",
            {"user_id": str(self.user["id"]), "limit": 10, "max_retry": 3},
        )
        retry_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(retry_handler)
        self.assertEqual(status, 200)
        retry_payload = json.loads(body)
        self.assertEqual(retry_payload["retried"], 0)
        self.assertEqual(retry_payload["failed"], 0)

    def test_hr_user_cannot_query_other_user_records(self):
        other_user = create_hr_user(
            username="hr.other",
            password="secret123",
            display_name="其他HR",
            role="hr",
            active=True,
            default_scorecard_id=self.scorecard_id,
            email_ingest_enabled=True,
            email_ingest_interval_minutes=60,
            notes="",
            operator="tests",
        )
        hr_cookie = self._login_cookie("hr.email", "secret123")
        records_handler = self._make_handler(
            "GET",
            f"/api/email-ingest/records?user_id={other_user['id']}",
        )
        records_handler.headers["Cookie"] = hr_cookie
        status, _body = self.api.handle_request(records_handler)
        self.assertEqual(status, 403)

    def test_hr_user_can_update_own_email_ingest_config(self):
        hr_cookie = self._login_cookie("hr.email", "secret123")
        ingest_directory = str(self.email_root / "custom_ingest" / "{user_id}")
        config_handler = self._make_handler(
            "POST",
            f"/api/email-ingest/users/{self.user['id']}/config",
            {
                "default_scorecard_id": self.scorecard_id,
                "email_ingest_enabled": True,
                "email_ingest_interval_minutes": 15,
                "email_ingest_directory": ingest_directory,
            },
        )
        config_handler.headers["Cookie"] = hr_cookie
        status, body = self.api.handle_request(config_handler)
        self.assertEqual(status, 200)
        user = json.loads(body)["user"]
        self.assertEqual(user["default_scorecard_id"], self.scorecard_id)
        self.assertTrue(user["email_ingest_enabled"])
        self.assertEqual(user["email_ingest_interval_minutes"], 15)
        self.assertEqual(user["email_ingest_source"], "email_import")
        self.assertEqual(user["email_ingest_directory"], ingest_directory)

    def test_api_run_once_supports_ingest_directory_override(self):
        admin_cookie = self._login_cookie("admin", "admin")
        custom_user = create_hr_user(
            username="hr.ingest.override",
            password="secret123",
            display_name="覆盖目录测试",
            role="hr",
            active=True,
            default_scorecard_id=self.scorecard_id,
            email_ingest_enabled=True,
            email_ingest_interval_minutes=30,
            notes="",
            operator="tests",
        )
        custom_date_dir = self.email_root / "manual_override" / "20260423"
        custom_date_dir.mkdir(parents=True, exist_ok=True)
        (custom_date_dir / "manual-override.docx").write_bytes(
            _build_docx_bytes(
                "\n".join(
                    [
                        "姓名：李四",
                        "Python开发工程师",
                        "4年工作经验",
                        "熟悉 Python、接口测试、Linux",
                    ]
                )
            )
        )
        run_handler = self._make_handler(
            "POST",
            "/api/email-ingest/run-once",
            {
                "user_id": str(custom_user["id"]),
                "trigger": "manual_override",
                "ingestDirectory": str(custom_date_dir),
            },
        )
        run_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(run_handler)
        self.assertEqual(status, 200)
        result = json.loads(body)["result"]
        self.assertEqual(result["scanned_files"], 1)
        self.assertEqual(result["processed_files"], 1)
        self.assertEqual(result["source"], "email_import")
        self.assertEqual(result.get("scan_directory"), str(custom_date_dir))

    def test_service_default_scan_falls_back_to_username_directory(self):
        user = create_hr_user(
            username="hr.mail.folder",
            password="secret123",
            display_name="用户名目录测试",
            role="hr",
            active=True,
            default_scorecard_id=self.scorecard_id,
            email_ingest_enabled=True,
            email_ingest_interval_minutes=30,
            notes="",
            operator="tests",
        )
        fallback_dir = self.email_root / user["username"] / "20260423"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        (fallback_dir / "fallback-by-username.docx").write_bytes(
            _build_docx_bytes(
                "\n".join(
                    [
                        "姓名：王五",
                        "Python开发工程师",
                        "3年工作经验",
                        "熟悉 Python、SQL、Linux",
                    ]
                )
            )
        )
        service = EmailResumeIngestService(
            scanner=EmailResumeScanner(root_dir=self.email_root),
            search_service=self.api.SEARCH_SERVICE,
        )
        summary = service.run_once(user_id=str(user["id"]), trigger="username_fallback")
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["scanned_files"], 1)
        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["scan_directory"], user["username"])
        self.assertEqual(summary["source"], "email_import")

    def test_admin_create_user_can_bind_default_scorecard_and_email_config(self):
        admin_cookie = self._login_cookie("admin", "admin")
        create_handler = self._make_handler(
            "POST",
            "/api/hr/users",
            {
                "username": "hr.bind",
                "password": "secret123",
                "display_name": "绑定测试",
                "role": "hr",
                "active": True,
                "default_scorecard_id": self.scorecard_id,
                "email_ingest_enabled": True,
                "email_ingest_interval_minutes": 45,
                "email_ingest_directory": "/data/email/{user_id}",
            },
        )
        create_handler.headers["Cookie"] = admin_cookie
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        user = json.loads(body)["user"]
        self.assertEqual(user["default_scorecard_id"], self.scorecard_id)
        self.assertTrue(user["email_ingest_enabled"])
        self.assertEqual(user["email_ingest_interval_minutes"], 45)
        self.assertEqual(user["email_ingest_source"], "email_import")
        self.assertEqual(user["email_ingest_directory"], "/data/email/{user_id}")
