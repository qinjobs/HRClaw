import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening.boss_selectors import BossSelectors
from src.screening.gpt_extractor import GPTFieldExtractor
from src.screening.playwright_agent import PlaywrightLocalAgent


class FakeRecommendRuntime:
    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.session_id = "recommend-session"
        self.current_url = "https://www.zhipin.com/web/chat/recommend"
        self.opened_ids = []
        self.greet_clicks = 0
        self.login_scan_active = False
        self.login_scan_wait_calls = []
        self.manual_verification_active = False
        self.manual_verification_wait_calls = []
        self.cards = [
            {
                "external_id": "recommend-001",
                "name": "候选人A",
                "current_title": "测试工程师",
                "current_company": "Demo Co",
                "years_experience": 5,
                "education_level": "本科",
                "location": "北京",
                "last_active_time": "刚刚活跃",
                "detail_url": None,
                "summary_text": (
                    "5年 测试工程师 在线教育 前端 后端 接口测试 测试计划 测试用例 "
                    "Linux Charles Jmeter Postman adb selenium appium 本科"
                ),
            }
        ]

    def start(self):
        return self.session_id

    def stop(self):
        self.tmpdir.cleanup()

    def goto_recommend_page(self, selectors):
        self.current_url = selectors.recommend_url
        return self.current_url

    def wait_for_any(self, selectors, timeout_ms=0):
        return selectors[0] if selectors else None

    def collect_recommend_cards(self, selectors, limit):
        return self.cards[:limit]

    def go_to_next_page(self, selectors):
        return False

    def open_recommend_candidate(self, card, selectors):
        self.opened_ids.append(card["external_id"])
        self.current_url = "https://www.zhipin.com/web/chat/recommend/detail"
        return self.current_url

    def extract_detail_payload(self, selectors):
        return {
            "detail_url": self.current_url,
            "page_text": (
                "5年测试经验 在线教育 前端 后端 接口测试 测试计划 测试策略 测试用例 缺陷跟踪 回归验证 "
                "需求分析 设计评审 冒烟 性能测试 Linux Charles Jmeter SQL Postman adb selenium appium "
                "pytest oracle docker grafana prometheus 本科 北京"
            ),
        }

    def extract_recommend_detail_payload(self, selectors):
        return self.extract_detail_payload(selectors)

    def download_resume(self, selectors, external_id=None, timeout_ms=12000):
        file_path = Path(self.tmpdir.name) / f"{external_id or 'resume'}.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        return {
            "downloaded": True,
            "resume_path": str(file_path),
            "suggested_filename": f"{external_id or 'resume'}.pdf",
        }

    def persist_resume_text(self, external_id, content):
        path = Path(self.tmpdir.name) / f"{external_id}.txt"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def screenshot_base64(self):
        return "ZmFrZQ=="

    def persist_screenshot(self, label):
        path = Path(self.tmpdir.name) / f"{label}.png"
        path.write_bytes(b"fake")
        return str(path)

    def click_recommend_greet(self, selectors):
        self.greet_clicks += 1
        return {"clicked": True}

    def close_recommend_detail(self, selectors):
        self.current_url = "https://www.zhipin.com/web/chat/recommend"
        return True

    def is_manual_verification_page(self):
        return self.manual_verification_active

    def wait_for_manual_verification(self, timeout_ms=180000, check_interval_ms=1500):
        self.manual_verification_wait_calls.append((timeout_ms, check_interval_ms))
        self.manual_verification_active = False
        return True

    def is_login_scan_page(self):
        return self.login_scan_active

    def wait_for_login_scan(self, timeout_ms=20000, check_interval_ms=1500):
        self.login_scan_wait_calls.append((timeout_ms, check_interval_ms))
        self.login_scan_active = False
        return True


class FakeExtractor:
    enabled = False

    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {}

    def merge_with_fallback(self, job_id, extracted, fallback_item):
        extractor = GPTFieldExtractor(client=object())
        return extractor.merge_with_fallback(job_id, extracted, fallback_item)


class RecommendFlowTests(unittest.TestCase):
    def _selectors(self):
        return BossSelectors(
            search_url="https://www.zhipin.com/web/chat/search",
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

    def test_recommend_flow_auto_greet_when_score_above_threshold(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "true", "SCREENING_AUTO_GREET_THRESHOLD": "0"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].evidence_map["resume_downloaded"])
        self.assertTrue(items[0].evidence_map["auto_greet_attempted"])
        self.assertTrue(items[0].evidence_map["auto_greet_clicked"])
        self.assertTrue(items[0].evidence_map["recommend_detail_closed"])
        self.assertEqual(runtime.greet_clicks, 1)

    def test_recommend_flow_skips_greet_when_score_below_threshold(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "true", "SCREENING_AUTO_GREET_THRESHOLD": "999"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].evidence_map["auto_greet_attempted"])
        self.assertFalse(items[0].evidence_map["auto_greet_clicked"])
        self.assertEqual(items[0].evidence_map["auto_greet_reason"], "below_threshold")
        self.assertEqual(runtime.greet_clicks, 0)

    def test_recommend_flow_exports_text_when_download_unavailable(self):
        class NoDownloadRuntime(FakeRecommendRuntime):
            def download_resume(self, selectors, external_id=None, timeout_ms=12000):
                return {"downloaded": False, "resume_path": None, "reason": "download_button_not_found"}

        runtime = NoDownloadRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "false"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].evidence_map["resume_downloaded"])
        self.assertTrue(items[0].evidence_map["resume_fallback_exported"])
        self.assertTrue(str(items[0].evidence_map["resume_path"]).endswith(".txt"))

    def test_recommend_flow_skips_existing_candidates_before_opening_detail(self):
        runtime = FakeRecommendRuntime()
        checker_calls = []

        def fake_checker(external_ids, *, max_age_hours=None):
            checker_calls.append((list(external_ids), max_age_hours))
            return {"recommend-001"}

        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
            existing_candidate_checker=fake_checker,
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            1,
            search_mode="recommend",
            search_config={"skip_existing_candidates": True, "refresh_window_hours": 72},
            max_pages=1,
        )
        self.assertEqual(items, [])
        self.assertEqual(runtime.opened_ids, [])
        self.assertEqual(checker_calls, [(["recommend-001"], 72.0)])

    def test_recommend_flow_applies_human_browse_delay(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        with mock.patch("src.screening.playwright_agent.random.uniform", return_value=7.5), mock.patch(
            "src.screening.playwright_agent.time.sleep"
        ) as sleep_mock:
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={
                    "resume_browse_delay_min_seconds": 5,
                    "resume_browse_delay_max_seconds": 10,
                },
                max_pages=1,
            )
        self.assertEqual(len(items), 1)
        sleep_mock.assert_called_once_with(7.5)

    def test_recommend_flow_waits_for_manual_verification(self):
        runtime = FakeRecommendRuntime()
        runtime.manual_verification_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            1,
            search_mode="recommend",
            search_config={"manual_verification_timeout_seconds": 30},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(runtime.manual_verification_wait_calls, [(30000, 1500)])

    def test_recommend_flow_waits_for_login_scan(self):
        runtime = FakeRecommendRuntime()
        runtime.login_scan_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            1,
            search_mode="recommend",
            search_config={"login_scan_wait_seconds": 20},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(runtime.login_scan_wait_calls, [(20000, 1500)])

    def test_recommend_flow_raises_when_manual_verification_not_cleared(self):
        class BlockingVerifyRuntime(FakeRecommendRuntime):
            def wait_for_manual_verification(self, timeout_ms=180000, check_interval_ms=1500):
                self.manual_verification_wait_calls.append((timeout_ms, check_interval_ms))
                return False

        runtime = BlockingVerifyRuntime()
        runtime.manual_verification_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        with self.assertRaisesRegex(RuntimeError, "manual verification"):
            agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"manual_verification_timeout_seconds": 30},
                max_pages=1,
            )

    def test_recommend_flow_raises_when_login_scan_not_cleared(self):
        class BlockingLoginRuntime(FakeRecommendRuntime):
            def wait_for_login_scan(self, timeout_ms=20000, check_interval_ms=1500):
                self.login_scan_wait_calls.append((timeout_ms, check_interval_ms))
                return False

        runtime = BlockingLoginRuntime()
        runtime.login_scan_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        with self.assertRaisesRegex(RuntimeError, "QR scan login"):
            agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"login_scan_wait_seconds": 20},
                max_pages=1,
            )
