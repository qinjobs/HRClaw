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
        chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
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
        self.assertIn("Spring Boot", body)
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
