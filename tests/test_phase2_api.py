import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.screening import db
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


class Phase2ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_env = {key: os.environ.get(key) for key in [
            "SCREENING_SEARCH_QDRANT_PATH",
            "SCREENING_SEARCH_QDRANT_URL",
            "SCREENING_SEARCH_EMBEDDING_PROVIDER",
            "SCREENING_SEARCH_SYNC_EXPLAIN",
        ]}
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

    def _login_cookie(self) -> str:
        handler = self._make_handler("POST", "/api/login", {"username": "admin", "password": "admin"})
        result = self.api.handle_request(handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_generate_save_and_open_phase2_page(self):
        generate_handler = self._make_handler(
            "POST",
            "/api/v2/scorecards/generate",
            {
                "jd_text": "Python开发工程师，北京，本科，3年以上，22-35岁，熟悉 Python、Linux、Redis，Kafka 优先",
                "name": "后端初筛",
            },
        )
        status, body = self.api.handle_request(generate_handler)
        self.assertEqual(status, 200)
        generated = json.loads(body)
        self.assertEqual(generated["scorecard"]["filters"]["location"], "北京")
        self.assertEqual(generated["scorecard"]["filters"]["education_min"], "本科")
        self.assertEqual(generated["scorecard"]["filters"]["age_min"], 22.0)
        self.assertEqual(generated["scorecard"]["filters"]["age_max"], 35.0)
        self.assertTrue(generated["scorecard"]["hard_filters"]["enforce_age"])
        self.assertIn("python", [item.lower() for item in generated["scorecard"]["must_have"]])

        save_handler = self._make_handler(
            "POST",
            "/api/v2/scorecards",
            {
                "name": "后端初筛",
                "created_by": "tester",
                "scorecard": generated["scorecard"],
            },
        )
        status, body = self.api.handle_request(save_handler)
        self.assertEqual(status, 200)
        saved = json.loads(body)["item"]
        self.assertTrue(saved["id"])

        list_handler = self._make_handler("GET", "/api/v2/scorecards")
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        self.assertTrue(any(item["id"] == saved["id"] and item["name"] == "后端初筛" for item in items))
        self.assertTrue(any(item["id"] == "qa_test_engineer_v1" and item["kind"] == "builtin_phase1" for item in items))

        cookie = self._login_cookie()
        page_handler = self._make_handler("GET", "/hr/phase2")
        page_handler.headers["Cookie"] = cookie
        status, body, content_type = self.api.handle_request(page_handler)
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        html = body.decode("utf-8")
        self.assertIn("HRClaw", html)
        self.assertIn("JD评分卡", html)
        self.assertIn("评分卡工作台", html)

        imports_page_handler = self._make_handler("GET", "/hr/resume-imports")
        imports_page_handler.headers["Cookie"] = cookie
        status, body, content_type = self.api.handle_request(imports_page_handler)
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        imports_html = body.decode("utf-8")
        self.assertIn("批量导入简历并打分", imports_html)
        self.assertIn("简历导入", imports_html)

    def test_import_docx_batch_scores_against_custom_scorecard(self):
        save_handler = self._make_handler(
            "POST",
            "/api/v2/scorecards",
            {
                "name": "Python开发-北京",
                "scorecard": {
                    "name": "Python开发-北京",
                    "role_title": "Python开发工程师",
                    "jd_text": "Python开发工程师，北京，本科，3年以上，熟悉 Python、Linux、Redis",
                    "filters": {"location": "北京", "years_min": 3, "education_min": "本科"},
                    "must_have": ["Python", "Linux", "Redis"],
                    "nice_to_have": ["Kafka"],
                    "exclude": [],
                    "titles": ["Python开发工程师"],
                    "industry": [],
                    "weights": {
                        "must_have": 45,
                        "nice_to_have": 10,
                        "title_match": 10,
                        "industry_match": 5,
                        "experience": 15,
                        "education": 10,
                        "location": 5,
                    },
                    "thresholds": {"recommend_min": 75, "review_min": 55},
                    "hard_filters": {
                        "enforce_years": True,
                        "enforce_education": True,
                        "enforce_location": False,
                        "strict_exclude": False,
                        "must_have_ratio_min": 0.5,
                    },
                },
            },
        )
        status, body = self.api.handle_request(save_handler)
        self.assertEqual(status, 200)
        scorecard_id = json.loads(body)["item"]["id"]

        docx_bytes = _build_docx_bytes(
            "\n".join(
                [
                    "张三",
                    "现居住地：北京",
                    "求职意向：Python开发工程师",
                    "4年工作经验",
                    "本科",
                    "熟悉 Python Linux Redis Kafka",
                ]
            )
        )
        import_handler = self._make_handler(
            "POST",
            "/api/v2/resume-imports",
            {
                "scorecard_id": scorecard_id,
                "batch_name": "后端首轮",
                "files": [
                    {
                        "name": "zhangsan.docx",
                        "content_base64": base64.b64encode(docx_bytes).decode("ascii"),
                    }
                ],
            },
        )
        status, body = self.api.handle_request(import_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["batch"]["recommend_count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["decision"], "recommend")
        self.assertEqual(result["extracted_name"], "张三")
        self.assertTrue(result["resume_profile_id"].startswith("resume_import:"))
        self.assertIn("Python", result["matched_terms"])

        detail_handler = self._make_handler("GET", f"/api/v2/resume-imports/{payload['batch']['id']}")
        status, body = self.api.handle_request(detail_handler)
        self.assertEqual(status, 200)
        detail = json.loads(body)
        self.assertEqual(detail["batch"]["batch_name"], "后端首轮")
        self.assertEqual(detail["results"][0]["decision"], "recommend")

        profile_handler = self._make_handler(
            "GET",
            f"/api/v3/candidates/{result['resume_profile_id']}/search-profile",
        )
        status, body = self.api.handle_request(profile_handler)
        self.assertEqual(status, 200)
        profile = json.loads(body)
        self.assertEqual(profile["name"], "张三")
        self.assertEqual(profile["source"], "resume_import")

    def test_import_scanned_pdf_uses_paddleocr_fallback(self):
        save_handler = self._make_handler(
            "POST",
            "/api/v2/scorecards",
            {
                "name": "OCR测试卡",
                "scorecard": {
                    "name": "OCR测试卡",
                    "role_title": "测试工程师",
                    "jd_text": "测试工程师，北京，本科，3年以上，熟悉 测试 Linux",
                    "filters": {"location": "北京", "years_min": 3, "education_min": "本科"},
                    "must_have": ["测试", "Linux"],
                    "nice_to_have": [],
                    "exclude": [],
                    "titles": ["测试工程师"],
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
            },
        )
        status, body = self.api.handle_request(save_handler)
        self.assertEqual(status, 200)
        scorecard_id = json.loads(body)["item"]["id"]

        class _FakePage:
            def extract_text(self):
                return ""

        class _FakePdfReader:
            def __init__(self, *_args, **_kwargs):
                self.pages = [_FakePage()]

        class _FakePaddleOCR:
            def __init__(self, **_kwargs):
                self.kwargs = _kwargs

            def predict(self, *, input):
                self.last_input = input
                return [
                    {
                        "pages": [
                            {
                                "rec_text": [
                                    "李四",
                                    "现居住地：北京",
                                    "求职意向：测试工程师",
                                    "4年工作经验",
                                    "本科",
                                    "熟悉 Linux 测试 自动化",
                                ]
                            }
                        ]
                    }
                ]

        fake_module = type("FakePaddleModule", (), {"PaddleOCR": _FakePaddleOCR})()
        pdf_bytes = b"%PDF-1.4 fake scanned pdf"

        with mock.patch("src.screening.phase2_imports.PdfReader", _FakePdfReader):
            with mock.patch("src.screening.phase2_imports.importlib.import_module", return_value=fake_module):
                import_handler = self._make_handler(
                    "POST",
                    "/api/v2/resume-imports",
                    {
                        "scorecard_id": scorecard_id,
                        "batch_name": "OCR批次",
                        "files": [
                            {
                                "name": "lisi.pdf",
                                "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                            }
                        ],
                    },
                )
                status, body = self.api.handle_request(import_handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["results"][0]["decision"], "recommend")
        self.assertEqual(payload["results"][0]["extracted_name"], "李四")
        self.assertIn("Linux", payload["results"][0]["matched_terms"])

    def test_resume_import_rejects_builtin_phase1_scorecard(self):
        import_handler = self._make_handler(
            "POST",
            "/api/v2/resume-imports",
            {
                "scorecard_id": "qa_test_engineer_v1",
                "batch_name": "非法导入",
                "files": [
                    {
                        "name": "zhangsan.docx",
                        "content_base64": base64.b64encode(_build_docx_bytes("张三\n本科\n3年测试经验")).decode("ascii"),
                    }
                ],
            },
        )
        status, body = self.api.handle_request(import_handler)
        self.assertEqual(status, 400)
        self.assertIn("不支持批量导入", json.loads(body)["error"])
