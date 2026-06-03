import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening.boss_selectors import BossSelectors
from src.screening.gpt_extractor import GPTFieldExtractor
from src.screening.models import CandidateDecision, ScoreResult
from src.screening.playwright_agent import PlaywrightLocalAgent


class FakeRecommendRuntime:
    def __init__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.session_id = "recommend-session"
        self.current_url = "https://www.zhipin.com/web/chat/recommend"
        self.opened_ids = []
        self.opened_cards = []
        self.events = []
        self.greet_clicks = 0
        self.next_page_calls = 0
        self.recover_recommend_list_calls = 0
        self.login_scan_active = False
        self.login_scan_wait_calls = []
        self.manual_verification_active = False
        self.manual_verification_wait_calls = []
        self.prepare_recommend_login_calls = []
        self.wait_for_recommend_list_ready_calls = []
        self.collect_recommend_cards_calls = 0
        self.close_recommend_detail_results = [True]
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
        self.events.append("goto_recommend_page")
        self.current_url = selectors.recommend_url
        return self.current_url

    def prepare_recommend_login(self, *, login_url=None, wait_timeout_ms=15000):
        self.events.append("prepare_recommend_login")
        self.prepare_recommend_login_calls.append((login_url, wait_timeout_ms))
        self.current_url = login_url or "https://www.zhipin.com/web/user/?ka=header-login"
        return {"opened": True, "waited": True, "url": self.current_url}

    def wait_for_any(self, selectors, timeout_ms=0):
        return selectors[0] if selectors else None

    def wait_for_recommend_list_ready(self, selectors, timeout_ms=10000):
        self.wait_for_recommend_list_ready_calls.append(timeout_ms)
        return {
            "ready_selector": ".card-list",
            "frame_name": "recommendFrame",
            "frame_url": "https://www.zhipin.com/web/frame/recommend/mock",
            "card_count": len(self.cards),
        }

    def collect_recommend_cards(self, selectors, limit):
        self.collect_recommend_cards_calls += 1
        items = []
        for index, card in enumerate(self.cards[:limit]):
            cloned = dict(card)
            cloned.setdefault("card_index", index)
            items.append(cloned)
        return items

    def go_to_next_page(self, selectors):
        self.next_page_calls += 1
        return False

    def recover_recommend_list(self, selectors, timeout_ms=5000):
        self.recover_recommend_list_calls += 1
        self.current_url = selectors.recommend_url
        return True

    def open_recommend_candidate(self, card, selectors):
        self.opened_ids.append(card["external_id"])
        self.opened_cards.append(dict(card))
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

    def persist_resume_full_screenshot(self, external_id, *, suffix="resume_full"):
        path = Path(self.tmpdir.name) / f"{external_id}_{suffix}.png"
        path.write_bytes(b"fake")
        return str(path)

    def persist_resume_markdown(self, external_id, content, *, title=None, source_url=None, content_html=None, page_html=None, screenshot_path=None):
        path = Path(self.tmpdir.name) / f"{external_id}.md"
        lines = [f"# {title or external_id or '简历'}", "", content or ""]
        if source_url:
            lines.insert(2, f"- 来源链接：{source_url}")
        path.write_text("\n".join(lines), encoding="utf-8")
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
        if self.close_recommend_detail_results:
            return self.close_recommend_detail_results.pop(0)
        return True

    def is_manual_verification_page(self):
        return self.manual_verification_active

    def wait_for_manual_verification(self, timeout_ms=180000, check_interval_ms=1500):
        self.manual_verification_wait_calls.append((timeout_ms, check_interval_ms))
        self.manual_verification_active = False
        return True

    def is_login_scan_page(self):
        return self.login_scan_active

    def wait_for_login_scan(self, timeout_ms=15000, check_interval_ms=1500):
        self.login_scan_wait_calls.append((timeout_ms, check_interval_ms))
        self.login_scan_active = False
        return True


class FakeRecommendRuntimeWithDynamicGreetLabel(FakeRecommendRuntime):
    def __init__(self, greet_label: str):
        super().__init__()
        self.greet_label = greet_label

    def click_recommend_greet(self, selectors):
        self.greet_clicks += 1
        available_selectors = " ".join(selectors.recommend_greet_button)
        if self.greet_label in available_selectors:
            return {"clicked": True}
        return {"clicked": False, "reason": "greet_button_not_found"}


class FakeRecommendRuntimeWithShiftedCards(FakeRecommendRuntime):
    def __init__(self):
        super().__init__()
        card_a = {
            **self.cards[0],
            "external_id": "recommend-001",
            "name": "候选人A",
            "summary_text": "候选人A 原始卡片摘要",
        }
        card_b = {
            **self.cards[0],
            "external_id": "recommend-002",
            "name": "候选人B",
            "summary_text": "候选人B 原始卡片摘要",
        }
        self.card_batches = [
            [
                {**card_a, "card_index": 0},
                {**card_b, "card_index": 1},
            ],
            [
                {**card_b, "card_index": 0},
                {**card_a, "card_index": 1},
            ],
        ]

    def collect_recommend_cards(self, selectors, limit):
        self.collect_recommend_cards_calls += 1
        batch_index = min(self.collect_recommend_cards_calls - 1, len(self.card_batches) - 1)
        return [dict(card) for card in self.card_batches[batch_index][:limit]]


class FakeRecommendRuntimeWithTransientlyMissingCard(FakeRecommendRuntime):
    def __init__(self):
        super().__init__()
        card_a = {
            **self.cards[0],
            "external_id": "recommend-001",
            "name": "候选人A",
            "summary_text": "候选人A 原始卡片摘要",
        }
        card_b = {
            **self.cards[0],
            "external_id": "recommend-002",
            "name": "候选人B",
            "summary_text": "候选人B 原始卡片摘要",
        }
        self.card_batches = [
            [
                {**card_a, "card_index": 0},
                {**card_b, "card_index": 1},
            ],
            [
                {**card_a, "card_index": 0},
            ],
            [
                {**card_a, "card_index": 0},
            ],
        ]

    def collect_recommend_cards(self, selectors, limit):
        self.collect_recommend_cards_calls += 1
        batch_index = min(self.collect_recommend_cards_calls - 1, len(self.card_batches) - 1)
        return [dict(card) for card in self.card_batches[batch_index][:limit]]


class FakeRecommendRuntimeWithRefreshedReplacementCards(FakeRecommendRuntime):
    def __init__(self):
        super().__init__()
        card_a = {
            **self.cards[0],
            "external_id": "recommend-001",
            "name": "候选人A",
            "summary_text": "候选人A 原始卡片摘要",
        }
        card_b = {
            **self.cards[0],
            "external_id": "recommend-002",
            "name": "候选人B",
            "summary_text": "候选人B 原始卡片摘要",
        }
        card_c = {
            **self.cards[0],
            "external_id": "recommend-003",
            "name": "候选人C",
            "summary_text": "候选人C 刷新后卡片摘要",
        }
        self.card_batches = [
            [
                {**card_a, "card_index": 0},
                {**card_b, "card_index": 1},
            ],
            [
                {**card_a, "card_index": 0},
                {**card_c, "card_index": 1},
            ],
            [
                {**card_a, "card_index": 0},
                {**card_c, "card_index": 1},
            ],
        ]

    def collect_recommend_cards(self, selectors, limit):
        self.collect_recommend_cards_calls += 1
        batch_index = min(self.collect_recommend_cards_calls - 1, len(self.card_batches) - 1)
        return [dict(card) for card in self.card_batches[batch_index][:limit]]


class FakeRecommendRuntimeWithKeywordPages(FakeRecommendRuntime):
    def __init__(self):
        super().__init__()
        page_one_card = {
            **self.cards[0],
            "external_id": "recommend-001",
            "name": "候选人A",
            "current_title": "产品经理",
            "location": "深圳",
            "summary_text": "候选人A 产品经理 深圳",
        }
        page_two_card = {
            **self.cards[0],
            "external_id": "recommend-002",
            "name": "候选人B",
            "current_title": "AI产品经理",
            "location": "深圳",
            "summary_text": "候选人B AI产品经理 深圳",
        }
        self.page_index = 0
        self.card_pages = [
            [{**page_one_card, "card_index": 0}],
            [{**page_two_card, "card_index": 0}],
        ]
        self.detail_payloads = {
            "recommend-001": {
                "detail_url": self.current_url,
                "page_text": "候选人A 产品经理 深圳 零售方向",
            },
            "recommend-002": {
                "detail_url": self.current_url,
                "page_text": "候选人B AI产品经理 深圳 字节合作项目",
            },
        }

    def collect_recommend_cards(self, selectors, limit):
        self.collect_recommend_cards_calls += 1
        return [dict(card) for card in self.card_pages[self.page_index][:limit]]

    def go_to_next_recommend_page(self, selectors):
        self.next_page_calls += 1
        if self.page_index >= len(self.card_pages) - 1:
            return False
        self.page_index += 1
        return True

    def extract_detail_payload(self, selectors):
        external_id = self.opened_ids[-1]
        payload = dict(self.detail_payloads[external_id])
        payload["detail_url"] = self.current_url
        return payload


class FakeExtractor:
    enabled = False

    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {}

    def merge_with_fallback(self, job_id, extracted, fallback_item):
        extractor = GPTFieldExtractor(client=object())
        return extractor.merge_with_fallback(job_id, extracted, fallback_item)


class PlaceholderNameExtractor(FakeExtractor):
    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {"name": "未提供"}


class NullNameExtractor(FakeExtractor):
    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {"name": "null"}


class GarbledStructuredFieldExtractor(FakeExtractor):
    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {
            "name": "候选人A",
            "education_level": "˶ʿ",
            "location": "\ufffd\ufffd",
            "current_title": "\ufffd\ufffd",
            "resume_summary": "\ufffd\ufffd",
        }


class DoubleEncodedMojibakeExtractor(FakeExtractor):
    def extract_candidate(self, job_id, page_text, screenshot_base64):
        return {
            "name": "����",
            "education_level": "˶ʿ",
            "location": "閿熸枻鎷烽敓鏂ゆ嫹",
            "current_company": "锟斤拷通锟斤拷锟斤拷锟斤拷锟斤拷",
            "current_title": "AI閿熸枻鎷峰搧閿熸枻鎷烽敓鏂ゆ嫹",
            "skills": ["AI Agent", "AI���ֶԻ�", "RAG"],
            "industry_tags": ["AI", "����VR"],
            "project_keywords": ["����VR��Ʒ", "B�˲�Ʒ"],
            "resume_summary": "29�꣬˶ʿѧ����4�깤�����顣",
            "evidence_map": {
                "location": "閿熸枻鎷烽敓鏂ゆ嫹",
                "current_title": "AI閿熸枻鎷峰搧閿熸枻鎷烽敓鏂ゆ嫹",
            },
            "normalized_fields": {
                "b�˾���": True,
                "data_analysis_capability": True,
                "skills": ["AI Agent", "AI���ֶԻ�"],
            },
        }


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
        self.assertTrue(items[0].evidence_map["resume_full_screenshot_path"].endswith(".png"))
        self.assertTrue(items[0].evidence_map["resume_markdown_path"].endswith(".md"))
        self.assertTrue(items[0].evidence_map["auto_greet_attempted"])
        self.assertTrue(items[0].evidence_map["auto_greet_clicked"])
        self.assertTrue(items[0].evidence_map["recommend_detail_closed"])
        self.assertEqual(runtime.greet_clicks, 1)

    def test_recommend_flow_prefers_card_name_over_placeholder_extracted_name(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=PlaceholderNameExtractor())
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
        self.assertEqual(items[0].name, "候选人A")

    def test_recommend_flow_prefers_card_name_over_null_extracted_name(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=NullNameExtractor())
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
        self.assertEqual(items[0].name, "候选人A")

    def test_recommend_flow_waits_for_recommend_list_ready_after_closing_detail(self):
        runtime = FakeRecommendRuntime()
        runtime.cards = [
            {**runtime.cards[0], "external_id": "recommend-001", "name": "候选人A"},
            {**runtime.cards[0], "external_id": "recommend-002", "name": "候选人B"},
        ]
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "false"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                2,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 2)
        self.assertGreaterEqual(len(runtime.wait_for_recommend_list_ready_calls), 3)

    def test_recommend_flow_refreshes_target_card_before_opening_when_list_reorders(self):
        runtime = FakeRecommendRuntimeWithShiftedCards()
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
        self.assertGreaterEqual(runtime.collect_recommend_cards_calls, 2)
        self.assertEqual(runtime.opened_cards[0]["external_id"], "recommend-001")
        self.assertEqual(runtime.opened_cards[0]["card_index"], 1)

    def test_recommend_flow_does_not_skip_target_when_refresh_temporarily_misses_card(self):
        runtime = FakeRecommendRuntimeWithTransientlyMissingCard()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "false"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                2,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 2)
        self.assertEqual([item.external_id for item in items], ["recommend-001", "recommend-002"])
        self.assertEqual(runtime.opened_cards[1]["external_id"], "recommend-002")

    def test_refresh_recommend_target_card_prefers_external_id_over_name(self):
        agent = PlaywrightLocalAgent(runtime=FakeRecommendRuntime(), selectors=self._selectors(), extractor=FakeExtractor())
        refreshed = agent._refresh_recommend_target_card(
            {"external_id": "recommend-001", "name": "候选人A"},
            [{"external_id": "recommend-001", "name": "候选人A(已匿名)", "card_index": 3}],
        )
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["card_index"], 3)

    def test_recommend_flow_switches_to_fresh_visible_card_when_original_target_is_replaced(self):
        runtime = FakeRecommendRuntimeWithRefreshedReplacementCards()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "false"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                2,
                search_mode="recommend",
                max_pages=1,
            )
        self.assertEqual(len(items), 2)
        self.assertEqual([item.external_id for item in items], ["recommend-001", "recommend-003"])

    def test_recommend_flow_auto_greet_supports_immediate_contact_labels(self):
        runtime = FakeRecommendRuntimeWithDynamicGreetLabel("立即沟通")
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
        self.assertTrue(items[0].evidence_map["auto_greet_attempted"])
        self.assertTrue(items[0].evidence_map["auto_greet_clicked"])
        self.assertEqual(runtime.greet_clicks, 1)

    def test_recommend_flow_prefers_repaired_education_and_readable_summary(self):
        runtime = FakeRecommendRuntime()
        runtime.cards[0].update(
            {
                "name": "李鑫",
                "current_title": "产品经理",
                "current_company": "深圳小亿网络有限公司",
                "education_level": "本科",
                "location": "深圳",
                "summary_text": "李鑫 28岁 硕士 6年 深圳 产品经理",
            }
        )
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=GarbledStructuredFieldExtractor(),
        )
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
        self.assertEqual(items[0].education_level, "硕士")
        self.assertEqual(items[0].location, "深圳")
        self.assertEqual(items[0].current_title, "产品经理")
        self.assertNotIn("\ufffd", items[0].raw_summary or "")

    def test_recommend_flow_discards_double_encoded_mojibake_fields(self):
        runtime = FakeRecommendRuntime()
        runtime.cards[0].update(
            {
                "name": "杨丽",
                "current_title": None,
                "current_company": None,
                "education_level": "硕士",
                "location": None,
                "summary_text": (
                    "20-25K\n杨丽\n刚刚活跃\n29岁 4年 硕士 离职-随时到岗\n"
                    "最近关注\n深圳 产品经理\n产品+AI经验\nB端产品\n搜索产品\n"
                    "2024.07 至今\n软通动力数字 AI产品经理\n"
                    "2024.05 2024.07\n超星尔雅智慧教育 产品经理"
                ),
            }
        )
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=DoubleEncodedMojibakeExtractor(),
        )
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
        item = items[0]
        self.assertEqual(item.name, "杨丽")
        self.assertEqual(item.education_level, "硕士")
        self.assertEqual(item.location, "深圳")
        self.assertEqual(item.current_title, "AI产品经理")
        self.assertEqual(item.current_company, "软通动力数字")
        structured_blob = json.dumps(
            {
                "normalized_fields": item.normalized_fields,
                "evidence_map": item.evidence_map,
            },
            ensure_ascii=False,
        )
        self.assertNotIn("閿", structured_blob)
        self.assertNotIn("锟斤拷", structured_blob)
        self.assertNotIn("\ufffd", structured_blob)

    def test_recommend_flow_filters_candidates_by_semicolon_keywords_across_pages(self):
        runtime = FakeRecommendRuntimeWithKeywordPages()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "false"}):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"keyword": "字节；AI"},
                max_pages=2,
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "recommend-002")
        self.assertEqual(runtime.opened_ids, ["recommend-001", "recommend-002"])
        self.assertEqual(runtime.next_page_calls, 1)

    def test_recommend_flow_auto_greet_ignores_decision_when_score_above_threshold(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        high_reject_score = ScoreResult(
            hard_filter_pass=True,
            hard_filter_fail_reasons=[],
            dimension_scores={"overall": 95.0},
            total_score=95.0,
            decision=CandidateDecision.REJECT,
            review_reasons=[],
        )
        with mock.patch("src.screening.playwright_agent.score_candidate", return_value=high_reject_score):
            with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "true", "SCREENING_AUTO_GREET_THRESHOLD": "80"}):
                agent.start_session()
                items = agent.collect_candidates(
                    "qa_test_engineer_v1",
                    1,
                    search_mode="recommend",
                    max_pages=1,
                )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].evidence_map["auto_greet_score"], 95.0)
        self.assertTrue(items[0].evidence_map["auto_greet_attempted"])
        self.assertTrue(items[0].evidence_map["auto_greet_clicked"])
        self.assertEqual(runtime.greet_clicks, 1)

    def test_recommend_flow_uses_scorecard_recommend_threshold_by_default(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "true"}, clear=False):
            with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_THRESHOLD": ""}, clear=False):
                agent.start_session()
                items = agent.collect_candidates(
                    "qa_test_engineer_v1",
                    1,
                    search_mode="recommend",
                    max_pages=1,
                )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].evidence_map["auto_greet_threshold"], 57.62)
        self.assertEqual(items[0].evidence_map["auto_greet_threshold_source"], "scorecard.recommend_min")
        self.assertTrue(items[0].evidence_map["auto_greet_attempted"])
        self.assertTrue(items[0].evidence_map["auto_greet_clicked"])
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

    def test_recommend_flow_search_config_threshold_overrides_scorecard_threshold(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(runtime=runtime, selectors=self._selectors(), extractor=FakeExtractor())
        self.addCleanup(agent.stop_session)
        with mock.patch.dict("os.environ", {"SCREENING_AUTO_GREET_ENABLED": "true", "SCREENING_AUTO_GREET_THRESHOLD": ""}, clear=False):
            agent.start_session()
            items = agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"auto_greet_threshold": 999},
                max_pages=1,
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].evidence_map["auto_greet_threshold"], 999.0)
        self.assertEqual(items[0].evidence_map["auto_greet_threshold_source"], "search_config")
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

    def test_recommend_flow_skips_existing_candidates_by_default(self):
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
            max_pages=1,
        )
        self.assertEqual(items, [])
        self.assertEqual(runtime.opened_ids, [])
        self.assertEqual(checker_calls, [(["recommend-001"], None)])

    def test_recommend_flow_skips_configured_external_ids_before_opening_detail(self):
        runtime = FakeRecommendRuntime()
        runtime.cards = [
            dict(runtime.cards[0]),
            {
                **runtime.cards[0],
                "external_id": "recommend-002",
                "name": "Candidate B",
                "card_index": 1,
            },
        ]
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
            search_config={"exclude_external_ids": ["recommend-001"], "skip_existing_candidates": False},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "recommend-002")
        self.assertEqual(runtime.opened_ids, ["recommend-002"])

    def test_recent_seen_external_ids_ignores_placeholder_playwright_ids(self):
        runtime = FakeRecommendRuntime()
        checker_calls = []

        def fake_checker(external_ids, *, max_age_hours=None):
            checker_calls.append((list(external_ids), max_age_hours))
            return set(external_ids)

        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
            existing_candidate_checker=fake_checker,
        )

        seen = agent._recent_seen_external_ids(
            [
                {"external_id": "playwright-2"},
                {"external_id": "playwright-fp-stable123"},
                {"external_id": "real-external-id"},
            ],
            {"skip_existing_candidates": True},
        )

        self.assertEqual(seen, {"playwright-fp-stable123", "real-external-id"})
        self.assertEqual(
            checker_calls,
            [(["playwright-fp-stable123", "real-external-id"], None)],
        )

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

    def test_recommend_flow_fails_fast_when_login_scan_is_visible(self):
        runtime = FakeRecommendRuntime()
        runtime.login_scan_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        with self.assertRaisesRegex(RuntimeError, "先在 9222"):
            agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"login_scan_wait_seconds": 15},
                max_pages=1,
            )
        self.assertEqual(runtime.login_scan_wait_calls, [])

    def test_recommend_flow_goes_directly_to_recommend_page_without_preparing_login_page(self):
        runtime = FakeRecommendRuntime()
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
            search_config={"login_scan_wait_seconds": 15},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(runtime.prepare_recommend_login_calls, [])
        self.assertEqual(runtime.events[:1], ["goto_recommend_page"])

    def test_recommend_flow_traces_recommend_ready_state(self):
        runtime = FakeRecommendRuntime()
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        trace_events = []
        agent.set_trace_logger(lambda event_type, payload: trace_events.append((event_type, payload)))
        agent.start_session()

        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            1,
            search_mode="recommend",
            max_pages=1,
        )

        self.assertEqual(len(items), 1)
        ready_event = next(payload for event_type, payload in trace_events if event_type == "recommend.list_ready")
        self.assertEqual(ready_event["ready_selector"], ".card-list")
        self.assertEqual(ready_event["frame_name"], "recommendFrame")
        self.assertEqual(ready_event["frame_url"], "https://www.zhipin.com/web/frame/recommend/mock")
        self.assertEqual(ready_event["card_count"], 1)

    def test_recommend_flow_collects_recommend_cards_once_per_page(self):
        runtime = FakeRecommendRuntime()
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
            search_config={"login_scan_wait_seconds": 15},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(runtime.collect_recommend_cards_calls, 2)

    def test_recommend_flow_fails_when_first_page_has_no_recommend_cards(self):
        runtime = FakeRecommendRuntime()
        runtime.cards = []
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()

        with self.assertRaisesRegex(RuntimeError, "No recommend candidate cards detected"):
            agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                max_pages=1,
            )

        self.assertEqual(runtime.collect_recommend_cards_calls, 2)

    def test_recommend_flow_recovers_same_page_when_detail_close_fails(self):
        runtime = FakeRecommendRuntime()
        runtime.cards = [
            {
                **runtime.cards[0],
                "external_id": "recommend-001",
                "name": "候选人A",
            },
            {
                **runtime.cards[0],
                "external_id": "recommend-002",
                "name": "候选人B",
            },
        ]
        runtime.close_recommend_detail_results = [False, True]
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            2,
            search_mode="recommend",
            max_pages=1,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(runtime.opened_ids, ["recommend-001", "recommend-002"])
        self.assertEqual(runtime.recover_recommend_list_calls, 1)
        self.assertEqual(runtime.next_page_calls, 0)
        self.assertEqual(runtime.collect_recommend_cards_calls, 4)

    def test_recommend_flow_processes_multiple_cards_even_with_same_external_id(self):
        runtime = FakeRecommendRuntime()
        runtime.cards = [
            {
                **runtime.cards[0],
                "external_id": "same-id",
                "name": "候选人A",
                "summary_text": "候选人A 5年测试经验 本科",
            },
            {
                **runtime.cards[0],
                "external_id": "same-id",
                "name": "候选人B",
                "summary_text": "候选人B 6年测试经验 本科",
            },
        ]
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        items = agent.collect_candidates(
            "qa_test_engineer_v1",
            2,
            search_mode="recommend",
            search_config={"login_scan_wait_seconds": 15},
            max_pages=1,
        )
        self.assertEqual(len(items), 2)
        self.assertEqual(runtime.collect_recommend_cards_calls, 3)

    def test_recommend_flow_raises_when_login_scan_is_still_visible(self):
        runtime = FakeRecommendRuntime()
        runtime.login_scan_active = True
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        agent.start_session()
        with self.assertRaisesRegex(RuntimeError, "先在 9222"):
            agent.collect_candidates(
                "qa_test_engineer_v1",
                1,
                search_mode="recommend",
                search_config={"login_scan_wait_seconds": 15},
                max_pages=1,
            )
        self.assertEqual(runtime.login_scan_wait_calls, [])

    def test_recommend_flow_enriches_phase2_scoring_payload(self):
        runtime = FakeRecommendRuntime()
        runtime.cards[0].update(
            {
                "name": "候选人Java",
                "current_title": "AI应用开发工程师",
                "location": "深圳",
                "summary_text": "6年 JAVA AI 应用开发经验，深圳，本科。",
            }
        )
        agent = PlaywrightLocalAgent(
            runtime=runtime,
            selectors=self._selectors(),
            extractor=FakeExtractor(),
        )
        self.addCleanup(agent.stop_session)
        captured_fields = {}

        def fake_score_candidate(job_id, fields):
            captured_fields["job_id"] = job_id
            captured_fields["fields"] = dict(fields)
            return ScoreResult(
                hard_filter_pass=True,
                hard_filter_fail_reasons=[],
                dimension_scores={},
                total_score=81.0,
                decision=CandidateDecision.RECOMMEND,
                review_reasons=[],
            )

        with mock.patch("src.screening.playwright_agent.score_candidate", side_effect=fake_score_candidate):
            agent.start_session()
            items = agent.collect_candidates(
                "phase2_custom_java_card",
                1,
                search_mode="recommend",
                max_pages=1,
            )

        self.assertEqual(len(items), 1)
        fields = captured_fields["fields"]
        self.assertEqual(captured_fields["job_id"], "phase2_custom_java_card")
        self.assertEqual(fields["current_title"], "AI应用开发工程师")
        self.assertEqual(fields["location"], "深圳")
        self.assertEqual(fields["city"], "深圳")
        self.assertEqual(fields["education_level"], "本科")
        self.assertEqual(fields["years_experience"], 5)
        self.assertIn("JAVA", fields["raw_summary"])
        self.assertIn("测试计划", fields["page_text"])

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

    def test_recommend_flow_does_not_wait_for_login_scan_in_direct_attach_mode(self):
        class BlockingLoginRuntime(FakeRecommendRuntime):
            def is_login_scan_page(self):
                return False

            def wait_for_login_scan(self, timeout_ms=15000, check_interval_ms=1500):
                self.login_scan_wait_calls.append((timeout_ms, check_interval_ms))
                return False

        runtime = BlockingLoginRuntime()
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
            search_config={"login_scan_wait_seconds": 15},
            max_pages=1,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(runtime.login_scan_wait_calls, [])
