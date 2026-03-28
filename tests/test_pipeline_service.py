import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.gpt54_adapter import MockBrowserAgent
from src.screening.orchestrator import ScreeningOrchestrator
from src.screening.pipeline_service import CollectionPipelineService
from src.screening.repositories import (
    get_collection_pipeline,
    list_collection_pipeline_runs,
    list_recent_tasks,
)
from src.screening.search_service import ResumeSearchService


class PipelineServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._previous_qdrant_path = os.environ.get("SCREENING_SEARCH_QDRANT_PATH")
        self._previous_qdrant_url = os.environ.get("SCREENING_SEARCH_QDRANT_URL")
        self._previous_embedding_provider = os.environ.get("SCREENING_SEARCH_EMBEDDING_PROVIDER")
        self._previous_local_llm_enabled = os.environ.get("SCREENING_SEARCH_ENABLE_LOCAL_LLM")
        self._previous_local_llm_base_url = os.environ.get("SCREENING_SEARCH_OPENAI_BASE_URL")
        self._previous_local_llm_api_key = os.environ.get("SCREENING_SEARCH_OPENAI_API_KEY")
        self._previous_local_llm_model = os.environ.get("SCREENING_SEARCH_OPENAI_MODEL")
        os.environ["SCREENING_SEARCH_QDRANT_PATH"] = str(Path(self.tmpdir.name) / "qdrant")
        os.environ.pop("SCREENING_SEARCH_QDRANT_URL", None)
        os.environ["SCREENING_SEARCH_EMBEDDING_PROVIDER"] = "hash"
        os.environ.pop("SCREENING_SEARCH_ENABLE_LOCAL_LLM", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_BASE_URL", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_API_KEY", None)
        os.environ.pop("SCREENING_SEARCH_OPENAI_MODEL", None)
        db.DB_PATH = Path(self.tmpdir.name) / "screening.db"
        db.init_db()
        self.search_service = ResumeSearchService()
        self.orchestrator = ScreeningOrchestrator(
            browser_agent=MockBrowserAgent(),
            search_service=self.search_service,
        )
        self.service = CollectionPipelineService(
            orchestrator=self.orchestrator,
            search_service=self.search_service,
        )

    def tearDown(self):
        if hasattr(self.search_service, "close"):
            self.search_service.close()
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

    def test_run_pipeline_creates_batch_tasks_and_syncs_search_index(self):
        pipeline = self.service.upsert_pipeline(
            {
                "name": "测试批量采集",
                "job_id": "qa_test_engineer_v1",
                "search_mode": "recommend",
                "max_candidates": 2,
                "max_pages": 1,
                "schedule_minutes": 30,
                "search_configs": [
                    {"keyword": "测试工程师", "city": "北京"},
                    {"keyword": "测试工程师", "city": "上海"},
                ],
                "runtime_options": {
                    "skip_existing_candidates": True,
                    "refresh_window_hours": 168,
                    "rebuild_interval_hours": 0,
                },
            }
        )

        summary = self.service.run_pipeline(pipeline["id"], force=True)
        self.assertTrue(summary["ok"])
        self.assertEqual(len(summary["task_ids"]), 2)
        self.assertEqual(len(summary["tasks"]), 2)
        self.assertGreaterEqual(summary["processed_count"], 2)
        self.assertGreaterEqual(summary["upserted_profiles"], 1)
        self.assertGreaterEqual(summary["upserted_chunks"], 1)

        stored = get_collection_pipeline(pipeline["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["last_run_status"], "completed")
        self.assertIsNotNone(stored["last_run_started_at"])
        self.assertIsNotNone(stored["last_run_finished_at"])
        self.assertIsNotNone(stored["next_run_at"])

        runs = list_collection_pipeline_runs(pipeline["id"])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "completed")
        self.assertEqual(len(runs[0]["task_ids"]), 2)

        tasks = list_recent_tasks(limit=10)
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(task["search_mode"] == "recommend" for task in tasks))
        self.assertEqual(tasks[0]["search_config"]["city"] in {"北京", "上海"}, True)

    def test_run_due_pipelines_only_triggers_due_items(self):
        due = self.service.upsert_pipeline(
            {
                "id": "pipeline-due",
                "name": "到期任务",
                "job_id": "qa_test_engineer_v1",
                "search_configs": [{"keyword": "测试"}],
                "next_run_at": "2000-01-01 00:00:00",
            }
        )
        self.service.upsert_pipeline(
            {
                "id": "pipeline-future",
                "name": "未来任务",
                "job_id": "qa_test_engineer_v1",
                "search_configs": [{"keyword": "测试"}],
                "next_run_at": "2999-01-01 00:00:00",
            }
        )

        summary = self.service.run_due_pipelines()
        self.assertEqual(summary["triggered"], 1)
        self.assertEqual(summary["runs"][0]["pipeline_id"], due["id"])

    def test_pipeline_can_force_vector_rebuild_after_batch(self):
        pipeline = self.service.upsert_pipeline(
            {
                "name": "重建索引批次",
                "job_id": "qa_test_engineer_v1",
                "search_configs": [{"keyword": "测试工程师"}],
                "runtime_options": {"run_full_rebuild_after_batch": True},
            }
        )
        with mock.patch.object(
            self.search_service,
            "rebuild_vector_store",
            return_value={"ok": True, "points": 123},
        ) as rebuild_mock:
            summary = self.service.run_pipeline(pipeline["id"], force=True)
        self.assertTrue(summary["ok"])
        rebuild_mock.assert_called_once()
        self.assertEqual(summary["vector_rebuild"]["points"], 123)
