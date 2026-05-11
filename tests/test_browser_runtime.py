import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.screening.boss_selectors import BossSelectors
from src.screening.browser_runtime import BrowserRuntimeError, PlaywrightBrowserRuntime


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

    def test_runtime_can_attach_to_existing_chrome_via_cdp(self):
        runtime = PlaywrightBrowserRuntime(cdp_url="http://127.0.0.1:9222")
        existing_page = mock.Mock()
        existing_page.url = "https://www.zhipin.com/web/chat/index"
        attached_context = mock.Mock()
        attached_context.pages = [mock.Mock(url="about:blank"), existing_page]
        attached_browser = mock.Mock()
        attached_browser.contexts = [attached_context]
        chromium = mock.Mock()
        chromium.connect_over_cdp.return_value = attached_browser
        playwright = mock.Mock()
        playwright.chromium = chromium

        with mock.patch("src.screening.browser_runtime.sync_playwright") as sync_playwright_mock:
            sync_playwright_mock.return_value.start.return_value = playwright
            session_id = runtime.start()

        self.assertIsNotNone(session_id)
        chromium.connect_over_cdp.assert_called_once()
        connect_target = chromium.connect_over_cdp.call_args.args[0]
        self.assertTrue(str(connect_target).startswith(("http://127.0.0.1:9222", "ws://127.0.0.1:9222/")))
        chromium.launch.assert_not_called()
        self.assertIs(runtime._page, existing_page)
        self.assertFalse(runtime._owns_page)
        self.assertEqual(runtime.current_url, "https://www.zhipin.com/web/chat/index")

        runtime.stop()
        existing_page.close.assert_not_called()
        attached_context.close.assert_not_called()
        attached_browser.close.assert_not_called()
        playwright.stop.assert_called_once()

    def test_runtime_normalizes_localhost_cdp_url_to_loopback(self):
        self.assertEqual(
            PlaywrightBrowserRuntime._normalize_cdp_url("http://localhost:9223"),
            "http://127.0.0.1:9223",
        )
        self.assertEqual(
            PlaywrightBrowserRuntime._normalize_cdp_url("ws://localhost:9223/devtools/browser/abc"),
            "ws://127.0.0.1:9223/devtools/browser/abc",
        )

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
        with mock.patch.object(runtime, "_open_recommend_from_chat_menu", return_value=True) as open_menu, mock.patch.object(
            runtime,
            "wait_for_recommend_list_ready",
            return_value=True,
        ):
            result = runtime.goto_recommend_page(selectors)
        page.goto.assert_called_once_with("https://www.zhipin.com/web/chat/index", wait_until="domcontentloaded")
        page.wait_for_timeout.assert_called_once_with(400)
        open_menu.assert_called_once_with(selectors)
        self.assertEqual(result, "https://www.zhipin.com/web/chat/index")

    def test_prepare_recommend_login_opens_new_page_when_attached_to_fixed_9222(self):
        runtime = PlaywrightBrowserRuntime(cdp_url="http://127.0.0.1:9222")
        current_page = mock.Mock()
        current_page.url = "https://www.zhipin.com/"
        login_page = mock.Mock()
        login_page.url = "about:blank"

        def fake_login_goto(url, wait_until="domcontentloaded"):
            login_page.url = url

        login_page.goto.side_effect = fake_login_goto
        context = mock.Mock()
        context.new_page.return_value = login_page
        runtime._context = context
        runtime._page = current_page
        runtime.attached_to_existing_browser = True

        result = runtime.prepare_recommend_login(wait_timeout_ms=15000)

        context.new_page.assert_called_once_with()
        login_page.bring_to_front.assert_called_once_with()
        login_page.goto.assert_called_once_with(
            "https://www.zhipin.com/web/user/?ka=header-login",
            wait_until="domcontentloaded",
        )
        login_page.wait_for_timeout.assert_called_once_with(15000)
        self.assertIs(runtime._page, login_page)
        self.assertTrue(runtime._owns_page)
        self.assertTrue(result["opened"])
        self.assertTrue(result["waited"])
        self.assertFalse(result["reused_current_page"])

    def test_prepare_recommend_login_is_noop_without_fixed_9222_attach(self):
        runtime = PlaywrightBrowserRuntime(cdp_url="http://127.0.0.1:9333")
        runtime.attached_to_existing_browser = True

        result = runtime.prepare_recommend_login(wait_timeout_ms=15000)

        self.assertEqual(
            result,
            {"opened": False, "waited": False, "reason": "cdp_9222_not_attached"},
        )

    def test_prepare_recommend_login_does_not_refresh_when_already_on_login_url(self):
        runtime = PlaywrightBrowserRuntime(cdp_url="http://127.0.0.1:9222")
        login_page = mock.Mock()
        login_page.url = "https://www.zhipin.com/web/user/?ka=header-login"
        context = mock.Mock()
        context.new_page.return_value = login_page
        runtime._context = context
        runtime.attached_to_existing_browser = True

        result = runtime.prepare_recommend_login(wait_timeout_ms=15000)

        context.new_page.assert_called_once_with()
        login_page.bring_to_front.assert_called_once_with()
        login_page.goto.assert_not_called()
        login_page.wait_for_timeout.assert_called_once_with(15000)
        self.assertTrue(result["opened"])
        self.assertTrue(result["waited"])
        self.assertFalse(result["reused_current_page"])

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
        ) as goto_mock, mock.patch.object(
            runtime,
            "wait_for_recommend_list_ready",
            return_value=True,
        ):
            result = runtime.goto_recommend_page(selectors)
        open_menu.assert_called_once_with(selectors)
        goto_mock.assert_called_once_with(selectors.recommend_url)
        self.assertEqual(result, selectors.recommend_url)

    def test_goto_recommend_page_reuses_existing_recommend_tab_before_navigating(self):
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
        current_page = mock.Mock()
        current_page.url = "https://www.zhipin.com/web/user/?ka=header-login"
        recommend_page = mock.Mock()
        recommend_page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = current_page
        runtime._context = mock.Mock()
        runtime._context.pages = [current_page, recommend_page]

        with mock.patch.object(runtime, "_find_existing_recommend_page", return_value=recommend_page) as find_mock, mock.patch.object(
            runtime,
            "_open_recommend_from_chat_menu",
            return_value=False,
        ) as open_menu, mock.patch.object(
            runtime,
            "goto",
            return_value=selectors.recommend_url,
        ) as goto_mock:
            result = runtime.goto_recommend_page(selectors)

        self.assertIs(runtime._page, recommend_page)
        recommend_page.bring_to_front.assert_called_once_with()
        current_page.goto.assert_not_called()
        find_mock.assert_called()
        open_menu.assert_not_called()
        goto_mock.assert_not_called()
        self.assertEqual(result, recommend_page.url)

    def test_wait_for_recommend_list_ready_requires_real_cards(self):
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
        scope = mock.Mock()
        runtime._page = mock.Mock()

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=scope), mock.patch.object(
            runtime,
            "_wait_for_any",
            return_value=".card-list",
        ), mock.patch.object(
            runtime,
            "_recommend_card_count_for_scope",
            return_value=0,
            create=True,
        ), mock.patch.object(
            runtime,
            "_reuse_existing_recommend_page",
            return_value=False,
        ):
            result = runtime.wait_for_recommend_list_ready(selectors, timeout_ms=1000)

        self.assertIsNone(result)

    def test_go_to_next_recommend_page_uses_recommend_scope(self):
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
        scope = mock.Mock()
        button = mock.Mock()
        button.get_attribute.return_value = None
        locator = mock.Mock()
        locator.first = button

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=scope) as resolve_mock, mock.patch.object(
            runtime,
            "_locator_for_any",
            return_value=locator,
        ) as locator_mock, mock.patch.object(runtime, "_wait_for_any") as wait_mock:
            result = runtime.go_to_next_recommend_page(selectors)

        self.assertTrue(result)
        resolve_mock.assert_called_once_with(selectors)
        locator_mock.assert_called_once_with(selectors.next_page, scope=scope)
        wait_mock.assert_called_once_with(
            selectors.recommend_list_ready + selectors.list_ready,
            timeout_ms=15000,
            scope=scope,
        )
        button.click.assert_called_once_with()

    def test_open_recommend_candidate_raises_when_detail_never_opens(self):
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
        runtime._page = page
        scope = mock.Mock()
        card_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card_scope

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=False,
        ), mock.patch.object(runtime, "_wait_for_any_global", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ):
            with self.assertRaisesRegex(BrowserRuntimeError, "detail did not open"):
                runtime.open_recommend_candidate({"card_index": 0}, selectors)

    def test_open_recommend_candidate_waits_for_global_recommend_detail(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        scope = mock.Mock()
        card_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card_scope
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "signature": "张三 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=False,
        ), mock.patch.object(runtime, "_wait_for_any_global", return_value="div.dialog-wrap.active") as wait_global, mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, ready_state],
        ):
            result = runtime.open_recommend_candidate({"card_index": 0}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        wait_global.assert_called()

    def test_open_recommend_candidate_prefers_resume_link_before_clicking_card(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        scope = mock.Mock()
        card_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card_scope
        link_first = mock.Mock()
        link_locator = mock.Mock()
        link_locator.first = link_first
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "signature": "吴国伟 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[link_locator],
        ), mock.patch.object(runtime, "_wait_for_any_global", return_value="div.dialog-wrap.active"), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, ready_state],
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "吴国伟"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        link_first.click.assert_called_once_with(timeout=5000)
        card_scope.click.assert_not_called()

    def test_open_recommend_candidate_uses_resume_hotspot_before_clicking_card(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        card_scope = mock.Mock()
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": True,
            "signature": "吴国伟 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=True,
        ) as hotspot_click, mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=False,
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "吴国伟"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        hotspot_click.assert_called_once_with(card_scope)
        card_scope.click.assert_not_called()

    def test_open_recommend_candidate_recovers_when_card_scope_temporarily_missing(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        card_scope = mock.Mock()
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": False,
            "has_resume_frame": True,
            "signature": "张三 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            side_effect=[None, card_scope],
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=True,
        ) as recover_mock, mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=True,
        ) as hotspot_click, mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, ready_state],
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        recover_mock.assert_called_once()
        hotspot_click.assert_called_once_with(card_scope)

    def test_open_recommend_candidate_treats_resume_iframe_as_opened(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        card_scope = mock.Mock()
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        iframe_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": False,
            "has_resume_frame": True,
            "signature": None,
            "content_ready": False,
        }
        detail_state_calls = {"count": 0}

        def fake_detail_state(*_args, **_kwargs):
            detail_state_calls["count"] += 1
            if detail_state_calls["count"] == 1:
                return before_state
            return iframe_state

        clock = {"value": 0.0}

        def fake_monotonic():
            clock["value"] += 0.5
            return clock["value"]

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=True,
        ) as hotspot_click, mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_active_recommend_dialog_locator",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=fake_detail_state,
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=False,
        ), mock.patch(
            "src.screening.browser_runtime.time.monotonic",
            side_effect=fake_monotonic,
        ):
            with self.assertRaisesRegex(BrowserRuntimeError, "detail did not open"):
                runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        hotspot_click.assert_called_once_with(card_scope)

    def test_recommend_detail_state_treats_resume_iframe_as_content_ready(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        with mock.patch.object(runtime, "_active_recommend_dialog_locator", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_find_recommend_resume_iframe_target",
            return_value=(mock.Mock(), mock.Mock(), {"width": 774, "height": 3340}),
        ), mock.patch.object(
            runtime,
            "_recommend_detail_signature",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_has_recommend_resume_frame",
            return_value=True,
        ):
            state = runtime._recommend_detail_state(selectors)

        self.assertTrue(state["has_resume_frame"])
        self.assertTrue(state["content_ready"])

    def test_open_recommend_candidate_does_not_treat_stale_detail_as_opened(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        scope = mock.Mock()
        card_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card_scope
        link_first = mock.Mock()
        link_locator = mock.Mock()
        link_locator.first = link_first
        stale_dialog_root = mock.Mock()
        stale_dialog_root.inner_text.return_value = "王小银 打招呼 经历概览"
        stale_dialog = mock.Mock()
        stale_dialog.first = stale_dialog_root
        stale_dialog.count.return_value = 1

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[link_locator],
        ), mock.patch.object(runtime, "_wait_for_any_global", return_value="div.dialog-wrap.active"), mock.patch.object(
            runtime,
            "_active_recommend_dialog_locator",
            return_value=stale_dialog,
        ), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch(
            "src.screening.browser_runtime.time.monotonic",
            side_effect=[0.0, 20.0, 20.1, 40.0, 40.1, 60.0, 60.1, 80.0],
        ):
            with self.assertRaisesRegex(BrowserRuntimeError, "detail did not open"):
                runtime.open_recommend_candidate({"card_index": 0, "name": "吴国伟"}, selectors)
        card_scope.click.assert_not_called()

    def test_open_recommend_candidate_waits_past_loading_placeholder(self):
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
            recommend_detail_ready=("div.dialog-wrap.active",),
        )
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = page
        scope = mock.Mock()
        card_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card_scope
        link_first = mock.Mock()
        link_locator = mock.Mock()
        link_locator.first = link_first

        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        loading_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": False,
            "has_resume_frame": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "signature": "张三 产品经理 5年经验 本科",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "_resolve_recommend_card_scope", return_value=card_scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[link_locator],
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, loading_state, ready_state],
        ), mock.patch(
            "src.screening.browser_runtime.time.monotonic",
            side_effect=[0.0, 0.0, 0.1, 0.2, 0.3],
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        link_first.click.assert_called_once_with(timeout=5000)

    def test_close_recommend_detail_does_not_press_escape_when_no_dialog_found(self):
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
        page.locator.return_value.count.return_value = 0
        runtime._page = page

        with mock.patch.object(runtime, "_locator_for_any_global", return_value=None):
            result = runtime.close_recommend_detail(selectors)

        self.assertTrue(result)
        page.keyboard.press.assert_not_called()

    def test_close_recommend_detail_uses_global_active_dialog_presence(self):
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
        page.locator.return_value.count.return_value = 0
        runtime._page = page
        active_dialog = mock.Mock()
        active_dialog.count.side_effect = [1, 0]

        def locator_global_side_effect(selectors_arg):
            if selectors_arg == selectors.recommend_close_button:
                return None
            return active_dialog

        with mock.patch.object(runtime, "_locator_for_any_global", side_effect=locator_global_side_effect):
            result = runtime.close_recommend_detail(selectors)

        self.assertTrue(result)
        page.keyboard.press.assert_called_once_with("Escape")

    def test_collect_recommend_cards_switches_to_existing_recommend_tab_when_current_page_is_empty(self):
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
        current_page = mock.Mock()
        current_page.url = "https://www.zhipin.com/web/chat/recommend"
        fallback_page = mock.Mock()
        fallback_page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page = current_page
        runtime._context = mock.Mock()
        runtime._context.pages = [current_page, fallback_page]

        fallback_scope = mock.Mock()
        card = mock.Mock()
        card.inner_text.return_value = "张三 测试工程师 5年经验 本科 深圳 产品经理 打招呼"
        card.get_attribute.return_value = None
        card.evaluate.return_value = []
        card_locator = mock.Mock()
        card_locator.count.return_value = 1
        card_locator.nth.return_value = card

        def locator_side_effect(selectors_arg, *, scope=None):
            if scope is current_page:
                return None
            if scope is fallback_scope:
                return card_locator
            return None

        with mock.patch.object(runtime, "_find_existing_recommend_page", return_value=fallback_page), mock.patch.object(
            runtime,
            "_resolve_recommend_scope",
            side_effect=[current_page, fallback_scope],
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=locator_side_effect,
        ):
            items = runtime.collect_recommend_cards(selectors, 10)

        self.assertEqual(len(items), 1)
        self.assertIs(runtime._page, fallback_page)
        fallback_page.bring_to_front.assert_called_once_with()

    def test_collect_recommend_cards_skips_blank_placeholders_and_scans_deeper(self):
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
        scope = mock.Mock()
        cards = []
        for text in [
            "张三 10-20K 3年 产品经理 本科 打招呼",
            "",
            "",
            "李四 15-25K 5年 AI产品经理 硕士 打招呼",
            "王五 12-18K 4年 产品经理 本科 打招呼",
        ]:
            card = mock.Mock()
            card.inner_text.return_value = text
            cards.append(card)
        card_locator = mock.Mock()
        card_locator.count.return_value = len(cards)
        card_locator.nth.side_effect = lambda index: cards[index]

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            return_value=card_locator,
        ), mock.patch.object(
            runtime,
            "_expand_cards_by_scrolling",
        ), mock.patch.object(
            runtime,
            "_attribute_from_scope",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_text_from_scope",
            return_value=None,
        ):
            items = runtime.collect_recommend_cards(selectors, 2)

        self.assertEqual(len(items), 2)
        self.assertEqual([item["card_index"] for item in items], [0, 3])
        self.assertTrue(items[0]["summary_text"])
        self.assertTrue(items[1]["summary_text"])

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


class BrowserRuntimeMarkdownTests(unittest.TestCase):
    def test_cleanup_resume_text_removes_known_noise_lines(self):
        raw = "收藏\n不合适\n举报\n转发牛人\n打招呼\n\n5年Java经验\n本科"
        cleaned = PlaywrightBrowserRuntime._cleanup_resume_text(raw)
        self.assertEqual(cleaned, "5年Java经验\n本科")

    def test_cleanup_resume_text_removes_noise_fragments(self):
        raw = "同事沟通 我的沟通\nTa向 张三 发起沟通\n5年Java经验\n本科"
        cleaned = PlaywrightBrowserRuntime._cleanup_resume_text(raw)
        self.assertEqual(cleaned, "5年Java经验\n本科")

    def test_build_resume_markdown_prefers_cleaned_html(self):
        runtime = PlaywrightBrowserRuntime()
        body = runtime._build_resume_markdown_body(
            "收藏\n打招呼\n5年Java经验",
            content_html="""
            <div class="resume-detail-wrap">
              <div class="button-list"><button>打招呼</button></div>
              <h2>候选人经历</h2>
              <p>5年Java经验</p>
              <ul><li>Spring Boot</li><li>AI应用开发</li></ul>
            </div>
            """,
        )
        self.assertIn("5年Java经验", body)
        self.assertNotIn("打招呼", body)

    def test_build_resume_markdown_falls_back_to_clean_text_when_html_unavailable(self):
        runtime = PlaywrightBrowserRuntime()
        body = runtime._build_resume_markdown_body("收藏\n举报\n本科\n3年经验")
        self.assertEqual(body, "本科\n3年经验")

    def test_resume_content_bonus_prefers_resume_panel_over_related_candidates(self):
        resume_score = PlaywrightBrowserRuntime._resume_content_bonus(
            ".iboss-left",
            "个人简介\n工作经历\n项目经历\n期望职位",
        )
        related_score = PlaywrightBrowserRuntime._resume_content_bonus(
            "main",
            "其他名校毕业的牛人\n邓**\n陈**",
        )
        self.assertGreater(resume_score, related_score)

    def test_resume_detail_selectors_excludes_main_and_body_fallbacks(self):
        runtime = PlaywrightBrowserRuntime()
        selectors = runtime._resume_detail_selectors()
        self.assertNotIn("main", selectors)
        self.assertNotIn("body", selectors)
        self.assertNotIn("div.resume-detail-wrap", selectors)
        self.assertNotIn("div.card-content", selectors)

    def test_resume_screenshot_bytes_prefers_resume_target_over_page_full_capture(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.screenshot.return_value = b"page-shot"
        target = (mock.Mock(), mock.Mock(), {"client_height": 400, "scroll_height": 1200})
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=target), mock.patch.object(
            runtime,
            "_capture_resume_scrollable_panel",
            return_value=b"resume-shot",
        ) as capture_mock:
            screenshot = runtime._resume_screenshot_bytes()
        capture_mock.assert_called_once_with(target=target)
        runtime._page.screenshot.assert_not_called()
        self.assertEqual(screenshot, b"resume-shot")

    def test_resume_screenshot_bytes_raises_when_resume_target_missing(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_capture_resume_dialog_left_clip",
            return_value=b"dialog-clip",
        ):
            self.assertEqual(runtime._resume_screenshot_bytes(), b"dialog-clip")

    def test_resume_screenshot_bytes_falls_back_to_dialog_panel_target_when_resume_target_missing(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        dialog_target = (mock.Mock(), mock.Mock(), {"client_height": 320, "scroll_height": 960})
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=dialog_target,
        ), mock.patch.object(
            runtime,
            "_capture_resume_scrollable_panel",
            return_value=b"dialog-resume-shot",
        ) as capture_mock:
            screenshot = runtime._resume_screenshot_bytes()
        capture_mock.assert_called_once_with(target=dialog_target)
        self.assertEqual(screenshot, b"dialog-resume-shot")

    def test_resume_screenshot_bytes_falls_back_to_page_capture_when_targets_missing(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.url = "https://www.zhipin.com/web/chat/search"
        runtime._page.screenshot.return_value = b"page-shot"
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_capture_resume_dialog_left_clip",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_prepare_long_resume_capture",
        ) as prepare_mock, mock.patch.object(
            runtime,
            "_restore_scroll_after_capture",
        ) as restore_mock:
            screenshot = runtime._resume_screenshot_bytes()
        prepare_mock.assert_called_once_with()
        restore_mock.assert_called_once_with()
        runtime._page.screenshot.assert_called_once_with(type="png", full_page=True)
        self.assertEqual(screenshot, b"page-shot")

    def test_resume_screenshot_bytes_falls_back_to_page_capture_on_recommend_page_when_targets_missing(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.url = "https://www.zhipin.com/web/chat/recommend"
        runtime._page.screenshot.return_value = b"page-shot"
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_capture_resume_dialog_left_clip",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_has_recommend_resume_frame",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_prepare_long_resume_capture",
        ) as prepare_mock, mock.patch.object(
            runtime,
            "_restore_scroll_after_capture",
        ) as restore_mock:
            screenshot = runtime._resume_screenshot_bytes()
        prepare_mock.assert_called_once_with()
        restore_mock.assert_called_once_with()
        runtime._page.screenshot.assert_called_once_with(type="png", full_page=True)
        self.assertEqual(screenshot, b"page-shot")

    def test_resume_screenshot_bytes_falls_back_to_active_recommend_dialog_when_targets_missing(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.url = "https://www.zhipin.com/web/chat/recommend"
        dialog_first = mock.Mock()
        dialog_first.screenshot.return_value = b"dialog-shot"
        dialog = mock.Mock()
        dialog.count.return_value = 1
        dialog.first = dialog_first
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_capture_resume_dialog_left_clip",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_active_recommend_dialog_locator",
            return_value=dialog,
        ), mock.patch.object(
            runtime,
            "_has_recommend_resume_frame",
            return_value=True,
        ):
            screenshot = runtime._resume_screenshot_bytes()
        dialog_first.screenshot.assert_called_once_with(type="png")
        self.assertEqual(screenshot, b"dialog-shot")

    def test_resume_screenshot_bytes_prefers_recommend_resume_iframe_when_present(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.url = "https://www.zhipin.com/web/chat/recommend"
        iframe_locator = mock.Mock()
        iframe_locator.screenshot.return_value = b"iframe-shot"
        iframe_target = (mock.Mock(), iframe_locator, {"width": 774, "height": 3340})
        with mock.patch.object(runtime, "_find_resume_content_target", return_value=None), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_capture_resume_dialog_left_clip",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_find_recommend_resume_iframe_target",
            return_value=iframe_target,
        ):
            screenshot = runtime._resume_screenshot_bytes()
        iframe_locator.screenshot.assert_called_once_with(type="png")
        self.assertEqual(screenshot, b"iframe-shot")

    def test_find_recommend_resume_iframe_target_accepts_iframe_without_bounding_box(self):
        runtime = PlaywrightBrowserRuntime()
        page = mock.Mock()
        page.url = "https://www.zhipin.com/web/chat/recommend"
        page.locator.return_value.count.return_value = 0
        recommend_frame = mock.Mock()
        recommend_frame.url = "https://www.zhipin.com/web/frame/recommend/?jobid=1"
        iframe = mock.Mock()
        iframe.bounding_box.return_value = None
        iframe.get_attribute.return_value = "/web/frame/c-resume/?source=recommend"
        locator = mock.Mock()
        locator.count.return_value = 1
        locator.nth.return_value = iframe
        recommend_frame.locator.return_value = locator
        page.frames = [recommend_frame]
        runtime._page = page

        result = runtime._find_recommend_resume_iframe_target()

        self.assertIsNotNone(result)
        _root, found, metrics = result
        self.assertIs(found, iframe)
        self.assertEqual(metrics["width"], 0)
        self.assertEqual(metrics["height"], 0)

    def test_render_resume_markdown_can_use_screenshot_ocr(self):
        runtime = PlaywrightBrowserRuntime()
        with mock.patch.object(runtime, "_ocr_resume_markdown_from_image", return_value="个人简介\n5年Java经验"), mock.patch.object(
            runtime,
            "_merge_scroll_html_fragments_to_markdown",
            return_value=None,
        ), mock.patch.object(runtime, "_clean_resume_html_fragment", return_value=None), mock.patch.object(
            runtime,
            "_readability_resume_html",
            return_value=None,
        ):
            body = runtime._render_resume_html_to_markdown(screenshot_path="/tmp/fake.png")
        self.assertEqual(body, "个人简介\n5年Java经验")
