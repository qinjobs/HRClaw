import json
import tempfile
import unittest
from pathlib import Path

from src.screening.gpt54_adapter import OpenAIComputerAgent


class FakeRuntime:
    width = 1440
    height = 900
    current_url = "https://www.zhipin.com/"

    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def start(self):
        return "fake-session"

    def screenshot_base64(self):
        return "ZmFrZQ=="

    def persist_screenshot(self, label: str) -> str:
        path = Path(self.tmpdir.name) / f"{label}.png"
        path.write_bytes(b"fake")
        return str(path)

    def execute(self, action):
        return {"ok": True}


class AdapterTests(unittest.TestCase):
    def test_parse_candidates_payload(self):
        runtime = FakeRuntime()
        self.addCleanup(runtime.tmpdir.cleanup)
        agent = OpenAIComputerAgent(client=object(), runtime=runtime)
        agent.session_id = "fake-session"
        payload = json.dumps(
            {
                "blocked": False,
                "reason": None,
                "candidates": [
                    {
                        "external_id": "boss-1",
                        "name": "Alice",
                        "education_level": "本科",
                        "years_experience": 5,
                        "skills": ["Linux", "adb"],
                        "industry_tags": ["在线教育"],
                        "resume_summary": "QA engineer",
                        "evidence_map": {"years_experience": "5年"},
                    }
                ],
            }
        )
        items = agent._parse_candidates("qa_test_engineer_v1", payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "boss-1")
        self.assertTrue(items[0].screenshot_path.endswith(".png"))

    def test_parse_blocked_payload_raises(self):
        runtime = FakeRuntime()
        self.addCleanup(runtime.tmpdir.cleanup)
        agent = OpenAIComputerAgent(client=object(), runtime=runtime)
        agent.session_id = "fake-session"
        payload = json.dumps({"blocked": True, "reason": "captcha", "candidates": []})
        with self.assertRaises(RuntimeError):
            agent._parse_candidates("qa_test_engineer_v1", payload)
