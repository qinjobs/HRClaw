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

    def test_wait_for_recommend_list_ready_rejects_null_jobid_frame(self):
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
            return_value=".candidate-recommend",
        ), mock.patch.object(
            runtime,
            "_recommend_card_count_for_scope",
            return_value=1,
            create=True,
        ), mock.patch.object(
            runtime,
            "_recommend_scope_info",
            return_value={
                "frame_name": "recommendFrame",
                "frame_url": "https://www.zhipin.com/web/frame/recommend/?jobid=null&status=0&version=9921",
            },
        ), mock.patch.object(
            runtime,
            "_reuse_existing_recommend_page",
            return_value=False,
        ):
            result = runtime.wait_for_recommend_list_ready(selectors, timeout_ms=1000)

        self.assertIsNone(result)

    def test_resolve_recommend_card_scope_falls_back_to_index_when_identity_no_longer_matches_index(self):
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
        card_scope_a = mock.Mock(name="card_scope_a")
        card_scope_b = mock.Mock(name="card_scope_b")
        card_locator = mock.Mock()
        card_locator.count.return_value = 2
        card_locator.nth.side_effect = lambda index: [card_scope_a, card_scope_b][index]

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=mock.Mock()), mock.patch.object(
            runtime,
            "_recommend_card_locator",
            return_value=card_locator,
        ), mock.patch.object(
            runtime,
            "_recommend_card_matches",
            return_value=False,
        ):
            result = runtime._resolve_recommend_card_scope(
                selectors,
                {
                    "card_index": 0,
                    "external_id": "recommend-001",
                    "name": "候选人A",
                    "summary_text": "候选人A 摘要",
                },
            )

        self.assertIs(result, card_scope_a)

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
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            return_value=before_state,
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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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
            side_effect=[before_state, before_state, ready_state],
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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[link_locator],
        ), mock.patch.object(runtime, "_wait_for_any_global", return_value="div.dialog-wrap.active"), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, ready_state],
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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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
            side_effect=[before_state, before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=False,
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "吴国伟"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        hotspot_click.assert_called_once_with(card_scope)
        card_scope.click.assert_not_called()

    def test_open_recommend_candidate_does_not_recover_healthy_list_before_card_click(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": "吴国伟 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_dispatch_recommend_card_click",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "_click_locator",
            return_value=True,
        ) as click_mock, mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=True,
        ) as recover_mock:
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "吴国伟"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        self.assertGreaterEqual(click_mock.call_count, 1)
        recover_mock.assert_not_called()

    def test_click_recommend_resume_hotspot_prefers_plain_name_click(self):
        runtime = PlaywrightBrowserRuntime()
        card_scope = mock.Mock()
        name_target = mock.Mock()
        name_locator = mock.Mock()
        name_locator.first = name_target

        with mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[name_locator],
        ), mock.patch.object(
            runtime,
            "_click_locator",
            return_value=True,
        ) as click_locator:
            result = runtime._click_recommend_resume_hotspot(card_scope)

        self.assertTrue(result)
        name_target.scroll_into_view_if_needed.assert_called_once_with(timeout=2000)
        click_locator.assert_called_once_with(name_target, timeout_ms=5000)

    def test_click_recommend_resume_hotspot_falls_back_to_card_click_positions(self):
        runtime = PlaywrightBrowserRuntime()
        card_scope = mock.Mock()

        with mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None, None, None, None, None, None, None],
        ), mock.patch.object(
            runtime,
            "_click_locator",
            side_effect=[False, False, True],
        ) as click_locator:
            result = runtime._click_recommend_resume_hotspot(card_scope)

        self.assertTrue(result)
        self.assertEqual(click_locator.call_args_list[0], mock.call(card_scope, timeout_ms=5000))
        self.assertEqual(
            click_locator.call_args_list[1],
            mock.call(card_scope, timeout_ms=5000, position={"x": 160, "y": 40}),
        )
        self.assertEqual(
            click_locator.call_args_list[2],
            mock.call(card_scope, timeout_ms=5000, position={"x": 120, "y": 36}),
        )

    def test_click_recommend_resume_hotspot_tries_upper_left_block_before_card_scope_fallback(self):
        runtime = PlaywrightBrowserRuntime()
        card_scope = mock.Mock()
        upper_left_target = mock.Mock()
        upper_left_locator = mock.Mock()
        upper_left_locator.first = upper_left_target

        with mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None, upper_left_locator, None, None, None, None, None],
        ), mock.patch.object(
            runtime,
            "_click_locator",
            side_effect=[False, True],
        ) as click_locator:
            result = runtime._click_recommend_resume_hotspot(card_scope)

        self.assertTrue(result)
        upper_left_target.scroll_into_view_if_needed.assert_called_once_with(timeout=2000)
        self.assertEqual(click_locator.call_args_list[0], mock.call(upper_left_target, timeout_ms=5000))
        self.assertEqual(
            click_locator.call_args_list[1],
            mock.call(upper_left_target, timeout_ms=5000, position={"x": 32, "y": 24}),
        )

    def test_click_recommend_resume_hotspot_prefers_upper_left_block_before_col2(self):
        runtime = PlaywrightBrowserRuntime()
        card_scope = mock.Mock()
        seen_selector_groups = []
        upper_left_target = mock.Mock()
        upper_left_locator = mock.Mock()
        upper_left_locator.first = upper_left_target
        col2_locator = mock.Mock()
        col2_locator.first = mock.Mock()

        def fake_locator_for_any(selectors, *, scope=None):
            seen_selector_groups.append(tuple(selectors))
            if ":scope > div:first-child" in selectors:
                return upper_left_locator
            if selectors == (".col-2",):
                return col2_locator
            return None

        with mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=fake_locator_for_any,
        ), mock.patch.object(
            runtime,
            "_click_locator",
            return_value=True,
        ) as click_locator:
            result = runtime._click_recommend_resume_hotspot(card_scope)

        self.assertTrue(result)
        self.assertEqual(click_locator.call_args_list[0], mock.call(upper_left_target, timeout_ms=5000))
        self.assertIn((":scope > div:first-child", ":scope > div:first-child > div:first-child"), seen_selector_groups)
        self.assertNotIn((".col-2",), seen_selector_groups[:2])

    def test_open_recommend_candidate_uses_dom_dispatch_fallback_when_native_clicks_fail(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": "张三 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "_click_locator",
            side_effect=[False, False, False, False],
        ), mock.patch.object(
            runtime,
            "_dispatch_recommend_card_click",
            return_value=True,
        ) as dispatch_mock, mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=True,
        ) as recover_mock:
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        dispatch_mock.assert_called_once_with(card_scope)
        recover_mock.assert_not_called()

    def test_open_recommend_candidate_accepts_canvas_resume_frame_when_card_marks_viewed(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        resume_frame_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": False,
            "has_resume_frame": True,
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=True,
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, resume_frame_state],
        ), mock.patch.object(
            runtime,
            "_recommend_card_has_opened_state",
            return_value=True,
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=True,
        ) as recover_mock:
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "龚显铸"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        recover_mock.assert_not_called()

    def test_open_recommend_candidate_retries_hotspot_with_refreshed_scope(self):
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
        stale_scope = mock.Mock()
        fresh_scope = mock.Mock()
        before_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": "张三 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            side_effect=[stale_scope, fresh_scope],
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            side_effect=[False, True],
        ) as hotspot_mock, mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=False,
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        self.assertEqual(hotspot_mock.call_count, 2)
        self.assertEqual(hotspot_mock.call_args_list[0], mock.call(stale_scope))
        self.assertEqual(hotspot_mock.call_args_list[1], mock.call(fresh_scope))

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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
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
            side_effect=[before_state, before_state, ready_state],
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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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

        self.assertGreaterEqual(hotspot_click.call_count, 1)

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

    def test_recommend_card_matches_prefers_external_id_over_name(self):
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
        card_scope = mock.Mock()
        with mock.patch.object(
            runtime,
            "_recommend_card_identity",
            return_value={"external_id": "recommend-001", "name": "候选人A(已匿名)"},
        ):
            matched = runtime._recommend_card_matches(
                card_scope,
                selectors,
                {"external_id": "recommend-001", "name": "候选人A"},
            )

        self.assertTrue(matched)

    def test_resolve_recommend_card_scope_falls_back_to_current_index_when_identity_cannot_be_matched(self):
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
        nth_scope = mock.Mock()
        card_locator = mock.Mock()
        card_locator.count.return_value = 2
        card_locator.nth.return_value = nth_scope

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=scope), mock.patch.object(
            runtime,
            "_recommend_card_locator",
            return_value=card_locator,
        ), mock.patch.object(
            runtime,
            "_recommend_card_matches",
            return_value=False,
        ):
            resolved = runtime._resolve_recommend_card_scope(
                selectors,
                {"card_index": 1, "external_id": "recommend-001", "name": "候选人A"},
            )

        self.assertIs(resolved, nth_scope)

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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
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
            side_effect=[before_state, before_state, loading_state, ready_state],
        ), mock.patch(
            "src.screening.browser_runtime.time.monotonic",
            side_effect=[0.0, 0.0, 0.1, 0.2, 0.3],
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        link_first.click.assert_called_once_with(timeout=5000)

    def test_open_recommend_candidate_skips_preclose_when_list_state_is_already_clean(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": True,
            "has_resume_iframe": False,
            "signature": "张三 产品经理 5年经验 本科 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True) as close_mock, mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, ready_state],
        ), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=[None, None],
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            return_value=True,
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=False,
        ):
            result = runtime.open_recommend_candidate({"card_index": 0, "name": "张三"}, selectors)

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        close_mock.assert_not_called()

    def test_open_recommend_candidate_retries_when_opened_detail_does_not_match_card(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        mismatched_ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": True,
            "has_resume_iframe": False,
            "signature": "费晶茹 AI产品经理 2年经验 硕士 深圳",
            "content_ready": True,
        }
        matched_ready_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": True,
            "has_resume_iframe": False,
            "signature": "余定燊 产品经理 应届生 硕士 深圳",
            "content_ready": True,
        }

        with mock.patch.object(runtime, "close_recommend_detail", return_value=True) as close_mock, mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[
                before_state,
                before_state,
                mismatched_ready_state,
                mismatched_ready_state,
                before_state,
                matched_ready_state,
                matched_ready_state,
            ],
        ), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            side_effect=[card_scope, card_scope],
        ), mock.patch.object(
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
            "_recommend_detail_matches_card",
            side_effect=[False, True],
            create=True,
        ) as match_mock, mock.patch.object(
            runtime,
            "recover_recommend_list",
            return_value=True,
        ) as recover_mock:
            result = runtime.open_recommend_candidate(
                {"card_index": 1, "name": "余定燊", "external_id": "7b56caa4d06971920Xd92dW-EVpQ"},
                selectors,
            )

        self.assertEqual(result, "https://www.zhipin.com/web/chat/recommend")
        self.assertEqual(hotspot_click.call_count, 2)
        recover_mock.assert_not_called()
        self.assertGreaterEqual(close_mock.call_count, 1)
        self.assertEqual(match_mock.call_count, 2)

    def test_open_recommend_candidate_requires_live_detail_before_accepting_match(self):
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
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }
        opened_state = {
            "ready_visible": True,
            "has_dialog": True,
            "has_panel": True,
            "has_resume_frame": True,
            "has_resume_iframe": False,
            "signature": "候选人A 产品经理",
            "content_ready": True,
        }
        closed_state = {
            "ready_visible": False,
            "has_dialog": False,
            "has_panel": False,
            "has_resume_frame": False,
            "has_resume_iframe": False,
            "signature": None,
            "content_ready": False,
        }

        with mock.patch.object(
            runtime,
            "_recommend_detail_state",
            side_effect=[before_state, before_state, opened_state, closed_state],
        ), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_click_recommend_resume_hotspot",
            side_effect=[True, False, False],
        ), mock.patch.object(
            runtime,
            "_wait_for_any_global",
            return_value="div.dialog-wrap.active",
        ), mock.patch.object(
            runtime,
            "_recommend_detail_matches_card",
            return_value=True,
        ), mock.patch.object(
            runtime,
            "_click_locator",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_dispatch_recommend_card_click",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_recommend_list_looks_healthy",
            return_value=True,
        ):
            with self.assertRaisesRegex(BrowserRuntimeError, "detail did not open"):
                runtime.open_recommend_candidate(
                    {"card_index": 0, "name": "候选人A", "external_id": "recommend-001"},
                    selectors,
                )

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

        with mock.patch.object(runtime, "_locator_for_any_global", side_effect=locator_global_side_effect), mock.patch.object(
            runtime,
            "_has_active_recommend_dialog",
            side_effect=[True, False],
        ), mock.patch.object(
            runtime,
            "_has_inline_recommend_detail",
            return_value=False,
        ):
            result = runtime.close_recommend_detail(selectors)

        self.assertTrue(result)
        page.keyboard.press.assert_called_once_with("Escape")

    def test_close_recommend_detail_does_not_reload_for_stale_resume_frame_only(self):
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
        runtime._page = page

        with mock.patch.object(runtime, "_locator_for_any_global", return_value=None), mock.patch.object(
            runtime,
            "_has_active_recommend_dialog",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_find_recommend_resume_iframe_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_has_recommend_resume_frame",
            return_value=True,
        ), mock.patch.object(
            runtime,
            "goto",
            return_value=selectors.recommend_url,
        ) as goto_mock:
            result = runtime.close_recommend_detail(selectors)

        self.assertTrue(result)
        page.keyboard.press.assert_not_called()
        goto_mock.assert_not_called()

    def test_close_recommend_detail_resets_stale_inline_resume_state(self):
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

        with mock.patch.object(runtime, "_locator_for_any_global", return_value=None), mock.patch.object(
            runtime,
            "_has_active_recommend_dialog",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_has_inline_recommend_detail",
            side_effect=[True, True, True, True, True, True, True, False],
        ), mock.patch.object(
            runtime,
            "goto",
            return_value=selectors.recommend_url,
        ) as goto_mock, mock.patch.object(
            runtime,
            "wait_for_recommend_list_ready",
            return_value={"card_count": 15},
        ) as wait_mock:
            result = runtime.close_recommend_detail(selectors)

        self.assertTrue(result)
        self.assertEqual(page.keyboard.press.call_count, 3)
        goto_mock.assert_called_once_with(selectors.recommend_url)
        wait_mock.assert_called_once_with(selectors, timeout_ms=10000)

    def test_click_recommend_greet_supports_resume_greet_container(self):
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
        greet_target = mock.Mock()
        greet_locator = mock.Mock()
        greet_locator.first = greet_target

        with mock.patch.object(runtime, "_active_recommend_dialog_locator", return_value=None), mock.patch.object(
            runtime,
            "_locator_for_any_global",
            side_effect=lambda selectors_arg: greet_locator
            if any("resumeGreet" in selector or "btn-greet" in selector for selector in selectors_arg)
            else None,
        ):
            result = runtime.click_recommend_greet(selectors)

        self.assertEqual(result, {"clicked": True})
        greet_target.click.assert_called_once_with(timeout=5000, force=True)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_click_recommend_greet_prefers_opened_recommend_card_scope(self):
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
        runtime._recommend_expected_card = {"external_id": "recommend-001", "name": "候选人A"}
        card_scope = mock.Mock()
        greet_target = mock.Mock()
        greet_locator = mock.Mock()
        greet_locator.first = greet_target

        def locator_side_effect(selectors_arg, *, scope=None):
            if scope is card_scope and any("button-chat-wrap" in selector or "btn-greet" in selector for selector in selectors_arg):
                return greet_locator
            return None

        with mock.patch.object(runtime, "_active_recommend_dialog_locator", return_value=None), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=locator_side_effect,
        ) as locator_mock, mock.patch.object(
            runtime,
            "_locator_for_any_global",
            return_value=None,
        ):
            result = runtime.click_recommend_greet(selectors)

        self.assertEqual(result, {"clicked": True})
        greet_target.click.assert_called_once_with(timeout=5000, force=True)
        page.wait_for_timeout.assert_called_once_with(500)
        self.assertTrue(any(call.kwargs.get("scope") is card_scope for call in locator_mock.call_args_list))

    def test_click_recommend_greet_falls_back_to_visible_text_when_selectors_miss(self):
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
        page.get_by_text.return_value.count.return_value = 0
        runtime._page = page
        runtime._recommend_expected_card = {"external_id": "recommend-001", "name": "候选人A"}
        card_scope = mock.Mock()
        text_target = mock.Mock()
        text_locator = mock.Mock()
        text_locator.count.return_value = 1
        text_locator.first = text_target

        def get_by_text_side_effect(label, exact=True):
            if label == "打招呼" and exact:
                return text_locator
            empty = mock.Mock()
            empty.count.return_value = 0
            return empty

        card_scope.get_by_text.side_effect = get_by_text_side_effect

        with mock.patch.object(runtime, "_active_recommend_dialog_locator", return_value=None), mock.patch.object(
            runtime,
            "_resolve_recommend_card_scope",
            return_value=card_scope,
        ), mock.patch.object(
            runtime,
            "_locator_for_any",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_locator_for_any_global",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            return_value={
                "ready_visible": True,
                "has_dialog": False,
                "has_panel": True,
                "has_resume_frame": False,
                "has_resume_iframe": False,
            },
        ):
            result = runtime.click_recommend_greet(selectors)

        self.assertEqual(result, {"clicked": True})
        text_target.click.assert_called_once_with(timeout=5000)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_click_recommend_greet_falls_back_to_position_when_text_lookup_misses(self):
        runtime = PlaywrightBrowserRuntime(width=2000, height=1200)
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
        page.get_by_text.return_value.count.return_value = 0
        active_dialog_root = mock.Mock()
        active_dialog_root.bounding_box.return_value = {"x": 100, "y": 40, "width": 1800, "height": 1000}
        active_dialog = mock.Mock()
        active_dialog.first = active_dialog_root
        with mock.patch.object(runtime, "_active_recommend_dialog_locator", return_value=active_dialog), mock.patch.object(
            runtime,
            "_locator_for_any",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_locator_for_any_global",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_recommend_detail_state",
            return_value={
                "ready_visible": True,
                "has_dialog": True,
                "has_panel": False,
                "has_resume_frame": False,
                "has_resume_iframe": False,
            },
        ):
            result = runtime.click_recommend_greet(selectors)

        self.assertEqual(result, {"clicked": True})
        page.mouse.click.assert_called_once_with(1612.0, 220.0)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_has_inline_recommend_detail_does_not_treat_recommend_list_frame_as_resume_detail(self):
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

        with mock.patch.object(runtime, "_has_recommend_resume_frame", return_value=False), mock.patch.object(
            runtime,
            "_resolve_recommend_scope",
            return_value=scope,
        ), mock.patch.object(
            runtime,
            "_find_recommend_resume_iframe_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_find_resume_dialog_panel_target",
            return_value=None,
        ), mock.patch.object(
            runtime,
            "_has_active_recommend_dialog",
            return_value=False,
        ), mock.patch.object(
            runtime,
            "_frame_url_value",
            return_value="https://www.zhipin.com/web/frame/recommend/?jobid=712112f4607039490nd53ty6FFFY&status=0&source=0",
        ):
            result = runtime._has_inline_recommend_detail(selectors)

        self.assertFalse(result)

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

        scope_calls = {"count": 0}

        def resolve_scope_side_effect(*args, **kwargs):
            scope_calls["count"] += 1
            return current_page if scope_calls["count"] == 1 else fallback_scope

        with mock.patch.object(runtime, "_find_existing_recommend_page", return_value=fallback_page), mock.patch.object(
            runtime,
            "_resolve_recommend_scope",
            side_effect=resolve_scope_side_effect,
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

    def test_collect_recommend_cards_retries_with_refreshed_locator_when_frame_detaches_mid_scan(self):
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
        stale_card_0 = mock.Mock()
        stale_card_0.inner_text.return_value = "张三 10-20K 3年 产品经理 本科 打招呼"
        stale_card_1 = mock.Mock()
        stale_card_1.inner_text.side_effect = RuntimeError("Frame was detached")
        fresh_card_1 = mock.Mock()
        fresh_card_1.inner_text.return_value = "李四 15-25K 5年 AI产品经理 硕士 打招呼"

        initial_locator = mock.Mock()
        initial_locator.count.return_value = 3
        initial_locator.nth.side_effect = lambda index: [stale_card_0, stale_card_1, stale_card_1][index]
        refreshed_locator = mock.Mock()
        refreshed_locator.count.return_value = 3
        refreshed_locator.nth.side_effect = lambda index: [stale_card_0, fresh_card_1, fresh_card_1][index]

        locator_calls = []

        def locator_side_effect(selectors_arg, *, scope=None):
            locator_calls.append((tuple(selectors_arg), scope))
            return initial_locator if len(locator_calls) == 1 else refreshed_locator

        with mock.patch.object(runtime, "_resolve_recommend_scope", return_value=scope), mock.patch.object(
            runtime,
            "_locator_for_any",
            side_effect=locator_side_effect,
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
        self.assertEqual([item["card_index"] for item in items], [0, 1])
        self.assertEqual(items[1]["summary_text"], "李四 15-25K 5年 AI产品经理 硕士 打招呼")

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

    def test_extract_recommend_detail_payload_prefers_full_detail_payload(self):
        runtime = PlaywrightBrowserRuntime()
        dialog_root = mock.Mock()
        dialog_root.inner_text.return_value = "转发\n打招呼\n经历概览\n高级产品"
        dialog = mock.Mock()
        dialog.first = dialog_root
        with mock.patch.object(
            runtime,
            "extract_detail_payload",
            return_value={
                "detail_url": "https://www.zhipin.com/web/chat/recommend",
                "page_text": "完整简历正文\n1、负责产品规划\n2、负责需求分析",
                "content_html": "<div><p>完整简历正文</p><p>1、负责产品规划</p></div>",
                "page_html": "<html></html>",
            },
        ), mock.patch.object(
            runtime,
            "_active_recommend_dialog_locator",
            return_value=dialog,
        ):
            payload = runtime.extract_recommend_detail_payload(mock.Mock())

        self.assertEqual(payload["page_text"], "完整简历正文\n1、负责产品规划\n2、负责需求分析")
        self.assertIn("content_html", payload)

    def test_extract_recommend_detail_payload_falls_back_to_dialog_text_when_detail_payload_empty(self):
        runtime = PlaywrightBrowserRuntime()
        runtime._page = mock.Mock()
        runtime._page.url = "https://www.zhipin.com/web/chat/recommend"
        dialog_root = mock.Mock()
        dialog_root.inner_text.return_value = "转发\n打招呼\n完整简历正文\n1、负责产品规划\n2、负责需求分析"
        dialog = mock.Mock()
        dialog.first = dialog_root
        with mock.patch.object(
            runtime,
            "extract_detail_payload",
            return_value={
                "detail_url": "https://www.zhipin.com/web/chat/recommend",
                "page_text": "加载中，请稍候",
                "content_html": None,
                "page_html": None,
            },
        ), mock.patch.object(
            runtime,
            "_active_recommend_dialog_locator",
            return_value=dialog,
        ):
            payload = runtime.extract_recommend_detail_payload(mock.Mock())

        self.assertEqual(payload["page_text"], "完整简历正文\n1、负责产品规划\n2、负责需求分析")
        self.assertEqual(payload["detail_url"], "https://www.zhipin.com/web/chat/recommend")

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
