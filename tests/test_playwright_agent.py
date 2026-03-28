import tempfile
import unittest
from pathlib import Path

from src.screening.boss_selectors import BossSelectors
from src.screening.gpt_extractor import GPTFieldExtractor
from src.screening.playwright_agent import PlaywrightLocalAgent, _extract_external_id


class FakeLocalRuntime:
    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.session_id = "fake-playwright-session"
        self.current_url = "https://www.zhipin.com/web/geek/job"
        self.cards = [
            {
                "external_id": "boss-local-001",
                "name": "Liu Qing",
                "current_title": "测试工程师",
                "current_company": "Blue Edu",
                "years_experience": 4,
                "education_level": "本科",
                "location": "Beijing",
                "last_active_time": "1h",
                "detail_url": "https://www.zhipin.com/geek/123456.html",
                "summary_text": "4年 测试工程师 在线教育 Linux adb Charles",
            },
            {
                "external_id": "boss-local-002",
                "name": "Wang Hao",
                "current_title": "Python开发工程师",
                "current_company": "Secure Cloud",
                "years_experience": 6,
                "education_level": "本科",
                "location": "Hangzhou",
                "last_active_time": "30m",
                "detail_url": "https://www.zhipin.com/geek/abcdef.html",
                "summary_text": "6年 Python Java Linux kafka redis elasticsearch 安全",
            },
        ]
        self.detail_payloads = {
            "boss-local-001": {
                "detail_url": "https://www.zhipin.com/geek/123456.html",
                "page_text": "4年测试经验 在线教育 接口测试 缺陷跟踪 Linux adb Charles 本科",
            },
            "boss-local-002": {
                "detail_url": "https://www.zhipin.com/geek/abcdef.html",
                "page_text": "6年Python开发经验 Linux shell Kafka Redis Elasticsearch Web Security 本科",
            },
        }
        self.opened = []

    def start(self):
        return self.session_id

    def stop(self):
        self.tmpdir.cleanup()

    def goto_search_page(self, selectors):
        return self.current_url

    def wait_for_any(self, selectors, timeout_ms=0):
        return selectors[0] if selectors else None

    def apply_search_filters(self, selectors, search_config, sort_by):
        self.search_config = dict(search_config)
        self.sort_by = sort_by
        return {"search_config": self.search_config, "sort_by": sort_by}

    def collect_candidate_cards(self, selectors, limit):
        return self.cards[:limit]

    def go_to_next_page(self, selectors):
        return False

    def open_candidate_card(self, card, selectors):
        self.opened.append(card["external_id"])
        self.current_url = card["detail_url"]
        return self.current_url

    def extract_detail_payload(self, selectors):
        external_id = self.opened[-1]
        return self.detail_payloads[external_id]

    def persist_screenshot(self, label):
        path = Path(self.tmpdir.name) / f"{label}.png"
        path.write_bytes(b"fake")
        return str(path)

    def screenshot_base64(self):
        return "ZmFrZQ=="


class FakeExtractor:
    enabled = True

    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {
            "name": "Liu Qing",
            "major": "计算机科学",
            "skills": ["Linux", "adb", "Charles"],
            "industry_tags": ["在线教育"],
            "resume_summary": "4年测试经验 在线教育 接口测试",
            "evidence_map": {"major": "计算机科学"},
        }

    def merge_with_fallback(self, job_id, extracted, fallback_item):
        extractor = GPTFieldExtractor(client=object())
        return extractor.merge_with_fallback(job_id, extracted, fallback_item)


class FakeFailingExtractor:
    enabled = True

    def extract_candidate(self, job_id, page_text, screenshot_base64):
        raise RuntimeError("insufficient_quota")

    def merge_with_fallback(self, job_id, extracted, fallback_item):
        extractor = GPTFieldExtractor(client=object())
        return extractor.merge_with_fallback(job_id, extracted, fallback_item)


class PlaywrightAgentTests(unittest.TestCase):
    def test_extract_external_id_uses_text_fingerprint_when_url_missing(self):
        external_id = _extract_external_id(
            None,
            1,
            "韩永康 北京畅读书海科技有限公司 测试工程师 3年测试经验 AI系统测试 接口自动化测试",
        )
        self.assertTrue(external_id.startswith("playwright-fp-"))
        self.assertNotEqual(external_id, "playwright-1")
        self.assertEqual(
            external_id,
            _extract_external_id(
                None,
                9,
                "韩永康 北京畅读书海科技有限公司 测试工程师 3年测试经验 AI系统测试 接口自动化测试",
            ),
        )

    def test_collect_candidates_from_local_runtime(self):
        runtime = FakeLocalRuntime()
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
            1,
            search_config={"keyword": "测试工程师", "city": "北京"},
            sort_by="active",
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "boss-local-001")
        self.assertEqual(items[0].major, "计算机科学")
        self.assertEqual(items[0].name, "Liu Qing")
        self.assertTrue(items[0].normalized_fields["testing_evidence"])
        self.assertEqual(items[0].evidence_map["major"], "计算机科学")
        self.assertEqual(items[0].evidence_map["page_index"], 1)
        self.assertEqual(items[0].evidence_map["applied_filters"]["search_config"]["city"], "北京")
        self.assertTrue(items[0].screenshot_path.endswith(".png"))

    def test_collect_candidates_falls_back_when_extractor_fails(self):
        runtime = FakeLocalRuntime()
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
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=selectors, extractor=FakeFailingExtractor())
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            1,
            search_config={"keyword": "测试工程师", "city": "北京"},
            sort_by="active",
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].evidence_map["gpt_extraction_used"])
        self.assertIn("insufficient_quota", items[0].evidence_map["gpt_extraction_error"])
        self.assertTrue(items[0].normalized_fields["testing_evidence"])
