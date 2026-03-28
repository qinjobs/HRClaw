import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening.boss_selectors import BossSelectors
from src.screening.browser_runtime import PlaywrightBrowserRuntime


class BrowserRuntimeConfigTests(unittest.TestCase):
    def test_storage_state_defaults_to_auth_directory(self):
        runtime = PlaywrightBrowserRuntime()
        self.assertTrue(str(runtime.storage_state_path).endswith("data/auth/boss_storage_state.json"))

    def test_runtime_can_skip_loading_saved_storage_state(self):
        runtime = PlaywrightBrowserRuntime(load_storage_state=False)
        self.assertFalse(runtime.load_storage_state)

    def test_runtime_can_skip_persisting_storage_state_on_stop(self):
        runtime = PlaywrightBrowserRuntime(persist_storage_state_on_stop=False)
        runtime._context = mock.Mock()
        runtime._browser = mock.Mock()
        runtime._playwright = mock.Mock()
        with mock.patch.object(runtime, "save_storage_state") as save_mock:
            runtime.stop()
        save_mock.assert_not_called()

    def test_storage_state_path_can_be_overridden_by_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom_state.json"
            original = os.environ.get("SCREENING_BROWSER_STORAGE_STATE_PATH")
            os.environ["SCREENING_BROWSER_STORAGE_STATE_PATH"] = str(custom_path)
            try:
                runtime = PlaywrightBrowserRuntime()
                self.assertEqual(runtime.storage_state_path, custom_path)
            finally:
                if original is None:
                    os.environ.pop("SCREENING_BROWSER_STORAGE_STATE_PATH", None)
                else:
                    os.environ["SCREENING_BROWSER_STORAGE_STATE_PATH"] = original

    def test_goto_recommend_page_enters_chat_then_clicks_recommend_menu(self):
        runtime = PlaywrightBrowserRuntime()
        selectors = BossSelectors(
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
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/user/?ka=header-login"

        def fake_goto(url, wait_until="domcontentloaded"):
            page.url = url

        page.goto.side_effect = fake_goto
        runtime._page = page
        with mock.patch.object(runtime, "_open_recommend_from_chat_menu", return_value=True) as open_menu:
            result = runtime.goto_recommend_page(selectors)
        page.goto.assert_called_once_with("https://www.zhipin.com/web/chat/index", wait_until="domcontentloaded")
        page.wait_for_timeout.assert_called_once_with(400)
        open_menu.assert_called_once_with(selectors)
        self.assertEqual(result, "https://www.zhipin.com/web/chat/index")

    def test_goto_recommend_page_falls_back_to_direct_url_when_menu_click_fails(self):
        runtime = PlaywrightBrowserRuntime()
        selectors = BossSelectors(
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
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/index"
        runtime._page = page
        with mock.patch.object(runtime, "_open_recommend_from_chat_menu", return_value=False) as open_menu, mock.patch.object(
            runtime,
            "goto",
            return_value=selectors.recommend_url,
        ) as goto_mock:
            result = runtime.goto_recommend_page(selectors)
        open_menu.assert_called_once_with(selectors)
        goto_mock.assert_called_once_with(selectors.recommend_url)
        self.assertEqual(result, selectors.recommend_url)

    def test_extract_external_id_uses_stable_fingerprint_when_dom_id_missing(self):
        runtime = PlaywrightBrowserRuntime()
        scope = mock.Mock()
        scope.get_attribute.return_value = None
        scope.evaluate.return_value = []
        external_id = runtime._extract_external_id(
            scope,
            ("[data-id]",),
            None,
            1,
            fallback_text="娄鑫龙 YY直播 测试工程师 约3年5个月测试经验",
        )
        self.assertTrue(external_id.startswith("playwright-fp-"))
        self.assertNotEqual(external_id, "playwright-1")
        self.assertEqual(
            external_id,
            runtime._extract_external_id(
                scope,
                ("[data-id]",),
                None,
                99,
                fallback_text="娄鑫龙 YY直播 测试工程师 约3年5个月测试经验",
            ),
        )
