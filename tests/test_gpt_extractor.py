import json
import os
import unittest
from unittest import mock

from src.screening.gpt_extractor import GPTFieldExtractor


class FakeChatResponse:
    def __init__(self, payload: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": payload})()})()]
        self.usage = type(
            "Usage",
            (),
            {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
            },
        )()


class FakeChatCompletionsAPI:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeChatResponse(self.payload)


class FakeFailingChatCompletionsAPI:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("provider unavailable")


class FakeClient:
    def __init__(self, payload: str):
        self.chat = type("ChatAPI", (), {"completions": FakeChatCompletionsAPI(payload)})()


class FakeFailingClient:
    def __init__(self):
        self.chat = type("ChatAPI", (), {"completions": FakeFailingChatCompletionsAPI()})()


class GPTExtractorTests(unittest.TestCase):
    def test_extract_candidate_validates_and_parses(self):
        payload = json.dumps(
            {
                "name": "Alice",
                "education_level": "本科",
                "skills": ["Linux", "adb"],
                "industry_tags": ["在线教育"],
                "project_keywords": [],
                "certificates": [],
                "resume_summary": "QA engineer",
                "evidence_map": {"education_level": "本科"},
            }
        )
        with mock.patch.dict(os.environ, {"SCREENING_EXTRACTION_PROVIDER": "openai_compatible"}, clear=False):
            extractor = GPTFieldExtractor(client=FakeClient(payload))
            result = extractor.extract_candidate("qa_test_engineer_v1", "本科 Linux adb", "ZmFrZQ==")
        self.assertEqual(result["name"], "Alice")
        self.assertEqual(result["skills"], ["Linux", "adb"])
        self.assertEqual(len(extractor.client.chat.completions.calls), 1)
        self.assertIsNotNone(extractor.last_usage)
        self.assertEqual(extractor.last_usage["prompt_tokens"], 123)
        self.assertEqual(extractor.last_usage["completion_tokens"], 45)
        self.assertEqual(extractor.last_usage["total_tokens"], 168)

    def test_merge_with_fallback_builds_normalized_fields(self):
        with mock.patch.dict(os.environ, {"SCREENING_EXTRACTION_PROVIDER": "openai_compatible"}, clear=False):
            extractor = GPTFieldExtractor(client=FakeClient("{}"))
            merged = extractor.merge_with_fallback(
                "qa_test_engineer_v1",
                {"name": "Alice", "skills": ["Linux"], "resume_summary": "测试 接口测试 缺陷 Linux"},
                {"skills": ["Linux"], "industry_tags": ["在线教育"], "resume_summary": "测试 接口测试 缺陷 Linux"},
            )
        self.assertEqual(merged["name"], "Alice")
        self.assertTrue(merged["normalized_fields"]["testing_evidence"])
        self.assertEqual(merged["industry_tags"], ["在线教育"])

    def test_merge_with_fallback_allows_role_signal_fallback(self):
        with mock.patch.dict(os.environ, {"SCREENING_EXTRACTION_PROVIDER": "openai_compatible"}, clear=False):
            extractor = GPTFieldExtractor(client=FakeClient("{}"))
            merged = extractor.merge_with_fallback(
                "qa_test_engineer_v1",
                {"name": "Bob", "resume_summary": "5年测试经验，负责功能测试"},
                {"skills": [], "industry_tags": [], "resume_summary": "5年测试经验，负责功能测试"},
            )
        self.assertTrue(merged["normalized_fields"]["testing_evidence"])

    def test_merge_with_fallback_overrides_model_testing_evidence_when_rule_not_met(self):
        with mock.patch.dict(os.environ, {"SCREENING_EXTRACTION_PROVIDER": "openai_compatible"}, clear=False):
            extractor = GPTFieldExtractor(client=FakeClient("{}"))
            merged = extractor.merge_with_fallback(
                "qa_test_engineer_v1",
                {
                    "name": "Carol",
                    "resume_summary": "3年开发工程师经验，熟悉业务流程",
                    "normalized_fields": {"testing_evidence": True},
                },
                {"skills": [], "industry_tags": [], "resume_summary": "3年开发工程师经验，熟悉业务流程"},
            )
        self.assertFalse(merged["normalized_fields"]["testing_evidence"])

    def test_extract_candidate_raises_when_provider_fails(self):
        with mock.patch.dict(os.environ, {"SCREENING_EXTRACTION_PROVIDER": "openai_compatible"}, clear=False):
            extractor = GPTFieldExtractor(client=FakeFailingClient())
            with self.assertRaises(RuntimeError):
                extractor.extract_candidate("py_dev_engineer_v1", "本科 Python")

    def test_extract_candidate_with_kimi_cli_bridge(self):
        payload = json.dumps(
            {
                "name": "Alice",
                "education_level": "本科",
                "skills": ["Linux", "adb"],
                "industry_tags": ["在线教育"],
                "project_keywords": [],
                "certificates": [],
                "resume_summary": "QA engineer",
                "evidence_map": {"education_level": "本科"},
            }
        )
        calls: list[dict] = []

        def fake_cli_runner(command, **kwargs):
            calls.append({"command": command, **kwargs})
            return type("Completed", (), {"returncode": 0, "stdout": payload, "stderr": ""})()

        with mock.patch.dict(
            os.environ,
            {
                "SCREENING_EXTRACTION_PROVIDER": "kimi_cli",
                "SCREENING_ENABLE_MODEL_EXTRACTION": "true",
                "SCREENING_KIMI_CLI_COMMAND": "kimi",
            },
            clear=False,
        ):
            extractor = GPTFieldExtractor(cli_runner=fake_cli_runner)
            result = extractor.extract_candidate("qa_test_engineer_v1", "本科 Linux adb")

        self.assertEqual(result["name"], "Alice")
        self.assertTrue(calls)
        self.assertEqual(calls[0]["command"][0], "kimi")
        self.assertIn("--print", calls[0]["command"])
        self.assertEqual(calls[0]["input"], None)
        self.assertEqual(extractor.last_usage["provider"], "kimi_cli")
