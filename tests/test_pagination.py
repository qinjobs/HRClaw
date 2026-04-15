import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening import db
from src.screening.boss_selectors import BossSelectors
from src.screening.gpt54_adapter import MockBrowserAgent
from src.screening.orchestrator import ScreeningOrchestrator
from src.screening.playwright_agent import PlaywrightLocalAgent


class FakePagedRuntime:
    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.session_id = "paged-session"
        self.current_url = "https://www.zhipin.com/web/geek/job"
        self.page_number = 1
        self.opened = []
        self.applied = None
        self.pages = {
            1: [
                {
                    "external_id": "boss-1",
                    "name": "A",
                    "current_title": "测试工程师",
                    "current_company": "Edu",
                    "years_experience": 4,
                    "education_level": "本科",
                    "location": "Beijing",
                    "last_active_time": "1h",
                    "detail_url": "https://www.zhipin.com/geek/aaa111.html",
                    "summary_text": "4年 测试 Linux adb 在线教育",
                },
                {
                    "external_id": "boss-2",
                    "name": "B",
                    "current_title": "测试工程师",
                    "current_company": "Edu",
                    "years_experience": 5,
                    "education_level": "本科",
                    "location": "Beijing",
                    "last_active_time": "2h",
                    "detail_url": "https://www.zhipin.com/geek/bbb222.html",
                    "summary_text": "5年 测试 Charles 在线教育",
                },
            ],
            2: [
                {
                    "external_id": "boss-2",
                    "name": "B",
                    "current_title": "测试工程师",
                    "current_company": "Edu",
                    "years_experience": 5,
                    "education_level": "本科",
                    "location": "Beijing",
                    "last_active_time": "2h",
                    "detail_url": "https://www.zhipin.com/geek/bbb222.html",
                    "summary_text": "5年 测试 Charles 在线教育",
                },
                {
                    "external_id": "boss-3",
                    "name": "C",
                    "current_title": "测试工程师",
                    "current_company": "Edu",
                    "years_experience": 6,
                    "education_level": "本科",
                    "location": "Beijing",
                    "last_active_time": "3h",
                    "detail_url": "https://www.zhipin.com/geek/ccc333.html",
                    "summary_text": "6年 测试 Fiddler 在线教育",
                },
            ],
        }

    def start(self):
        return self.session_id

    def stop(self):
        self.tmpdir.cleanup()

    def goto_search_page(self, selectors):
        self.page_number = 1
        return self.current_url

    def wait_for_any(self, selectors, timeout_ms=0):
        return selectors[0] if selectors else None

    def apply_search_filters(self, selectors, search_config, sort_by):
        self.applied = {"search_config": dict(search_config), "sort_by": sort_by}
        return self.applied

    def collect_candidate_cards(self, selectors, limit):
        return list(self.pages[self.page_number])[:limit]

    def go_to_next_page(self, selectors):
        if self.page_number >= 2:
            return False
        self.page_number += 1
        return True

    def open_candidate_card(self, card, selectors):
        self.opened.append(card["external_id"])
        self.current_url = card["detail_url"]
        return self.current_url

    def extract_detail_payload(self, selectors):
        external_id = self.opened[-1]
        return {
            "detail_url": self.current_url,
            "page_text": f"{external_id} 4年测试经验 Linux adb Charles 在线教育 本科",
        }

    def persist_screenshot(self, label):
        path = Path(self.tmpdir.name) / f"{label}.png"
        path.write_bytes(b"fake")
        return str(path)

    def persist_resume_full_screenshot(self, external_id, *, suffix="resume_full"):
        path = Path(self.tmpdir.name) / f"{external_id}_{suffix}.png"
        path.write_bytes(b"fake")
        return str(path)

    def persist_resume_markdown(self, external_id, content, *, title=None, source_url=None, content_html=None, page_html=None, screenshot_path=None):
        path = Path(self.tmpdir.name) / f"{external_id}.md"
        path.write_text(f"# {title or external_id}\n\n{content or ''}", encoding="utf-8")
        return str(path)

    def screenshot_base64(self):
        return "ZmFrZQ=="


class FakeExtractor:
    enabled = False

    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {}

    def merge_with_fallback(self, job_id, extracted, fallback_item):
        from src.screening.gpt_extractor import GPTFieldExtractor

        extractor = GPTFieldExtractor(client=object())
        return extractor.merge_with_fallback(job_id, extracted, fallback_item)


class PaginationTests(unittest.TestCase):
    def test_playwright_agent_paginates_and_deduplicates(self):
        runtime = FakePagedRuntime()
        selectors = BossSelectors(
            search_url="https://www.zhipin.com/web/geek/job",
            search_keyword_input=("input",),
            search_city_input=("input",),
            search_submit=("button",),
            sort_active=("button.active",),
            sort_recent=("button.recent",),
            list_ready=("body",),
            candidate_card=("article",),
            candidate_name=("h2",),
            candidate_title=("h3",),
            candidate_company=("h4",),
            candidate_experience=("h5",),
            candidate_education=("h6",),
            candidate_location=("h7",),
            candidate_active_time=("h8",),
            candidate_link=("a",),
            candidate_external_id=("[data-id]",),
            detail_ready=("main",),
            detail_main_text=("main",),
            next_page=("button.next",),
        )
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=selectors, extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            3,
            search_config={"keyword": "测试工程师", "city": "北京"},
            sort_by="active",
            max_pages=2,
        )
        self.assertEqual([item.external_id for item in items], ["boss-1", "boss-2", "boss-3"])
        self.assertEqual(runtime.applied["search_config"]["keyword"], "测试工程师")
        self.assertEqual(items[-1].evidence_map["page_index"], 2)
        self.assertTrue(items[0].evidence_map["resume_full_screenshot_path"].endswith(".png"))
        self.assertTrue(items[0].evidence_map["resume_markdown_path"].endswith(".md"))

    def test_api_task_persists_search_config(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db.DB_PATH = Path(tmpdir.name) / "screening.db"
        db.init_db()

        from src.screening import api

        api.init_db()
        api.ORCHESTRATOR = ScreeningOrchestrator(browser_agent=MockBrowserAgent())

        raw = json.dumps(
            {
                "job_id": "qa_test_engineer_v1",
                "search_mode": "deep_search",
                "sort_by": "active",
                "max_candidates": 5,
                "max_pages": 2,
                "search_config": {"keyword": "测试工程师", "city": "北京"},
                "require_hr_confirmation": True,
            }
        ).encode("utf-8")
        handler = type("Handler", (), {})()
        handler.command = "POST"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.path = "/api/tasks"
        handler.rfile = mock.Mock()
        handler.rfile.read = mock.Mock(return_value=raw)
        status, body = api.handle_request(handler)
        self.assertEqual(status, 201)
        task_id = json.loads(body)["task_id"]

        get_handler = type("Handler", (), {})()
        get_handler.command = "GET"
        get_handler.path = f"/api/tasks/{task_id}"
        get_handler.headers = {}
        get_handler.rfile = mock.Mock()
        get_handler.rfile.read = mock.Mock(return_value=b"")
        status, body = api.handle_request(get_handler)
        self.assertEqual(status, 200)
        task = json.loads(body)["task"]
        self.assertEqual(task["search_mode"], "recommend")
        self.assertEqual(task["max_pages"], 2)
        self.assertEqual(task["search_config"]["city"], "北京")
