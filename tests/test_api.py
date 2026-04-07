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
from src.screening.phase2_repositories import upsert_custom_scorecard
from src.screening.search_service import ResumeSearchService


class ApiFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_qdrant_path = os.environ.get("SCREENING_SEARCH_QDRANT_PATH")
        self._previous_qdrant_url = os.environ.get("SCREENING_SEARCH_QDRANT_URL")
        self._previous_sync = os.environ.get("SCREENING_SEARCH_SYNC_EXPLAIN")
        self._previous_embedding_provider = os.environ.get("SCREENING_SEARCH_EMBEDDING_PROVIDER")
        self._previous_local_llm_enabled = os.environ.get("SCREENING_SEARCH_ENABLE_LOCAL_LLM")
        self._previous_local_llm_base_url = os.environ.get("SCREENING_SEARCH_OPENAI_BASE_URL")
        self._previous_local_llm_api_key = os.environ.get("SCREENING_SEARCH_OPENAI_API_KEY")
        self._previous_local_llm_model = os.environ.get("SCREENING_SEARCH_OPENAI_MODEL")
        os.environ["SCREENING_SEARCH_QDRANT_PATH"] = str(Path(self.tmpdir.name) / "qdrant")
        os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        os.environ["SCREENING_SEARCH_SYNC_EXPLAIN"] = "1"
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
        login_handler = self._make_handler("POST", "/api/login", {"username": "admin", "password": "admin"})
        result = self.api.handle_request(login_handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0]

    def test_task_create_start_and_candidates(self):
        create_handler = self._make_handler(
            "POST",
            "/api/tasks",
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "deep_search",
                "sort_by": "active",
                "max_candidates": 5,
                "max_pages": 1,
                "search_config": {"keyword": "测试工程师"},
                "require_hr_confirmation": True,
            },
        )
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        task_id = json.loads(body)["task_id"]

        start_handler = self._make_handler("POST", f"/api/tasks/{task_id}/start")
        status, body = self.api.handle_request(start_handler)
        self.assertEqual(status, 200)
        started = json.loads(body)
        self.assertEqual(started["task_id"], task_id)
        self.assertTrue(started["processed"])
        self.assertIn("search_index_sync", started)
        self.assertTrue(started["search_index_sync"]["ok"])
        self.assertGreaterEqual(started["search_index_sync"]["upserted_profiles"], 1)
        self.assertIn("token_usage", started)
        self.assertIn("total_tokens", started["token_usage"])

        task_handler = self._make_handler("GET", f"/api/tasks/{task_id}")
        status, body = self.api.handle_request(task_handler)
        self.assertEqual(status, 200)
        task_payload = json.loads(body)["task"]
        self.assertIn("token_usage", task_payload)
        self.assertIn("total_tokens", task_payload["token_usage"])

        list_handler = self._make_handler("GET", f"/api/tasks/{task_id}/candidates")
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        self.assertGreaterEqual(len(items), 1)

        query_handler = self._make_handler(
            "POST",
            "/api/v3/search/query",
            {
                "query_text": "在线教育 Linux adb Charles 测试工程师",
                "filters": {"education_min": "本科"},
                "top_k": 5,
                "explain": False,
            },
        )
        status, body = self.api.handle_request(query_handler)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["results"])
        self.assertIn("测试", payload["results"][0]["latest_title"])

    def test_task_create_accepts_unified_jd_scorecard(self):
        custom_scorecard = upsert_custom_scorecard(
            {
                "name": "Python开发-年龄范围",
                "scorecard": {
                    "name": "Python开发-年龄范围",
                    "role_title": "Python开发工程师",
                    "jd_text": "Python开发工程师，北京，本科，3年以上，25-35岁，熟悉 Python、Linux、Redis",
                    "filters": {"location": "北京", "years_min": 3, "age_min": 25, "age_max": 35, "education_min": "本科"},
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
                        "enforce_age": True,
                        "enforce_education": True,
                        "enforce_location": False,
                        "strict_exclude": False,
                        "must_have_ratio_min": 0.5,
                    },
                },
            }
        )

        create_handler = self._make_handler(
            "POST",
            "/api/tasks",
            {
                "job_id": custom_scorecard["id"],
                "search_mode": "deep_search",
                "sort_by": "active",
                "max_candidates": 5,
                "max_pages": 1,
                "search_config": {"keyword": "Python开发"},
                "require_hr_confirmation": True,
            },
        )
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 201)
        task_id = json.loads(body)["task_id"]

        task_handler = self._make_handler("GET", f"/api/tasks/{task_id}")
        status, body = self.api.handle_request(task_handler)
        self.assertEqual(status, 200)
        task_payload = json.loads(body)["task"]
        self.assertEqual(task_payload["job_id"], custom_scorecard["id"])

    def test_login_and_protected_page(self):
        trial_handler = self._make_handler("GET", "/hr/trial")
        result = self.api.handle_request(trial_handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 303)
        self.assertIn("/login", headers.get("Location", ""))

        page_handler = self._make_handler("GET", "/hr/tasks")
        result = self.api.handle_request(page_handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 303)
        self.assertIn("/login", headers.get("Location", ""))

        login_handler = self._make_handler("POST", "/api/login", {"username": "admin", "password": "admin"})
        result = self.api.handle_request(login_handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertIn("screening_session=", cookie)

        page_handler = self._make_handler("GET", "/hr/tasks")
        page_handler.headers["Cookie"] = cookie
        result = self.api.handle_request(page_handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("Recommend", body.decode("utf-8"))

        root_handler = self._make_handler("GET", "/")
        root_handler.headers["Cookie"] = cookie
        result = self.api.handle_request(root_handler)
        self.assertEqual(len(result), 4)
        status, _body, _content_type, headers = result
        self.assertEqual(status, 303)
        self.assertIn("/hr/trial", headers.get("Location", ""))

        trial_handler = self._make_handler("GET", "/hr/trial")
        trial_handler.headers["Cookie"] = cookie
        result = self.api.handle_request(trial_handler)
        self.assertEqual(len(result), 3)
        status, body, content_type = result
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("试点中心", body.decode("utf-8"))

    def test_recommend_run_requires_login(self):
        handler = self._make_handler(
            "POST",
            "/api/recommend/run",
            {
                "job_id": "qa_test_engineer_v1",
                "max_candidates": 10,
                "max_pages": 2,
                "sort_by": "active",
            },
        )
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 401)
        self.assertIn("登录", json.loads(body)["error"])

    def test_boss_session_save_prompts_manual_login_when_not_detected(self):
        cookie = self._login_cookie()
        handler = self._make_handler("POST", "/api/boss/session/save", {})
        handler.headers["Cookie"] = cookie
        with mock.patch.object(
            self.api,
            "save_boss_storage_state",
            return_value={
                "ok": False,
                "login_detected": False,
                "manual_login_required": True,
                "reason": "on_login_form",
                "message": "未检测到有效的 BOSS 登录状态。请先在打开的 BOSS 页面手动登录，然后再次点击保存会话。",
            },
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 400)
        payload = json.loads(body)
        self.assertIn("手动登录", payload["error"])
        self.assertTrue(payload["summary"]["manual_login_required"])

    def test_boss_session_save_returns_success_when_login_detected(self):
        cookie = self._login_cookie()
        handler = self._make_handler("POST", "/api/boss/session/save", {})
        handler.headers["Cookie"] = cookie
        with mock.patch.object(
            self.api,
            "save_boss_storage_state",
            return_value={
                "ok": True,
                "login_detected": True,
                "manual_login_required": False,
                "reason": "recruiter_ui_detected",
                "message": "已检测到有效的 BOSS 招聘端登录状态，并完成会话保存。",
            },
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["login_detected"])

    def test_boss_session_sync_accepts_extension_payload(self):
        handler = self._make_handler(
            "POST",
            "/api/boss/session/sync",
            {
                "source": "chrome_extension",
                "browser": "chrome",
                "current_url": "https://www.zhipin.com/web/chat/index",
                "cookies": [{"name": "sid", "value": "abc", "domain": ".zhipin.com", "path": "/"}],
            },
        )
        with mock.patch.object(
            self.api,
            "sync_boss_storage_state",
            return_value={
                "ok": True,
                "cookie_count": 1,
                "source": "chrome_extension",
                "browser": "chrome",
                "message": "已从当前 Chrome 会话同步 BOSS Cookie 到本地筛选系统。",
            },
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["cookie_count"], 1)

    def test_boss_session_reset_clears_previous_state_and_reopens_clean_browser(self):
        cookie = self._login_cookie()
        handler = self._make_handler("POST", "/api/boss/session/reset", {})
        handler.headers["Cookie"] = cookie
        with mock.patch.object(
            self.api,
            "reset_boss_storage_state",
            return_value={
                "ok": True,
                "login_detected": False,
                "manual_login_required": True,
                "session_cleared": True,
                "reason": "session_reset",
                "message": "已清空旧的 BOSS 会话，并打开干净的登录浏览器。请在打开的页面里手动点击登录/扫码，完成后再次点击保存会话。",
            },
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["manual_login_required"])
        self.assertTrue(payload["session_cleared"])

    def test_extension_score_endpoint_returns_result(self):
        fake_service = mock.Mock()
        fake_service.score_candidate_page.return_value = {
            "score": 88.5,
            "decision": "recommend",
            "dimension_scores": {"core_test_depth": 22.0},
            "hard_filter_fail_reasons": [],
            "review_reasons": [],
            "extracted_fields": {"name": "张三"},
            "fallback_used": False,
            "model_usage": {"total_tokens": 120},
            "scored_at": "2026-03-18T03:00:00Z",
        }
        handler = self._make_handler(
            "POST",
            "/api/extension/score",
            {
                "job_id": "qa_test_engineer_v1",
                "page_url": "https://www.zhipin.com/web/geek/job-recommend/abc123.html",
                "page_title": "测试工程师",
                "page_text": "5年测试经验，本科，接口测试，回归测试。",
                "candidate_hint": "张三 / QA",
            },
        )
        with mock.patch.object(self.api, "ExtensionScoreService", return_value=fake_service), mock.patch.object(
            self.api,
            "_force_model_env",
            return_value=None,
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["score"], 88.5)
        self.assertEqual(payload["decision"], "recommend")
        fake_service.score_candidate_page.assert_called_once()

    def test_extension_score_endpoint_rejects_bad_request(self):
        handler = self._make_handler(
            "POST",
            "/api/extension/score",
            {
                "job_id": "qa_test_engineer_v1",
                "page_url": "https://www.zhipin.com/web/geek/job-recommend/empty.html",
                "page_text": "   ",
            },
        )
        fake_service = mock.Mock()
        fake_service.score_candidate_page.side_effect = ValueError("page_text 不能为空")
        with mock.patch.object(self.api, "ExtensionScoreService", return_value=fake_service), mock.patch.object(
            self.api,
            "_force_model_env",
            return_value=None,
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 400)
        self.assertIn("page_text", json.loads(body)["error"])

    def test_scoring_targets_endpoint_includes_custom_scorecard(self):
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

        handler = self._make_handler("GET", "/api/scoring-targets")
        status, body = self.api.handle_request(handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        self.assertTrue(any(item["id"] == "qa_test_engineer_v1" for item in items))
        self.assertTrue(any(item["id"] == custom["id"] and item["kind"] == "custom_phase2" for item in items))

    def test_extension_candidate_upsert_lookup_and_stage_lock(self):
        upsert_handler = self._make_handler(
            "POST",
            "/api/extension/candidates/upsert",
            {
                "job_id": "qa_test_engineer_v1",
                "page_url": "https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
                "page_title": "测试工程师",
                "page_text": "张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
                "candidate_name": "张三",
                "source": "boss_extension_v1",
                "source_candidate_key": "geek-001",
                "context_key": "ctx-001",
            },
        )
        status, body = self.api.handle_request(upsert_handler)
        self.assertEqual(status, 200)
        created = json.loads(body)
        self.assertTrue(created["created_new"])
        candidate_id = created["candidate_id"]

        lookup_handler = self._make_handler(
            "GET",
            "/api/extension/candidates/lookup?job_id=qa_test_engineer_v1&source_candidate_key=geek-001",
        )
        status, body = self.api.handle_request(lookup_handler)
        self.assertEqual(status, 200)
        lookup = json.loads(body)
        self.assertTrue(lookup["found"])
        self.assertEqual(lookup["candidate_id"], candidate_id)
        self.assertEqual(lookup["pipeline_state"]["current_stage"], "new")

        stage_handler = self._make_handler(
            "POST",
            f"/api/candidates/{candidate_id}/stage",
            {
                "current_stage": "to_review",
                "reason_code": "resume_incomplete",
                "reason_notes": "需要人工复核",
                "final_decision": "review",
                "operator": "boss_extension_hr",
            },
        )
        status, body = self.api.handle_request(stage_handler)
        self.assertEqual(status, 200)
        stage_payload = json.loads(body)
        self.assertTrue(stage_payload["state"]["manual_stage_locked"])
        self.assertEqual(stage_payload["state"]["current_stage"], "to_review")

    def test_extension_candidate_score_endpoint_returns_scored_candidate_payload(self):
        upsert_handler = self._make_handler(
            "POST",
            "/api/extension/candidates/upsert",
            {
                "job_id": "qa_test_engineer_v1",
                "page_url": "https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
                "page_title": "测试工程师",
                "page_text": "张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
                "candidate_name": "张三",
                "source": "boss_extension_v1",
                "source_candidate_key": "geek-001",
            },
        )
        status, body = self.api.handle_request(upsert_handler)
        self.assertEqual(status, 200)
        candidate_id = json.loads(body)["candidate_id"]

        fake_service = mock.Mock()
        fake_service.score_candidate.return_value = {
            "candidate_id": candidate_id,
            "score": 88.5,
            "decision": "recommend",
            "hard_filter_pass": True,
            "dimension_scores": {"core_test_depth": 22.0},
            "hard_filter_fail_reasons": [],
            "review_reasons": [],
            "extracted_fields": {"name": "张三"},
            "fallback_used": False,
            "model_usage": {"total_tokens": 120},
            "scored_at": "2026-03-18T03:00:00Z",
            "pipeline_state": {"current_stage": "scored", "manual_stage_locked": False},
            "state_transition": {"from": "new", "to": "scored", "skipped": False},
        }
        handler = self._make_handler(
            "POST",
            f"/api/extension/candidates/{candidate_id}/score",
            {
                "job_id": "qa_test_engineer_v1",
                "page_url": "https://www.zhipin.com/web/frame/c-resume/?geekId=geek-001",
                "page_title": "测试工程师",
                "page_text": "张三\n26岁 5年 本科\n工作经历\n熟悉接口测试、回归测试。",
                "candidate_hint": "张三",
            },
        )
        with mock.patch.object(self.api, "ExtensionCandidateIngestService", return_value=fake_service), mock.patch.object(
            self.api,
            "_force_model_env",
            return_value=None,
        ):
            status, body = self.api.handle_request(handler)

        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["candidate_id"], candidate_id)
        self.assertEqual(payload["pipeline_state"]["current_stage"], "scored")
        fake_service.score_candidate.assert_called_once()

    def test_pipeline_endpoints_create_list_and_run(self):
        create_handler = self._make_handler(
            "POST",
            "/api/v3/pipelines",
            {
                "name": "夜间采集",
                "job_id": "qa_test_engineer_v1",
                "search_mode": "recommend",
                "max_candidates": 3,
                "max_pages": 1,
                "schedule_minutes": 120,
                "search_configs": [
                    {"keyword": "测试工程师", "city": "北京"},
                    {"keyword": "测试工程师", "city": "上海"},
                ],
                "runtime_options": {
                    "skip_existing_candidates": True,
                    "refresh_window_hours": 168,
                    "rebuild_interval_hours": 0,
                },
            },
        )
        status, body = self.api.handle_request(create_handler)
        self.assertEqual(status, 200)
        pipeline = json.loads(body)["pipeline"]
        self.assertEqual(pipeline["name"], "夜间采集")

        list_handler = self._make_handler("GET", "/api/v3/pipelines")
        status, body = self.api.handle_request(list_handler)
        self.assertEqual(status, 200)
        items = json.loads(body)["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "夜间采集")

        run_handler = self._make_handler("POST", f"/api/v3/pipelines/{pipeline['id']}/run")
        status, body = self.api.handle_request(run_handler)
        self.assertEqual(status, 200)
        summary = json.loads(body)
        self.assertTrue(summary["ok"])
        self.assertEqual(len(summary["task_ids"]), 2)
