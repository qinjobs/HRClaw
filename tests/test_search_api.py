import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.repositories import create_task, insert_candidate, insert_snapshot
from src.screening.search_service import ResumeSearchService, _extract_json_blob


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_sync = os.environ.get("SCREENING_SEARCH_SYNC_EXPLAIN")
        self._previous_qdrant_path = os.environ.get("SCREENING_SEARCH_QDRANT_PATH")
        self._previous_qdrant_url = os.environ.get("SCREENING_SEARCH_QDRANT_URL")
        self._previous_embedding_provider = os.environ.get("SCREENING_SEARCH_EMBEDDING_PROVIDER")
        self._previous_local_llm_enabled = os.environ.get("SCREENING_SEARCH_ENABLE_LOCAL_LLM")
        self._previous_local_llm_base_url = os.environ.get("SCREENING_SEARCH_OPENAI_BASE_URL")
        self._previous_local_llm_api_key = os.environ.get("SCREENING_SEARCH_OPENAI_API_KEY")
        self._previous_local_llm_model = os.environ.get("SCREENING_SEARCH_OPENAI_MODEL")
        os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = "1"
        os.environ["SCREENING_SEARCH_QDRANT_PATH"] = str(Path(self.tmpdir.name) / "qdrant")
        os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = "hash"
        os.environ.pop("SCREENING_SEARCH_ENABLE_LOCAL_LLM", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_BASE_URL", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_API_KEY", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_MODEL", None)
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        self.api = api
        self.api.init_db()
        self.api.SEARCH_SERVICE = ResumeSearchService()

        task_id = create_task(
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "recommend",
                "sort_by": "active",
                "max_candidates": 10,
                "max_pages": 1,
                "search_config": {"keyword": "测试工程师", "city": "北京"},
                "require_hr_confirmation": True,
            }
        )
        self.candidate_a = insert_candidate(
            task_id,
            {
                "external_id": "boss-a",
                "name": "刘青",
                "age": 27,
                "education_level": "本科",
                "major": "计算机科学与技术",
                "years_experience": 4,
                "current_company": "EduTech",
                "current_title": "测试工程师",
                "expected_salary": "18K",
                "location": "北京",
                "last_active_time": "刚刚活跃",
                "raw_summary": "4 years QA, online education, Linux, adb, Charles, API testing.",
                "normalized_fields": {
                    "testing_evidence": True,
                    "tools": ["Linux", "adb", "Charles", "MySQL"],
                    "industry_tags": ["在线教育"],
                    "frontend_backend_test": True,
                },
            },
        )
        self.candidate_b = insert_candidate(
            task_id,
            {
                "external_id": "boss-b",
                "name": "赵伟",
                "age": 25,
                "education_level": "本科",
                "major": "软件工程",
                "years_experience": 2,
                "current_company": "Demo Co",
                "current_title": "测试工程师",
                "expected_salary": "13K",
                "location": "北京",
                "last_active_time": "今天活跃",
                "raw_summary": "2 years QA, manual tests, some Charles.",
                "normalized_fields": {
                    "testing_evidence": True,
                    "tools": ["Charles"],
                    "industry_tags": [],
                },
            },
        )
        shot_path = Path(self.tmpdir.name) / "shot.png"
        shot_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        resume_path = Path(self.tmpdir.name) / "boss-a.pdf"
        resume_path.write_bytes(b"%PDF-1.4")
        insert_snapshot(
            self.candidate_a,
            "candidate_detail",
            str(shot_path),
            "负责在线教育产品功能测试、接口测试、兼容性测试，熟练使用 Linux、ADB、Charles，处理过 APP 和 Web 场景。",
            {
                "source": "test",
                "resume_path": str(resume_path),
                "resume_downloaded": True,
                "resume_filename": "boss-a.pdf",
                "detail_url": "https://www.zhipin.com/web/geek/detail/boss-a",
            },
        )
        insert_snapshot(
            self.candidate_b,
            "candidate_detail",
            str(shot_path),
            "主要做手工功能测试，少量 Charles 抓包经验，没有教育行业背景。",
            {"source": "test"},
        )

    def tearDown(self):
        close = getattr(getattr(self, "api", None), "SEARCH_SERVICE", None)
        if close is not None and hasattr(close, "close"):
            close.close()
        if self._previous_sync is None:
            os.environ.pop("SCREENING_SEARCH_SYNC_EXPLAIN", None)
        else:
            os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = self._previous_sync
        if self._previous_qdrant_path is None:
            os.environ.pop("SCREENING_SEARCH_QDRANT_PATH", None)
        else:
            os.environ["SCREENING_SEARCH_QDRANT_PATH"] = self._previous_qdrant_path
        if self._previous_qdrant_url is None:
            os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        else:
            os.environ["SCREENING_SEARCH_QDRANT_URL"] = self._previous_qdrant_url
        if self._previous_embedding_provider is None:
            os.environ.pop("SCREENING_SEARCH_EMBEDDING_PROVIDER", None)
        else:
            os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = self._previous_embedding_provider
        if self._previous_local_llm_enabled is None:
            os.environ.pop("SCREENING_SEARCH_ENABLE_LOCAL_LLM", None)
        else:
            os.environ["SCREENING_SEARCH_ENABLE_LOCAL_LLM"] = self._previous_local_llm_enabled
        if self._previous_local_llm_base_url is None:
            os.environ.pop("SCREENING_SEARCH_OPENAI_BASE_URL", None)
        else:
            os.environ["SCREENING_SEARCH_OPENAI_BASE_URL"] = self._previous_local_llm_base_url
        if self._previous_local_llm_api_key is None:
            os.environ.pop("SCREENING_SEARCH_OPENAI_API_KEY", None)
        else:
            os.environ["SCREENING_SEARCH_OPENAI_API_KEY"] = self._previous_local_llm_api_key
        if self._previous_local_llm_model is None:
            os.environ.pop("SCREENING_SEARCH_OPENAI_MODEL", None)
        else:
            os.environ["SCREENING_SEARCH_OPENAI_MODEL"] = self._previous_local_llm_model

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

    def test_search_index_upsert_and_query(self):
        upsert_handler = self._make_handler("POST", "/api/v3/search/index/upsert", {})
        status, body = self.api.handle_request(upsert_handler)
        self.assertEqual(status, 200)
        upserted = json.loads(body)
        self.assertGreaterEqual(upserted["upserted_profiles"], 2)
        self.assertGreaterEqual(upserted["upserted_chunks"], 2)

        query_handler = self._make_handler(
            "POST",
            "/api/v3/search/query",
            {
                "query_text": "找北京3年以上，做过在线教育，熟悉Linux、ADB、Charles的测试工程师",
                "filters": {"location": "北京", "years_min": 3, "education_min": "本科"},
                "top_k": 5,
                "explain": True,
            },
        )
        status, body = self.api.handle_request(query_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["results"])
        self.assertEqual(payload["results"][0]["candidate_id"], self.candidate_a)
        self.assertTrue(payload["results"][0]["matched_evidence"])
        self.assertTrue(payload["results"][0]["interview_questions"])

        run_handler = self._make_handler("GET", f"/api/v3/search/runs/{payload['search_run_id']}")
        status, body = self.api.handle_request(run_handler)
        self.assertEqual(status, 200)
        run_payload = json.loads(body)
        self.assertEqual(run_payload["status"], "completed")
        self.assertEqual(run_payload["results"][0]["candidate_id"], self.candidate_a)

    def test_rebuild_vector_store_from_existing_chunks(self):
        summary = self.api.SEARCH_SERVICE.upsert_profiles()
        self.assertGreaterEqual(summary["upserted_chunks"], 2)
        rebuild = self.api.SEARCH_SERVICE.rebuild_vector_store()
        self.assertTrue(rebuild["ok"])
        self.assertEqual(rebuild["collection"], "resume_chunks_v1")
        self.assertGreaterEqual(rebuild["points"], 2)

    def test_search_profile_route_and_page(self):
        upsert_handler = self._make_handler("POST", "/api/v3/search/index/upsert", {})
        status, _body = self.api.handle_request(upsert_handler)
        self.assertEqual(status, 200)

        profile_handler = self._make_handler("GET", f"/api/v3/candidates/{self.candidate_a}/search-profile")
        status, body = self.api.handle_request(profile_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["source_candidate_id"], self.candidate_a)
        self.assertTrue(payload["chunks"])
        self.assertIn("detail_api_path", payload["raw_resume_entry"])
        self.assertTrue(str(payload["raw_resume_entry"]["resume_path"]).endswith("boss-a.pdf"))

        cookie = self._login_cookie()
        page_handler = self._make_handler("GET", "/hr/search")
        page_handler.headers["Cookie"] = cookie
        result = self.api.handle_request(page_handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("高级搜索", body.decode("utf-8"))

    def test_remote_openai_compatible_llm_json_prefill(self):
        service = ResumeSearchService()
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": "```json\n{\"ok\": true, \"name\": \"nanbeige\"}\n```",
                        "reasoning_content": None,
                    }
                }
            ]
        }
        response_mock = mock.MagicMock()
        response_mock.read.return_value = json.dumps(response_payload).encode("utf-8")
        response_mock.__enter__.return_value = response_mock
        response_mock.__exit__.return_value = None
        with mock.patch.dict(
            os.environ,
            {
                "SCREENING_SEARCH_ENABLE_LOCAL_LLM": "1",
                "SCREENING_SEARCH_OPENAI_BASE_URL": "http://127.0.0.1:8000/v1",
                "SCREENING_SEARCH_OPENAI_API_KEY": "001122",
                "SCREENING_SEARCH_OPENAI_MODEL": "Nanbeige4.1-3B-8bit",
            },
            clear=False,
        ):
            with mock.patch("src.screening.search_service.urllib.request.urlopen", return_value=response_mock) as mocked_urlopen:
                payload = service._generate_local_llm_json(
                    system_prompt="你是一个JSON助手。",
                    user_prompt="输出一个JSON对象。",
                    max_new_tokens=128,
                    expected_type="object",
                )
        self.assertEqual(payload, {"ok": True, "name": "nanbeige"})
        request = mocked_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["messages"][-1]["role"], "assistant")
        self.assertEqual(body["messages"][-1]["content"], "{")

    def test_extract_json_blob_prefers_array_when_response_starts_with_array(self):
        payload = _extract_json_blob('[{"resume_profile_id":"abc","fit_score":91}]')
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["resume_profile_id"], "abc")

    def test_openai_compatible_llm_auto_enables_without_explicit_flag(self):
        service = ResumeSearchService()
        self.api.SEARCH_SERVICE.upsert_profiles()
        profile_rows = self.api.SEARCH_SERVICE._load_all_profiles()
        candidate_a_profile_id = next(
            profile["id"] for profile in profile_rows if profile.get("source_candidate_id") == self.candidate_a
        )
        response_payloads = [
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "must_have": ["测试", "charles"],
                                    "nice_to_have": ["在线教育"],
                                    "exclude": [],
                                    "titles": ["测试工程师"],
                                    "skills": ["charles", "linux"],
                                    "industry": ["在线教育"],
                                    "location": "北京",
                                    "years_min": 3,
                                    "education_min": "本科",
                                    "weights": {"must_have": 0.4},
                                    "query_variants": ["测试工程师 北京 charles"],
                                },
                                ensure_ascii=False,
                            ),
                            "reasoning_content": None,
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "resume_profile_id": candidate_a_profile_id,
                                        "fit_score": 92,
                                        "hard_filter_pass": True,
                                        "matched_evidence": ["在线教育测试经验", "熟悉 Linux/ADB/Charles"],
                                        "gaps": [],
                                        "risk_flags": [],
                                        "interview_questions": ["请说明在线教育项目中的测试深度。"],
                                        "final_recommendation": "recommend",
                                    }
                                ],
                                ensure_ascii=False,
                            ),
                            "reasoning_content": None,
                        }
                    }
                ]
            },
        ]

        def fake_urlopen(*_args, **_kwargs):
            response_payload = response_payloads.pop(0)
            response_mock = mock.MagicMock()
            response_mock.read.return_value = json.dumps(response_payload).encode("utf-8")
            response_mock.__enter__.return_value = response_mock
            response_mock.__exit__.return_value = None
            return response_mock

        with mock.patch.dict(
            os.environ,
            {
                "SCREENING_SEARCH_OPENAI_BASE_URL": "http://127.0.0.1:8000/v1",
                "SCREENING_SEARCH_OPENAI_API_KEY": "001122",
                "SCREENING_SEARCH_OPENAI_MODEL": "Nanbeige4.1-3B-8bit",
            },
            clear=False,
        ):
            with mock.patch("src.screening.search_service.urllib.request.urlopen", side_effect=fake_urlopen):
                result = self.api.SEARCH_SERVICE.search(
                    jd_text=None,
                    query_text="找北京 3 年以上 在线教育测试工程师，熟悉 Charles",
                    filters={"location": "北京", "years_min": 3, "education_min": "本科"},
                    top_k=5,
                    explain=True,
                )
        run = self.api.SEARCH_SERVICE.get_search_run(result["search_run_id"])
        self.assertEqual(run["model_summary"]["provider"], "openai_compatible")
        self.assertEqual(run["model_summary"]["model"], "Nanbeige4.1-3B-8bit")
        self.assertNotIn("intent_rule_parser", run["degraded"])
        self.assertNotIn("nanbeige_unavailable", run["degraded"])
        self.assertEqual(run["results"][0]["explanation_status"], "completed")
