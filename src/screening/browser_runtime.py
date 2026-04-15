from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urljoin, urlparse, urlunparse

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None

try:
    import html2text
except ImportError:  # pragma: no cover - optional dependency
    html2text = None

try:
    from readability import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None

try:
    from lxml import html as lxml_html
except ImportError:  # pragma: no cover - optional dependency
    lxml_html = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

from .boss_selectors import BossSelectors


class BrowserRuntimeError(RuntimeError):
    pass


_RESUME_NOISE_LINES = {
    "收藏",
    "不合适",
    "举报",
    "转发牛人",
    "打招呼",
    "立即沟通",
    "立即开聊",
    "下载简历",
    "经历概览",
    "同事沟通",
    "我的沟通",
    "继续沟通",
    "推荐牛人",
    "招聘规范",
    "我的客服",
    "面试",
    "招聘数据",
    "账号权益",
    "升级VIP",
    "BOSS直聘",
    "职位管理",
    "搜索",
    "沟通",
    "意向沟通",
    "互动",
    "牛人管理",
    "道具",
    "工具箱",
    "更多",
    "客户端",
    "立即下载",
    "首充礼",
}

_RESUME_POSITIVE_MARKERS = (
    "工作经历",
    "项目经历",
    "最近关注",
    "个人优势",
    "个人简介",
    "期望职位",
    "项目简介",
    "具体内容",
    "项目职责",
    "教育经历",
)

_RESUME_NEGATIVE_MARKERS = (
    "其他名校毕业的牛人",
    "相似牛人",
    "更多牛人",
    "牛人最近7天沟通过的职位",
    "同事沟通",
    "我的沟通",
    "Ta向",
)

_RESUME_NOISE_FRAGMENTS = (
    "Ta向",
    "同事沟通",
    "我的沟通",
    "其他名校毕业的牛人",
    "牛人最近7天沟通过的职位",
)


class PlaywrightBrowserRuntime:
    def __init__(
        self,
        *,
        width: int = 1440,
        height: int = 900,
        headless: bool | None = None,
        start_url: str | None = None,
        screenshot_dir: Path | None = None,
        storage_state_path: Path | None = None,
        load_storage_state: bool = True,
        persist_storage_state_on_stop: bool = True,
        cdp_url: str | None = None,
        cdp_port: int | str | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.headless = headless if headless is not None else os.getenv("SCREENING_BROWSER_HEADLESS", "false").lower() == "true"
        self.start_url = start_url or os.getenv("SCREENING_BROWSER_START_URL", "https://www.zhipin.com/")
        self.screenshot_dir = screenshot_dir or Path(__file__).resolve().parents[2] / "data" / "screenshots"
        self.resume_dir = Path(__file__).resolve().parents[2] / "data" / "resumes"
        self.screenshot_full_page = os.getenv("SCREENING_SCREENSHOT_FULL_PAGE", "true").strip().lower() not in {
            "0",
            "false",
            "off",
            "no",
        }
        configured_storage_state = os.getenv("SCREENING_BROWSER_STORAGE_STATE_PATH")
        self.storage_state_path = storage_state_path or (
            Path(configured_storage_state)
            if configured_storage_state
            else Path(__file__).resolve().parents[2] / "data" / "auth" / "boss_storage_state.json"
        )
        configured_cdp_url = os.getenv("SCREENING_BROWSER_CDP_URL")
        configured_cdp_port = os.getenv("SCREENING_BROWSER_CDP_PORT")
        self.cdp_url = self._normalize_cdp_url(
            cdp_url
            or configured_cdp_url
            or configured_cdp_port
            or cdp_port
        )
        self.attached_to_existing_browser = bool(self.cdp_url)
        self.load_storage_state = load_storage_state
        self.persist_storage_state_on_stop = persist_storage_state_on_stop
        self.session_id: str | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._owns_page = False
        self._owns_browser = False
        self._owns_context = False
        self._resume_ocr_backend = None

    def start(self) -> str:
        if sync_playwright is None:
            raise BrowserRuntimeError("Playwright is not installed. Install with: python3 -m pip install playwright && python3 -m playwright install chromium")

        self.session_id = str(uuid.uuid4())
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.resume_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        if self.cdp_url:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
            self._owns_browser = False
            contexts = list(getattr(self._browser, "contexts", []) or [])
            if not contexts:
                raise BrowserRuntimeError(
                    f"No browser context available on attached Chrome session: {self.cdp_url}. "
                    "Start Chrome with a visible profile and remote debugging enabled."
                )
            self._context = contexts[0]
            self._owns_context = False
            self._page = self._select_attached_page(self._context.pages)
            if self._page is None:
                self._page = self._context.new_page()
                self._owns_page = True
            else:
                self._owns_page = False
            if self.start_url and self._is_blank_page_url(self._page.url):
                self._page.goto(self.start_url, wait_until="domcontentloaded")
        else:
            launch_kwargs: dict[str, Any] = {"headless": self.headless}
            executable_path = self._resolve_browser_executable_path()
            if executable_path is not None:
                launch_kwargs["executable_path"] = str(executable_path)
            self._browser = self._playwright.chromium.launch(**launch_kwargs)
            self._owns_browser = True
            context_kwargs: dict[str, Any] = {
                "viewport": {"width": self.width, "height": self.height},
                "accept_downloads": True,
            }
            if self.load_storage_state and self.storage_state_path.exists():
                context_kwargs["storage_state"] = str(self.storage_state_path)
            self._context = self._browser.new_context(**context_kwargs)
            self._owns_context = True
            self._page = self._context.new_page()
            self._owns_page = True
            if self.start_url:
                self._page.goto(self.start_url, wait_until="domcontentloaded")
        return self.session_id

    @property
    def current_url(self) -> str:
        if self._page is None:
            return ""
        return self._page.url

    def save_storage_state(self) -> None:
        if self._context is None:
            return
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.storage_state_path))

    def has_storage_state(self) -> bool:
        return self.storage_state_path.exists()

    def screenshot_bytes(self) -> bytes:
        if self._page is None:
            raise BrowserRuntimeError("Browser session not started.")
        if not self.screenshot_full_page:
            return self._page.screenshot(type="png")

        stitched_resume = self._capture_resume_scrollable_panel()
        if stitched_resume is not None:
            return stitched_resume

        self._prepare_long_resume_capture()
        try:
            return self._page.screenshot(type="png", full_page=True)
        except Exception:
            return self._page.screenshot(type="png")
        finally:
            self._restore_scroll_after_capture()

    def _resume_screenshot_bytes(self) -> bytes:
        if self._page is None:
            raise BrowserRuntimeError("Browser session not started.")
        target = self._find_resume_content_target()
        if target is not None:
            stitched_resume = self._capture_resume_scrollable_panel(target=target)
            if stitched_resume is not None:
                return stitched_resume
            _root, locator, _metrics = target
            try:
                return locator.screenshot(type="png")
            except Exception:
                pass
        clipped = self._capture_resume_dialog_left_clip()
        if clipped is not None:
            return clipped
        raise BrowserRuntimeError("No resume content container found for full resume screenshot.")

    def _capture_resume_dialog_left_clip(self) -> bytes | None:
        page = self._require_page()
        try:
            clip = page.evaluate(
                """
                () => {
                  const dialog =
                    document.querySelector('.dialog-wrap.active')
                    || document.querySelector("div[data-type='boss-dialog'].active")
                    || document.querySelector('[role="dialog"]');
                  if (!dialog) return null;
                  const dialogRect = dialog.getBoundingClientRect();
                  const dialogWidth = dialogRect.width || 0;
                  const dialogHeight = dialogRect.height || 0;
                  if (dialogWidth < 600 || dialogHeight < 200) return null;

                  const candidates = [...dialog.querySelectorAll('*')];
                  let best = null;
                  let bestScore = -Infinity;
                  for (const el of candidates) {
                    if (!(el instanceof HTMLElement)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 420 || rect.height < 180) continue;
                    if (rect.left < dialogRect.left || rect.right > dialogRect.right) continue;
                    const centerX = rect.left + rect.width / 2;
                    if (centerX > dialogRect.left + dialogWidth * 0.52) continue;
                    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (text.length < 80) continue;
                    let score = text.length + rect.width * 2 + rect.height;
                    if (el.scrollHeight > el.clientHeight + 40) score += 12000;
                    if (rect.width > dialogWidth * 0.7) score -= 20000;
                    if (rect.width > dialogWidth * 0.62) score -= 12000;
                    if (rect.left < dialogRect.left + dialogWidth * 0.08) score -= 12000;
                    if (/\\b\\d{2}岁\\b/.test(text)) score += 4000;
                    if (/(本科|硕士|博士|大专)/.test(text)) score += 2500;
                    if (/(工作经历|项目经历|最近关注|期望职位)/.test(text)) score += 3500;
                    if (text.includes('经历概览') || text.includes('其他名校毕业的牛人')) score -= 30000;
                    if (score > bestScore) {
                      best = rect;
                      bestScore = score;
                    }
                  }

                  const rect = best || {
                    left: dialogRect.left + Math.max(32, dialogWidth * 0.06),
                    top: dialogRect.top,
                    width: Math.max(420, dialogWidth * 0.58),
                    height: dialogHeight,
                  };
                  const clipLeft = Math.max(dialogRect.left + dialogWidth * 0.08, rect.left);
                  const clipWidth = Math.min(
                    rect.width,
                    dialogWidth * 0.62,
                    dialogRect.right - clipLeft
                  );
                  return {
                    x: Math.max(0, clipLeft),
                    y: Math.max(0, rect.top),
                    width: Math.max(1, clipWidth),
                    height: Math.max(1, Math.min(rect.height, dialogRect.bottom - rect.top)),
                  };
                }
                """
            )
        except Exception:
            return None
        if not clip:
            return None
        try:
            return page.screenshot(type="png", clip=clip)
        except Exception:
            return None

    def screenshot_base64(self) -> str:
        return base64.b64encode(self.screenshot_bytes()).decode("utf-8")

    def persist_screenshot(self, label: str) -> str:
        if self.session_id is None:
            raise BrowserRuntimeError("Browser session not started.")
        safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label)[:80]
        session_dir = self.screenshot_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{safe_label}.png"
        path.write_bytes(self.screenshot_bytes())
        return str(path)

    def persist_resume_full_screenshot(self, external_id: str, *, suffix: str = "resume_full") -> str:
        safe = self._safe_id(external_id or f"resume-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        if self.session_id is None:
            raise BrowserRuntimeError("Browser session not started.")
        session_dir = self.screenshot_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{safe}_{suffix}.png"
        path.write_bytes(self._resume_screenshot_bytes())
        return str(path)

    def persist_resume_markdown(
        self,
        external_id: str,
        content: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        content_html: str | None = None,
        page_html: str | None = None,
        screenshot_path: str | None = None,
    ) -> str:
        safe = self._safe_id(external_id or f"resume-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        session_dir = self._resume_session_dir()
        path = session_dir / f"{safe}.md"
        scroll_capture = self._extract_resume_scrollable_content()
        rendered_body = self._build_resume_markdown_body(
            content or "",
            content_html=content_html,
            page_html=page_html,
            scroll_text=scroll_capture.get("text"),
            scroll_html_fragments=scroll_capture.get("html_fragments") or (),
            screenshot_path=screenshot_path,
        )
        lines = [
            f"# {title or external_id or '简历'}",
            "",
            f"- 外部ID：{external_id or '-'}",
        ]
        if source_url:
            lines.append(f"- 来源链接：{source_url}")
        lines.extend(
            [
                f"- 归档时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "",
                "## 简历正文",
                "",
                rendered_body,
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def persist_resume_archive(
        self,
        external_id: str,
        content: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        content_html: str | None = None,
        page_html: str | None = None,
    ) -> dict[str, str]:
        screenshot_path = self.persist_resume_full_screenshot(external_id)
        markdown_path = self.persist_resume_markdown(
            external_id,
            content,
            title=title,
            source_url=source_url,
            content_html=content_html,
            page_html=page_html,
            screenshot_path=screenshot_path,
        )
        return {
            "resume_full_screenshot_path": screenshot_path,
            "resume_markdown_path": markdown_path,
            "resume_markdown_filename": Path(markdown_path).name,
        }

    def goto(self, url: str) -> str:
        page = self._require_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        return page.url

    def wait_for_any(self, selectors: Sequence[str], *, timeout_ms: int = 10000) -> str | None:
        return self._wait_for_any(selectors, timeout_ms=timeout_ms)

    def _wait_for_any(self, selectors: Sequence[str], *, timeout_ms: int = 10000, scope=None) -> str | None:
        page = scope or self._require_page()
        if not selectors:
            return None
        per_selector_timeout = max(500, timeout_ms // len(selectors))
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=per_selector_timeout, state="attached")
                return selector
            except Exception:
                continue
        return None

    def goto_search_page(self, selectors: BossSelectors) -> str:
        return self.goto(selectors.search_url)

    def goto_recommend_page(self, selectors: BossSelectors) -> str:
        page = self._require_page()
        current_url = (self.current_url or "").lower()
        chat_home_url = os.getenv("SCREENING_BOSS_CHAT_URL", "https://www.zhipin.com/web/chat/index")
        if "/web/chat/" not in current_url:
            page.goto(chat_home_url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
        if self._open_recommend_from_chat_menu(selectors):
            return page.url
        return self.goto(selectors.recommend_url)

    def is_login_scan_page(self) -> bool:
        page = self._require_page()
        current_url = (self.current_url or "").lower()
        if "/web/user" not in current_url and "login" not in current_url:
            return False
        try:
            body_text = page.locator("body").inner_text()[:2000]
        except Exception:
            return False
        markers = (
            "app扫码登录",
            "扫码登录",
            "扫码帮助",
            "验证码登录/注册",
        )
        return any(marker in body_text.lower() for marker in markers)

    def wait_for_login_scan(
        self,
        *,
        timeout_ms: int = 15000,
        check_interval_ms: int = 1500,
    ) -> bool:
        page = self._require_page()
        deadline = time.time() + max(0.5, timeout_ms / 1000.0)
        while time.time() < deadline:
            try:
                if page.is_closed():
                    return False
            except Exception:
                return False
            if not self.is_login_scan_page():
                return True
            try:
                page.wait_for_timeout(max(250, check_interval_ms))
            except Exception:
                return False
        return not self.is_login_scan_page()

    def is_manual_verification_page(self) -> bool:
        page = self._require_page()
        current_url = (self.current_url or "").lower()
        if any(token in current_url for token in ("/safe/verify-slider", "/safe/verify", "verify-slider")):
            return True
        markers = (
            "请完成验证",
            "点击按钮开始验证",
            "拖动滑块",
            "安全验证",
            "请点击图中",
            "verify-slider",
        )
        visible_selectors = (
            "iframe[src*='verify']",
            "iframe[src*='captcha']",
            "iframe[title*='验证']",
            "iframe[title*='verify']",
            "[class*='verify']",
            "[class*='captcha']",
            "[class*='slider']",
            "[role='dialog']",
            "div.dialog-wrap.active",
            "div[aria-modal='true']",
        )
        for selector in visible_selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(min(count, 3)):
                try:
                    element = locator.nth(index)
                    if not element.is_visible():
                        continue
                    text = ""
                    try:
                        text = element.inner_text(timeout=1000)[:2000]
                    except Exception:
                        text = ""
                    if any(marker in text for marker in markers):
                        return True
                    # A visible iframe with verify/captcha in the selector is already a strong signal.
                    if selector.startswith("iframe["):
                        return True
                except Exception:
                    continue
        return False

    def wait_for_manual_verification(
        self,
        *,
        timeout_ms: int = 180000,
        check_interval_ms: int = 1500,
    ) -> bool:
        page = self._require_page()
        deadline = time.time() + max(0.5, timeout_ms / 1000.0)
        while time.time() < deadline:
            try:
                if page.is_closed():
                    return False
            except Exception:
                return False
            if not self.is_manual_verification_page():
                return True
            try:
                page.wait_for_timeout(max(250, check_interval_ms))
            except Exception:
                return False
        return not self.is_manual_verification_page()

    def _open_recommend_from_chat_menu(self, selectors: BossSelectors) -> bool:
        page = self._require_page()
        current_url = (self.current_url or "").lower()
        if "/web/chat/recommend" in current_url:
            return True
        nav_selectors = self._recommend_nav_selectors()
        for _ in range(6):
            locator = self._locator_for_any_global(nav_selectors)
            if locator is not None:
                try:
                    locator.first.click()
                    page.wait_for_timeout(800)
                except Exception:
                    continue
                if "/web/chat/recommend" in (self.current_url or "").lower():
                    return True
                if self._locator_for_any_global(selectors.recommend_list_ready) is not None:
                    return True
            try:
                page.wait_for_timeout(400)
            except Exception:
                return False
        return False

    @staticmethod
    def _recommend_nav_selectors() -> tuple[str, ...]:
        raw = os.getenv("SCREENING_BOSS_RECOMMEND_NAV_SELECTORS")
        if raw:
            items = tuple(part.strip() for part in raw.split("||") if part.strip())
            if items:
                return items
        return (
            "a[href*='/web/chat/recommend']",
            "[ka*='recommend']",
            "[data-tab*='recommend']",
            "[data-name*='recommend']",
            "a:has-text('推荐牛人')",
            "button:has-text('推荐牛人')",
            "div:has-text('推荐牛人')",
            "span:has-text('推荐牛人')",
            "text=推荐牛人",
        )

    def apply_search_filters(self, selectors: BossSelectors, search_config: dict[str, Any], sort_by: str | None = None) -> dict[str, Any]:
        scope = self._resolve_search_scope(selectors)
        applied: dict[str, Any] = {}
        keyword = str(search_config.get("keyword", "")).strip()
        if keyword and self.fill_first(selectors.search_keyword_input, keyword, scope=scope):
            applied["keyword"] = keyword

        city = str(search_config.get("city", "")).strip()
        if city and self.fill_first(selectors.search_city_input, city, scope=scope):
            applied["city"] = city

        if applied:
            submitted = self.click_first(selectors.search_submit, scope=scope)
            if not submitted and keyword:
                self.press_enter_first(selectors.search_keyword_input, scope=scope)
            self._wait_for_any(selectors.list_ready, timeout_ms=15000, scope=scope)

        if sort_by and self.apply_sort(selectors, sort_by):
            applied["sort_by"] = sort_by

        return applied

    def collect_candidate_cards(self, selectors: BossSelectors, limit: int) -> list[dict[str, Any]]:
        scope = self._resolve_search_scope(selectors)
        card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
        if card_locator is None:
            return []

        self._expand_cards_by_scrolling(card_locator, limit=limit, scope=scope)
        items = []
        count = min(card_locator.count(), limit)
        for index in range(count):
            card = card_locator.nth(index)
            raw_href = self._attribute_from_scope(card, selectors.candidate_link, "href")
            detail_url = None if not raw_href or raw_href.startswith("javascript") else self._absolute_url(raw_href)
            summary_text = " | ".join(
                part
                for part in (
                    self._text_from_scope(card, selectors.candidate_name),
                    self._text_from_scope(card, selectors.candidate_title),
                    self._text_from_scope(card, selectors.candidate_company),
                    self._text_from_scope(card, selectors.candidate_experience),
                    self._text_from_scope(card, selectors.candidate_education),
                    self._text_from_scope(card, selectors.candidate_location),
                )
                if part
            )
            # The BOSS card contains richer fields than our generic selectors can capture.
            # Prefer the full card text as fallback evidence for extraction/scoring.
            try:
                full_card_text = card.inner_text().strip()
            except Exception:
                full_card_text = ""
            external_id = self._extract_external_id(
                card,
                selectors.candidate_external_id,
                detail_url,
                index + 1,
                fallback_text=full_card_text or summary_text,
            )
            items.append(
                {
                    "card_index": index,
                    "external_id": external_id,
                    "name": self._text_from_scope(card, selectors.candidate_name),
                    "current_title": self._text_from_scope(card, selectors.candidate_title),
                    "current_company": self._text_from_scope(card, selectors.candidate_company),
                    "years_experience": self._extract_years(self._text_from_scope(card, selectors.candidate_experience)),
                    "education_level": self._text_from_scope(card, selectors.candidate_education),
                    "location": self._text_from_scope(card, selectors.candidate_location),
                    "last_active_time": self._text_from_scope(card, selectors.candidate_active_time),
                    "detail_url": detail_url,
                    "summary_text": full_card_text or summary_text,
                }
            )
        return items

    def collect_recommend_cards(self, selectors: BossSelectors, limit: int) -> list[dict[str, Any]]:
        scope = self._resolve_recommend_scope(selectors)
        card_locator = self._locator_for_any(selectors.recommend_candidate_card, scope=scope)
        if card_locator is None:
            card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
        if card_locator is None:
            return []

        self._expand_cards_by_scrolling(card_locator, limit=limit, scope=scope)
        items = []
        count = min(card_locator.count(), limit)
        for index in range(count):
            card = card_locator.nth(index)
            raw_href = self._attribute_from_scope(card, selectors.recommend_candidate_name_link, "href")
            detail_url = None if not raw_href or raw_href.startswith("javascript") else self._absolute_url(raw_href)
            try:
                full_card_text = card.inner_text().strip()
            except Exception:
                full_card_text = ""
            external_id = self._extract_external_id(
                card,
                selectors.recommend_candidate_external_id,
                detail_url,
                index + 1,
                fallback_text=full_card_text,
            )
            items.append(
                {
                    "card_index": index,
                    "external_id": external_id,
                    "name": self._text_from_scope(card, selectors.candidate_name)
                    or self._text_from_scope(card, selectors.recommend_candidate_name_link),
                    "current_title": self._text_from_scope(card, selectors.candidate_title),
                    "current_company": self._text_from_scope(card, selectors.candidate_company),
                    "years_experience": self._extract_years(self._text_from_scope(card, selectors.candidate_experience)),
                    "education_level": self._text_from_scope(card, selectors.candidate_education),
                    "location": self._text_from_scope(card, selectors.candidate_location),
                    "last_active_time": self._text_from_scope(card, selectors.candidate_active_time),
                    "detail_url": detail_url,
                    "summary_text": full_card_text,
                }
            )
        return items

    def open_candidate_card(self, card: dict[str, Any], selectors: BossSelectors) -> str:
        scope = self._resolve_search_scope(selectors)
        if card.get("detail_url") and not str(card.get("detail_url")).startswith("javascript"):
            self.goto(card["detail_url"])
        else:
            # BOSS frequently keeps the previous resume dialog open, which blocks
            # pointer events on the next list card. Dismiss overlays before clicking.
            self._dismiss_blocking_dialogs()
            card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
            if card_locator is None or card["card_index"] >= card_locator.count():
                raise BrowserRuntimeError("Candidate card is no longer available on the list page.")
            card_scope = card_locator.nth(card["card_index"])
            link_locator = self._locator_for_any(selectors.candidate_link, scope=card_scope)
            if link_locator is not None:
                try:
                    link_locator.first.click(timeout=5000)
                except Exception:
                    self._dismiss_blocking_dialogs()
                    try:
                        link_locator.first.click(timeout=5000, force=True)
                    except Exception:
                        card_scope.click(timeout=5000, force=True)
            else:
                try:
                    card_scope.click(timeout=5000)
                except Exception:
                    self._dismiss_blocking_dialogs()
                    card_scope.click(timeout=5000, force=True)
            self._require_page().wait_for_timeout(1200)
        self.wait_for_any(selectors.detail_ready, timeout_ms=15000)
        return self._require_page().url

    def open_recommend_candidate(self, card: dict[str, Any], selectors: BossSelectors) -> str:
        scope = self._resolve_recommend_scope(selectors)
        self._dismiss_blocking_dialogs()
        card_locator = self._locator_for_any(selectors.recommend_candidate_card, scope=scope)
        if card_locator is None:
            card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
        if card_locator is None or card["card_index"] >= card_locator.count():
            raise BrowserRuntimeError("Recommend candidate card is no longer available on the list page.")

        card_scope = card_locator.nth(card["card_index"])
        link_locator = self._locator_for_any(selectors.recommend_candidate_name_link, scope=card_scope)
        if link_locator is None:
            link_locator = self._locator_for_any(selectors.candidate_link, scope=card_scope)
        if link_locator is not None:
            try:
                link_locator.first.click(timeout=5000)
            except Exception:
                self._dismiss_blocking_dialogs()
                link_locator.first.click(timeout=5000, force=True)
        else:
            try:
                card_scope.click(timeout=5000)
            except Exception:
                self._dismiss_blocking_dialogs()
                card_scope.click(timeout=5000, force=True)

        self._require_page().wait_for_timeout(1200)
        self._wait_for_any(selectors.recommend_detail_ready + selectors.detail_ready, timeout_ms=15000)
        return self._require_page().url

    def download_resume(self, selectors: BossSelectors, external_id: str | None = None, *, timeout_ms: int = 12000) -> dict[str, Any]:
        page = self._require_page()
        active_dialog = self._locator_for_any_global(
            ("div.dialog-wrap.active", "div[data-type='boss-dialog'].active")
        )
        locator = None
        if active_dialog is not None:
            try:
                locator = self._locator_for_any(selectors.recommend_download_button, scope=active_dialog.first)
            except Exception:
                locator = None
        if locator is None:
            locator = self._locator_for_any_global(selectors.recommend_download_button)
        if locator is None:
            return {"downloaded": False, "reason": "download_button_not_found", "resume_path": None}
        try:
            with page.expect_download(timeout=timeout_ms) as download_info:
                locator.first.click(timeout=5000, force=True)
            download = download_info.value
            suggested_name = download.suggested_filename or "resume.bin"
            suffix = Path(suggested_name).suffix or ".bin"
            base = self._safe_id(external_id or f"resume-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
            path = self._resume_session_dir() / f"{base}{suffix}"
            download.save_as(str(path))
            return {
                "downloaded": True,
                "resume_path": str(path),
                "suggested_filename": suggested_name,
            }
        except Exception as exc:
            return {"downloaded": False, "reason": str(exc), "resume_path": None}

    def click_recommend_greet(self, selectors: BossSelectors) -> dict[str, Any]:
        active_dialog = self._locator_for_any_global(
            ("div.dialog-wrap.active", "div[data-type='boss-dialog'].active")
        )
        locator = None
        if active_dialog is not None:
            try:
                locator = self._locator_for_any(selectors.recommend_greet_button, scope=active_dialog.first)
            except Exception:
                locator = None
        if locator is None:
            locator = self._locator_for_any_global(selectors.recommend_greet_button)
        if locator is None:
            return {"clicked": False, "reason": "greet_button_not_found"}
        try:
            locator.first.click(timeout=5000, force=True)
            self._require_page().wait_for_timeout(500)
            return {"clicked": True}
        except Exception as exc:
            return {"clicked": False, "reason": str(exc)}

    def close_recommend_detail(self, selectors: BossSelectors) -> bool:
        page = self._require_page()
        for _ in range(3):
            locator = self._locator_for_any_global(selectors.recommend_close_button)
            if locator is not None:
                try:
                    locator.first.click(timeout=1500, force=True)
                    page.wait_for_timeout(300)
                    return True
                except Exception:
                    pass
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
            except Exception:
                return False
            if page.locator("div.dialog-wrap.active, div[data-type='boss-dialog'].active").count() == 0:
                return True
        return False

    def extract_recommend_detail_payload(self, selectors: BossSelectors) -> dict[str, Any]:
        active_dialog = self._locator_for_any_global(
            ("div.dialog-wrap.active", "div[data-type='boss-dialog'].active")
        )
        if active_dialog is not None:
            try:
                text = active_dialog.first.inner_text().strip()
                if text:
                    return {"detail_url": self.current_url, "page_text": text}
            except Exception:
                pass
        return self.extract_detail_payload(selectors)

    def persist_resume_text(self, external_id: str, content: str) -> str:
        safe = self._safe_id(external_id or f"resume-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
        path = self._resume_session_dir() / f"{safe}.txt"
        path.write_text(content or "", encoding="utf-8")
        return str(path)

    def extract_detail_payload(self, selectors: BossSelectors) -> dict[str, Any]:
        best_target = self._find_resume_content_target(selectors)
        scroll_capture = self._extract_resume_scrollable_content(target=best_target)
        best_content = self._extract_best_resume_content(selectors, target=best_target)
        text = (
            self._cleanup_resume_text(scroll_capture.get("text"))
            or best_content.get("text")
            or self.text_content_any(self._resume_detail_selectors(selectors))
            or ""
        )
        content_html = (
            scroll_capture.get("html")
            or best_content.get("html")
            or self.html_content_any(self._resume_detail_selectors(selectors))
        )
        page_html = self.page_html()
        return {
            "detail_url": self.current_url,
            "page_text": text.strip(),
            "content_html": content_html,
            "page_html": page_html,
            "content_selector": best_content.get("selector") or scroll_capture.get("selector"),
        }

    def apply_sort(self, selectors: BossSelectors, sort_by: str) -> bool:
        scope = self._resolve_search_scope(selectors)
        normalized = (sort_by or "").strip().lower()
        if normalized in {"active", "activity"}:
            if self.click_first(selectors.sort_active, scope=scope):
                self._wait_for_any(selectors.list_ready, timeout_ms=10000, scope=scope)
                return True
        elif normalized in {"recent", "latest", "new"}:
            if self.click_first(selectors.sort_recent, scope=scope):
                self._wait_for_any(selectors.list_ready, timeout_ms=10000, scope=scope)
                return True
        return False

    def go_to_next_page(self, selectors: BossSelectors) -> bool:
        scope = self._resolve_search_scope(selectors)
        locator = self._locator_for_any(selectors.next_page, scope=scope)
        if locator is None:
            return False
        button = locator.first
        try:
            disabled = (button.get_attribute("disabled") is not None) or (
                (button.get_attribute("aria-disabled") or "").lower() == "true"
            )
            classes = (button.get_attribute("class") or "").lower()
            if disabled or "disabled" in classes:
                return False
            button.click()
            self._wait_for_any(selectors.list_ready, timeout_ms=15000, scope=scope)
            return True
        except Exception:
            return False

    def text_content_any(self, selectors: Sequence[str], *, scope=None) -> str | None:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return None
        try:
            return locator.first.inner_text().strip()
        except Exception:
            return None

    def html_content_any(self, selectors: Sequence[str], *, scope=None) -> str | None:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return None
        try:
            return locator.first.inner_html()
        except Exception:
            return None

    def page_html(self) -> str | None:
        page = self._require_page()
        try:
            return page.content()
        except Exception:
            return None

    def _extract_best_resume_content(self, selectors: BossSelectors, *, target=None) -> dict[str, str]:
        if target is not None:
            try:
                _root, locator, _metrics = target
                text = self._cleanup_resume_text(locator.inner_text())
                html = locator.inner_html()
                selector = locator.evaluate("(el) => el.className || el.id || el.tagName.toLowerCase()") or ""
                return {"text": text, "html": html, "selector": selector}
            except Exception:
                pass
        page = self._require_page()
        roots = [page, *page.frames]
        selector_pool = list(dict.fromkeys(self._resume_detail_selectors(selectors)))
        best: dict[str, str] = {"text": "", "html": "", "selector": ""}
        best_score = -1
        for root in roots:
            for selector in selector_pool:
                locator = root.locator(selector)
                try:
                    count = min(locator.count(), 3)
                except Exception:
                    continue
                for index in range(count):
                    node = locator.nth(index)
                    try:
                        text = node.inner_text().strip()
                    except Exception:
                        continue
                    cleaned = self._cleanup_resume_text(text)
                    if len(cleaned) < 40:
                        continue
                    score = len(cleaned) + self._resume_content_bonus(selector, cleaned)
                    try:
                        html = node.inner_html()
                    except Exception:
                        html = ""
                    if score > best_score:
                        best = {"text": cleaned, "html": html, "selector": selector}
                        best_score = score
                if best_score > 900:
                    break
            if best_score > 900:
                break
        return best

    def fill_first(self, selectors: Sequence[str], value: str, *, scope=None) -> bool:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return False
        try:
            locator.first.fill(value)
            return True
        except Exception:
            return False

    def click_first(self, selectors: Sequence[str], *, scope=None) -> bool:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return False
        try:
            locator.first.click()
            return True
        except Exception:
            return False

    def press_enter_first(self, selectors: Sequence[str], *, scope=None) -> bool:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return False
        try:
            locator.first.press("Enter")
            return True
        except Exception:
            return False

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        if self._page is None:
            raise BrowserRuntimeError("Browser session not started.")
        action_type = action.get("type")
        if action_type == "click":
            self._page.mouse.click(action["x"], action["y"], button=action.get("button", "left"))
        elif action_type == "double_click":
            self._page.mouse.click(action["x"], action["y"], button=action.get("button", "left"), click_count=2)
        elif action_type == "move":
            self._page.mouse.move(action["x"], action["y"])
        elif action_type == "scroll":
            if "x" in action and "y" in action:
                self._page.mouse.move(action["x"], action["y"])
            self._page.mouse.wheel(action.get("scroll_x", 0), action.get("scroll_y", 0))
        elif action_type == "keypress":
            self._page.keyboard.press(action["keys"])
        elif action_type == "type":
            text = action.get("text", "")
            if action.get("clear"):
                self._page.keyboard.press("Meta+A" if os.name != "nt" else "Control+A")
                self._page.keyboard.press("Backspace")
            self._page.keyboard.type(text)
        elif action_type == "wait":
            self._page.wait_for_timeout(action.get("ms", 1000))
        elif action_type == "drag":
            self._page.mouse.move(action["x"], action["y"])
            self._page.mouse.down()
            last = action.get("path", [])[-1]
            self._page.mouse.move(last["x"], last["y"])
            self._page.mouse.up()
        elif action_type == "navigate":
            self._page.goto(action["url"], wait_until="domcontentloaded")
        else:
            raise BrowserRuntimeError(f"Unsupported computer action: {action_type}")

        self._page.wait_for_timeout(400)
        return {"action_type": action_type, "current_url": self.current_url}

    def stop(self) -> None:
        try:
            if self.persist_storage_state_on_stop:
                self.save_storage_state()
        finally:
            if self._page is not None and self._owns_page:
                try:
                    self._page.close()
                except Exception:
                    pass
            if self._context is not None and self._owns_context:
                self._context.close()
            if self._browser is not None and self._owns_browser:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._owns_page = False
            self._owns_context = False
            self._owns_browser = False

    @staticmethod
    def _normalize_cdp_url(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            return f"http://127.0.0.1:{text}"
        if text.startswith(("http://", "https://", "ws://", "wss://")):
            parsed = urlparse(text)
            if parsed.hostname in {"localhost", "::1"}:
                host = "127.0.0.1"
                netloc = host
                if parsed.port:
                    netloc = f"{host}:{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return text
        if re.fullmatch(r"\d+", text):
            return f"http://127.0.0.1:{text}"
        return text

    @staticmethod
    def _is_blank_page_url(url: str | None) -> bool:
        normalized = (url or "").strip().lower()
        return not normalized or normalized in {"about:blank", "chrome://newtab/", "chrome://newtab"}

    def _select_attached_page(self, pages: Sequence[Any]) -> Any | None:
        if not pages:
            return None
        preferred_hosts = ("zhipin.com", "localhost", "127.0.0.1")
        preferred_fragments = (
            "/web/chat/",
            "/web/frame/",
            "/web/user/",
            "/web/recommend/",
            "/login",
        )
        candidates = list(pages)
        for page in reversed(candidates):
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if self._is_blank_page_url(url):
                continue
            if any(host in url for host in preferred_hosts) and any(fragment in url for fragment in preferred_fragments):
                return page
        for page in reversed(candidates):
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if self._is_blank_page_url(url):
                continue
            if any(host in url for host in preferred_hosts):
                return page
        for page in reversed(candidates):
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if not self._is_blank_page_url(url):
                return page
        return None

    def _require_page(self):
        if self._page is None:
            raise BrowserRuntimeError("Browser session not started.")
        return self._page

    def _resolve_browser_executable_path(self) -> Path | None:
        configured = os.getenv("SCREENING_BROWSER_EXECUTABLE_PATH", "").strip()
        if not configured:
            return None
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path if path.exists() else None

    def _resolve_search_scope(self, selectors: BossSelectors):
        return self._resolve_scope(selectors.search_frame_name, selectors.search_frame_url_contains)

    def _resolve_recommend_scope(self, selectors: BossSelectors):
        return self._resolve_scope(selectors.recommend_frame_name, selectors.recommend_frame_url_contains)

    def _resolve_scope(self, frame_name: str | None, frame_url_contains: str | None):
        page = self._require_page()
        for _ in range(60):
            for frame in page.frames:
                if frame_name and frame.name == frame_name:
                    return frame
                if frame_url_contains and frame_url_contains in frame.url:
                    return frame
            page.wait_for_timeout(250)
        return page

    def _locator_for_any(self, selectors: Sequence[str], *, scope=None):
        root = scope or self._require_page()
        for selector in selectors:
            locator = root.locator(selector)
            try:
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        return None

    def _locator_for_any_global(self, selectors: Sequence[str]):
        page = self._require_page()
        roots = [page, *page.frames]
        for root in roots:
            locator = self._locator_for_any(selectors, scope=root)
            if locator is not None:
                return locator
        return None

    def _expand_cards_by_scrolling(self, card_locator, *, limit: int, scope=None) -> int:
        """
        Best-effort expansion for infinite-scroll lists before collecting cards.
        """
        target = max(1, int(limit or 1))
        try:
            last_count = card_locator.count()
        except Exception:
            return 0
        if last_count >= target:
            return last_count

        scroll_attempts = max(6, min(60, target // 2 + 8))
        stable_rounds = 0
        root = scope or self._require_page()
        for _ in range(scroll_attempts):
            try:
                root.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900));")
            except Exception:
                break
            try:
                root.wait_for_timeout(450)
            except Exception:
                self._require_page().wait_for_timeout(450)

            try:
                current_count = card_locator.count()
            except Exception:
                break

            if current_count >= target:
                last_count = current_count
                break

            if current_count <= last_count:
                stable_rounds += 1
                if stable_rounds >= 4:
                    break
            else:
                stable_rounds = 0
                last_count = current_count

        return last_count

    def _text_from_scope(self, scope, selectors: Sequence[str]) -> str | None:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return None
        try:
            return locator.first.inner_text().strip()
        except Exception:
            return None

    def _attribute_from_scope(self, scope, selectors: Sequence[str], name: str) -> str | None:
        locator = self._locator_for_any(selectors, scope=scope)
        if locator is None:
            return None
        try:
            return locator.first.get_attribute(name)
        except Exception:
            return None

    def _absolute_url(self, url: str | None) -> str | None:
        if not url:
            return None
        return urljoin(self.current_url or self.start_url, url)

    def _extract_external_id(
        self,
        scope,
        external_id_selectors: Sequence[str],
        detail_url: str | None,
        index: int,
        *,
        fallback_text: str | None = None,
    ) -> str:
        for attr_name in ("data-geek-id", "data-id", "data-uid", "data-jid", "data-user-id", "data-geekid", "data-expect"):
            try:
                direct = scope.get_attribute(attr_name)
                if direct:
                    return direct
            except Exception:
                pass
            value = self._attribute_from_scope(scope, external_id_selectors, attr_name)
            if value:
                return value
        for candidate in self._candidate_id_hints(scope):
            external_id = self._normalize_external_id_hint(candidate)
            if external_id:
                return external_id
        if detail_url:
            match = re.search(r"/([A-Za-z0-9_-]{6,})\.html", detail_url)
            if match:
                return match.group(1)
        return self._fingerprint_external_id(fallback_text, index=index)

    def _candidate_id_hints(self, scope) -> list[str]:
        try:
            values = scope.evaluate(
                """(node) => {
                    const attrs = ['href', 'data-geek-id', 'data-id', 'data-uid', 'data-jid', 'data-user-id', 'data-geekid', 'data-expect'];
                    const nodes = [node, ...node.querySelectorAll('*')].slice(0, 80);
                    const hits = [];
                    for (const item of nodes) {
                      for (const attr of attrs) {
                        const value = item.getAttribute && item.getAttribute(attr);
                        if (value) hits.push(value);
                      }
                      if (item.dataset) {
                        for (const [key, value] of Object.entries(item.dataset)) {
                          if (value && /(id|uid|jid|geek|expect)/i.test(key)) hits.push(value);
                        }
                      }
                    }
                    return hits;
                }"""
            )
        except Exception:
            return []
        return [str(value).strip() for value in (values or []) if str(value).strip()]

    @staticmethod
    def _normalize_external_id_hint(value: str | None) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        direct_match = re.search(r"/([A-Za-z0-9_-]{6,})\.html", raw)
        if direct_match:
            return direct_match.group(1)
        query_match = re.search(r"(?:geekid|geek_id|data-geek-id|uid|user_id|id)=([A-Za-z0-9_-]{6,})", raw, re.I)
        if query_match:
            return query_match.group(1)
        if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", raw) and not raw.startswith("playwright-"):
            return raw
        return None

    @staticmethod
    def _fingerprint_external_id(fallback_text: str | None, *, index: int) -> str:
        source = re.sub(r"\s+", " ", str(fallback_text or "")).strip()
        if source:
            digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
            return f"playwright-fp-{digest}"
        return f"playwright-{index}"

    def _resume_session_dir(self) -> Path:
        if self.session_id is None:
            raise BrowserRuntimeError("Browser session not started.")
        target = self.resume_dir / self.session_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _safe_id(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120]

    def _build_resume_markdown_body(
        self,
        content: str,
        *,
        content_html: str | None = None,
        page_html: str | None = None,
        scroll_text: str | None = None,
        scroll_html_fragments: Sequence[str] = (),
        screenshot_path: str | None = None,
    ) -> str:
        markdown = self._render_resume_html_to_markdown(
            content_html=content_html,
            page_html=page_html,
            scroll_html_fragments=scroll_html_fragments,
            screenshot_path=screenshot_path,
        )
        if markdown:
            return markdown
        fallback_text = self._cleanup_resume_text(scroll_text) or self._cleanup_resume_text(content)
        return fallback_text or "_暂无可提取文本_"

    def _render_resume_html_to_markdown(
        self,
        *,
        content_html: str | None = None,
        page_html: str | None = None,
        scroll_html_fragments: Sequence[str] = (),
        screenshot_path: str | None = None,
    ) -> str | None:
        ocr_markdown = self._ocr_resume_markdown_from_image(screenshot_path)
        if ocr_markdown:
            return ocr_markdown

        candidates: list[str] = []
        if lxml_html is not None and html2text is not None:
            merged_scroll_markdown = self._merge_scroll_html_fragments_to_markdown(scroll_html_fragments)
            if merged_scroll_markdown:
                candidates.append(merged_scroll_markdown)
            cleaned_fragment = self._clean_resume_html_fragment(content_html)
            if cleaned_fragment:
                rendered = self._html_fragment_to_markdown(cleaned_fragment)
                if rendered:
                    candidates.append(rendered)

            readability_fragment = self._readability_resume_html(page_html)
            if readability_fragment:
                rendered = self._html_fragment_to_markdown(readability_fragment)
                if rendered and rendered not in candidates:
                    candidates.append(rendered)

        best_markdown: str | None = None
        best_score = float("-inf")
        for rendered in candidates:
            if not rendered:
                continue
            score = self._resume_markdown_quality_score(rendered)
            if score > best_score:
                best_markdown = rendered
                best_score = score
        return best_markdown

    def _merge_scroll_html_fragments_to_markdown(self, fragments: Sequence[str]) -> str | None:
        markdown_blocks: list[str] = []
        seen_signatures: set[str] = set()
        for fragment in fragments:
            cleaned = self._clean_resume_html_fragment(fragment)
            if not cleaned:
                continue
            rendered = self._html_fragment_to_markdown(cleaned)
            if not rendered:
                continue
            signature = hashlib.sha1(rendered.encode("utf-8")).hexdigest()
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            markdown_blocks.append(rendered)
        if not markdown_blocks:
            return None
        return self._merge_markdown_blocks(markdown_blocks)

    def _clean_resume_html_fragment(self, content_html: str | None) -> str | None:
        if not content_html or lxml_html is None:
            return None
        try:
            root = lxml_html.fragment_fromstring(content_html, create_parent="div")
        except Exception:
            try:
                root = lxml_html.fromstring(f"<div>{content_html}</div>")
            except Exception:
                return None

        for xpath in (
            ".//script",
            ".//style",
            ".//noscript",
            ".//svg",
            ".//canvas",
            ".//iframe",
            ".//button",
            ".//input",
            ".//select",
            ".//textarea",
        ):
            for node in root.xpath(xpath):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)

        class_keywords = (
            "button-list",
            "btn",
            "action",
            "toolbar",
            "operate",
            "operation",
            "report",
            "collect",
            "header-right",
            "topbar",
            "tool",
        )
        for node in list(root.iter()):
            class_id = " ".join(
                str(node.attrib.get(key, "")).lower()
                for key in ("class", "id", "data-role", "data-name")
            )
            if any(keyword in class_id for keyword in class_keywords):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                continue
            text = re.sub(r"\s+", " ", "".join(node.itertext())).strip()
            if text in _RESUME_NOISE_LINES:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)

        return lxml_html.tostring(root, encoding="unicode", method="html")

    def _readability_resume_html(self, page_html: str | None) -> str | None:
        if not page_html or Document is None:
            return None
        try:
            summary = Document(page_html).summary(html_partial=True)
        except Exception:
            return None
        return self._clean_resume_html_fragment(summary)

    def _html_fragment_to_markdown(self, html_fragment: str | None) -> str | None:
        if not html_fragment or html2text is None:
            return None
        try:
            renderer = html2text.HTML2Text()
            renderer.body_width = 0
            renderer.ignore_links = True
            renderer.ignore_images = True
            renderer.ignore_emphasis = False
            renderer.single_line_break = False
            markdown = renderer.handle(html_fragment)
        except Exception:
            return None
        cleaned = self._cleanup_resume_text(markdown)
        return cleaned or None

    @staticmethod
    def _resume_markdown_quality_score(markdown: str) -> int:
        lines = [line.strip() for line in markdown.splitlines() if line.strip()]
        if not lines:
            return -1
        noise_hits = sum(1 for line in lines if line in _RESUME_NOISE_LINES)
        heading_hits = sum(1 for line in lines if line.startswith(("#", "-", "*")))
        long_lines = sum(1 for line in lines if len(line) >= 28)
        very_long_lines = sum(1 for line in lines if len(line) >= 48)
        date_like_lines = sum(1 for line in lines if re.search(r"\d{4}[./-]\d{1,2}\s*[-至]\s*\d{4}[./-]\d{1,2}|至今|^\d+年\d+个月?$", line))
        bullet_like_lines = sum(1 for line in lines if re.match(r"^\d+[.、]", line))
        marker_bonus = sum(1 for marker in _RESUME_POSITIVE_MARKERS if marker in markdown)
        negative_hits = sum(1 for marker in _RESUME_NEGATIVE_MARKERS if marker in markdown)
        score = len("".join(lines)) + heading_hits * 8 - noise_hits * 60
        score += long_lines * 180 + very_long_lines * 300 + bullet_like_lines * 500 + marker_bonus * 1200
        score -= negative_hits * 25000
        if long_lines == 0:
            score -= 18000
        if date_like_lines > max(3, long_lines * 1.4):
            score -= 9000
        return score

    def _ocr_resume_markdown_from_image(self, screenshot_path: str | None) -> str | None:
        if not screenshot_path:
            return None
        image_path = Path(screenshot_path)
        if not image_path.exists():
            return None
        backend = self._get_resume_ocr_backend()
        if backend is None or not backend.enabled():
            return None
        try:
            text = backend.extract_text(image_path)
        except Exception:
            return None
        return self._cleanup_resume_text(text) or None

    def _get_resume_ocr_backend(self):
        if self._resume_ocr_backend is not None:
            return self._resume_ocr_backend
        try:
            from .phase2_imports import PaddleOCRBackend
        except Exception:
            return None
        self._resume_ocr_backend = PaddleOCRBackend()
        return self._resume_ocr_backend

    @staticmethod
    def _cleanup_resume_text(text: str | None) -> str:
        raw_lines = [re.sub(r"\s+", " ", (line or "")).strip() for line in str(text or "").splitlines()]
        filtered: list[str] = []
        last_blank = False
        for line in raw_lines:
            if not line:
                if filtered and not last_blank:
                    filtered.append("")
                last_blank = True
                continue
            if line in _RESUME_NOISE_LINES:
                continue
            if any(fragment in line for fragment in _RESUME_NOISE_FRAGMENTS):
                continue
            filtered.append(line)
            last_blank = False
        meta_index = next(
            (
                index
                for index, line in enumerate(filtered)
                if re.search(r"\d{2}岁", line)
                or (
                    re.search(r"(本科|硕士|博士|大专)", line)
                    and re.search(r"(离职-|在职-|随时到岗|考虑机会)", line)
                )
            ),
            None,
        )
        if meta_index is not None and meta_index > 0:
            preserved_prefix: list[str] = []
            for line in filtered[max(0, meta_index - 3):meta_index]:
                normalized = line.strip()
                if not normalized:
                    continue
                if re.search(r"[A-Za-z]{2,}", normalized):
                    continue
                if len(normalized) <= 8 or normalized in {"刚刚活跃", "在线", "离线", "活跃"}:
                    preserved_prefix.append(normalized)
            filtered = preserved_prefix[-2:] + filtered[meta_index:]
        while filtered and not filtered[-1]:
            filtered.pop()
        return "\n".join(filtered).strip()

    @staticmethod
    def _merge_markdown_blocks(blocks: Sequence[str]) -> str:
        seen: set[str] = set()
        merged: list[str] = []
        for block in blocks:
            lines = [line.rstrip() for line in block.splitlines()]
            chunk: list[str] = []
            for line in lines:
                normalized = re.sub(r"\s+", " ", line).strip()
                if not normalized:
                    if chunk and chunk[-1] != "":
                        chunk.append("")
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                chunk.append(line)
            while chunk and chunk[-1] == "":
                chunk.pop()
            if chunk:
                if merged and merged[-1] != "":
                    merged.append("")
                merged.extend(chunk)
        return "\n".join(merged).strip()

    @staticmethod
    def _resume_content_bonus(selector: str, text: str) -> int:
        normalized_selector = (selector or "").lower()
        normalized_text = text or ""
        bonus = 0
        if any(token in normalized_selector for token in ("iboss-left", "resume-detail-wrap", "geek-resume-wrap", "resume-content")):
            bonus += 12000
        if "iboss-left" in normalized_selector:
            bonus += 8000
        if "dialog-wrap.active" in normalized_selector:
            bonus += 3000
        if normalized_selector == "main":
            bonus -= 1500
        if any(token in normalized_selector for token in ("card-inner", "candidate-card-wrap", "card-content")):
            bonus -= 2000
        if "resume-detail-wrap" in normalized_selector:
            bonus -= 5000
        for marker in _RESUME_POSITIVE_MARKERS:
            if marker in normalized_text:
                bonus += 1200
        for marker in _RESUME_NEGATIVE_MARKERS:
            if marker in normalized_text:
                bonus -= 25000
        return bonus

    def _dismiss_blocking_dialogs(self) -> None:
        page = self._require_page()
        close_selectors = (
            "div.dialog-wrap.active i.icon-close",
            "div.dialog-wrap.active .close",
            "div.dialog-wrap.active [class*='close']",
            "div[data-type='boss-dialog'].active i.icon-close",
            "div[data-type='boss-dialog'].active .close",
            "div[role='dialog'] [aria-label*='关闭']",
        )
        for _ in range(3):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(120)
            closed = False
            for selector in close_selectors:
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        locator.first.click(timeout=1000, force=True)
                        page.wait_for_timeout(120)
                        closed = True
                        break
                except Exception:
                    continue
            if not closed:
                # No explicit close button found this round. If no active dialogs are
                # present, exit early.
                try:
                    if page.locator("div.dialog-wrap.active, div[data-type='boss-dialog'].active").count() == 0:
                        break
                except Exception:
                    break

    @staticmethod
    def _extract_years(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", value)
        return float(match.group(1)) if match else None

    def _prepare_long_resume_capture(self) -> None:
        page = self._require_page()
        try:
            page.evaluate(
                """
                () => {
                  const selectorList = [
                    ".dialog-wrap.active",
                    "div[role='dialog']",
                    "div[aria-modal='true']",
                    ".resume-detail-wrap",
                    "div.resume-detail-wrap",
                    "div.geek-resume-wrap",
                    ".iboss-left",
                    "main",
                    "body",
                    "html"
                  ];
                  const state = [];
                  const seen = new Set();
                  const capture = (el) => {
                    if (!el || seen.has(el)) return;
                    seen.add(el);
                    try {
                      const computed = window.getComputedStyle(el);
                      const overflow = `${computed.overflow || ""} ${computed.overflowX || ""} ${computed.overflowY || ""}`;
                      const isBodyLike = el === document.body || el === document.documentElement;
                      const isScrollable = /auto|scroll|hidden/i.test(overflow);
                      const isTall = el.scrollHeight > el.clientHeight + 40;
                      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
                      const isVisible = !rect || (rect.width > 0 && rect.height > 0);
                      if (!isVisible || (!isBodyLike && !isScrollable && !isTall)) {
                        return;
                      }
                      state.push({
                        el,
                        scrollTop: el.scrollTop || 0,
                        height: el.style.height || "",
                        maxHeight: el.style.maxHeight || "",
                        minHeight: el.style.minHeight || "",
                        overflow: el.style.overflow || "",
                        overflowX: el.style.overflowX || "",
                        overflowY: el.style.overflowY || "",
                      });
                      el.style.height = "auto";
                      el.style.maxHeight = "none";
                      el.style.minHeight = "0px";
                      el.style.overflow = "visible";
                      el.style.overflowX = "visible";
                      el.style.overflowY = "visible";
                    } catch (error) {
                      return;
                    }
                  };
                  window.__hrclawResumeCaptureState = state;
                  const roots = [];
                  for (const selector of selectorList) {
                    for (const el of document.querySelectorAll(selector)) {
                      roots.push(el);
                    }
                  }
                  if (!roots.length) {
                    roots.push(document.body);
                  }
                  for (const root of roots) {
                    capture(root);
                    try {
                      root.querySelectorAll("*").forEach((el) => capture(el));
                    } catch (error) {
                      // Ignore invalid roots.
                    }
                  }
                  try {
                    document.documentElement.style.height = "auto";
                    document.documentElement.style.overflow = "visible";
                    document.documentElement.style.overflowX = "visible";
                    document.documentElement.style.overflowY = "visible";
                  } catch (error) {
                    // Ignore document root failures.
                  }
                  try {
                    document.body.style.height = "auto";
                    document.body.style.overflow = "visible";
                    document.body.style.overflowX = "visible";
                    document.body.style.overflowY = "visible";
                  } catch (error) {
                    // Ignore body failures.
                  }
                  window.scrollTo(0, document.body.scrollHeight || 0);
                }
                """
            )
            page.wait_for_timeout(350)
        except Exception:
            return

    def _resume_detail_selectors(self, selectors: BossSelectors | None = None) -> tuple[str, ...]:
        explicit = tuple(selectors.detail_main_text) if selectors is not None else ()
        return tuple(
            dict.fromkeys(
                (
                    ".dialog-wrap.active .iboss-left",
                    ".dialog-wrap.active .geek-resume-wrap",
                    ".dialog-wrap.active .resume-content",
                    "div[data-type='boss-dialog'].active .iboss-left",
                    "div[data-type='boss-dialog'].active .geek-resume-wrap",
                    "div[data-type='boss-dialog'].active .resume-content",
                    *explicit,
                    ".iboss-left",
                    "div.geek-resume-wrap",
                    "div.resume-content",
                )
            )
        )

    def _resume_scroll_container_selectors(self) -> tuple[str, ...]:
        return self._resume_detail_selectors()

    def _capture_resume_scrollable_panel(self, *, target=None) -> bytes | None:
        if Image is None:
            return None
        target = target or self._find_resume_scrollable_target()
        if target is None:
            return None
        _root, locator, metrics = target
        if metrics["client_height"] <= 0 or metrics["scroll_height"] <= 0:
            return None
        if metrics["scroll_height"] <= metrics["client_height"] + 40:
            try:
                return locator.screenshot(type="png")
            except Exception:
                return None

        try:
            snapshot = locator.evaluate(
                """
                (el) => ({
                  scrollTop: el.scrollTop || 0,
                  style: {
                    height: el.style.height || "",
                    maxHeight: el.style.maxHeight || "",
                    minHeight: el.style.minHeight || "",
                    overflow: el.style.overflow || "",
                    overflowX: el.style.overflowX || "",
                    overflowY: el.style.overflowY || "",
                  }
                })
                """
            )
            locator.evaluate(
                """
                (el) => {
                  el.style.height = `${Math.max(el.clientHeight || 0, 200)}px`;
                  el.style.maxHeight = `${Math.max(el.clientHeight || 0, 200)}px`;
                  el.style.minHeight = `${Math.max(el.clientHeight || 0, 200)}px`;
                  el.style.overflow = "auto";
                  el.style.overflowX = "hidden";
                  el.style.overflowY = "auto";
                }
                """
            )
            page = self._require_page()
            page.wait_for_timeout(200)
            # First pass: scroll to bottom to trigger lazy rendering in the resume panel.
            last_scroll_height = 0.0
            stable_bottom_rounds = 0
            for _ in range(18):
                state = locator.evaluate(
                    """
                    (el) => ({
                      top: el.scrollTop || 0,
                      height: el.clientHeight || 0,
                      scrollHeight: el.scrollHeight || 0,
                    })
                    """
                )
                client_height = max(1.0, float(state.get("height") or 0))
                scroll_height = max(client_height, float(state.get("scrollHeight") or 0))
                max_top = max(0.0, scroll_height - client_height)
                locator.evaluate("(el, top) => { el.scrollTop = top; }", max_top)
                page.wait_for_timeout(180)
                refreshed_height = float(
                    locator.evaluate("(el) => el.scrollHeight || 0") or 0.0
                )
                if refreshed_height <= last_scroll_height + 2:
                    stable_bottom_rounds += 1
                else:
                    stable_bottom_rounds = 0
                last_scroll_height = max(last_scroll_height, refreshed_height)
                if stable_bottom_rounds >= 2:
                    break

            locator.evaluate("(el) => { el.scrollTop = 0; }")
            page.wait_for_timeout(160)

            chunks: list[tuple[Image.Image, int, int]] = []
            ratio = 1.0
            max_scroll_height = 0
            max_canvas_bottom = 0
            for _ in range(120):
                state = locator.evaluate(
                    """
                    (el) => ({
                      top: Math.max(0, Math.round(el.scrollTop || 0)),
                      height: Math.max(1, Math.round(el.clientHeight || 1)),
                      scrollHeight: Math.max(1, Math.round(el.scrollHeight || 1)),
                    })
                    """
                )
                top = int(state.get("top") or 0)
                client_height = max(1, int(state.get("height") or 1))
                scroll_height = max(client_height, int(state.get("scrollHeight") or client_height))
                max_scroll_height = max(max_scroll_height, scroll_height)

                raw = locator.screenshot(type="png")
                image = Image.open(io.BytesIO(raw)).convert("RGBA")
                if client_height > 0:
                    ratio = max(ratio, image.height / float(client_height))
                y = max(0, int(round(top * ratio)))
                chunks.append((image, y, scroll_height))
                max_canvas_bottom = max(max_canvas_bottom, y + image.height)

                next_top = min(scroll_height - client_height, top + client_height)
                if next_top <= top:
                    break
                locator.evaluate("(el, top) => { el.scrollTop = top; }", next_top)
                page.wait_for_timeout(180)
                moved_top = int(locator.evaluate("(el) => Math.round(el.scrollTop || 0)") or 0)
                if moved_top <= top:
                    break

            if not chunks:
                return None
            canvas_width = max(image.width for image, _y, _h in chunks)
            estimated_height = int(round(max_scroll_height * ratio)) if max_scroll_height else 0
            canvas_height = max(estimated_height, max_canvas_bottom, 1)
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
            for image, y, _scroll_h in chunks:
                canvas.paste(image, (0, y))
            output = io.BytesIO()
            canvas.save(output, format="PNG")
            return output.getvalue()
        except Exception:
            return None
        finally:
            try:
                locator.evaluate(
                    """
                    (el, payload) => {
                      if (!payload) return;
                      el.scrollTop = payload.scrollTop || 0;
                      el.style.height = payload.style?.height || "";
                      el.style.maxHeight = payload.style?.maxHeight || "";
                      el.style.minHeight = payload.style?.minHeight || "";
                      el.style.overflow = payload.style?.overflow || "";
                      el.style.overflowX = payload.style?.overflowX || "";
                      el.style.overflowY = payload.style?.overflowY || "";
                    }
                    """,
                    snapshot if "snapshot" in locals() else None,
                )
            except Exception:
                pass

    def _find_resume_content_target(self, selectors: BossSelectors | None = None):
        page = self._require_page()
        roots = [page, *page.frames]
        dynamic_target = self._find_dynamic_resume_target(roots)
        if dynamic_target is not None:
            return dynamic_target
        best: tuple[object, object, dict[str, float]] | None = None
        best_score = -1.0
        for root in roots:
            for selector in self._resume_detail_selectors(selectors):
                locator = root.locator(selector)
                try:
                    count = min(locator.count(), 6)
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        metrics = candidate.evaluate(
                            """
                            (el) => {
                              const rect = el.getBoundingClientRect();
                              const style = window.getComputedStyle(el);
                            return {
                                width: rect.width || 0,
                                height: rect.height || 0,
                                left: rect.left || 0,
                                right: rect.right || 0,
                                client_height: el.clientHeight || 0,
                                scroll_height: el.scrollHeight || 0,
                                overflow_y: style.overflowY || "",
                                overflow: style.overflow || "",
                            };
                            }
                            """
                        )
                    except Exception:
                        continue
                    width = float(metrics.get("width") or 0)
                    height = float(metrics.get("height") or 0)
                    left = float(metrics.get("left") or 0)
                    right = float(metrics.get("right") or 0)
                    client_height = float(metrics.get("client_height") or 0)
                    scroll_height = float(metrics.get("scroll_height") or 0)
                    if width < 280 or height < 120:
                        continue
                    try:
                        preview_text = self._cleanup_resume_text(candidate.inner_text())[:1200]
                    except Exception:
                        preview_text = ""
                    if len(preview_text) < 40:
                        continue
                    score = (
                        len(preview_text) * 2
                        + max(0.0, scroll_height - client_height)
                        + (width * 0.2)
                        + self._resume_content_bonus(selector, preview_text)
                    )
                    if "经历概览" in preview_text:
                        score -= 45000
                    if "最近关注" in preview_text or "期望职位" in preview_text:
                        score += 6000
                    if re.search(r"\d{2}岁", preview_text):
                        score += 4000
                    if re.search(r"(本科|硕士|博士|大专)", preview_text):
                        score += 2500
                    if left > self.width * 0.65:
                        score -= 25000
                    if right > self.width * 0.82:
                        score -= 12000
                    if width < 420:
                        score -= 8000
                    if score > best_score:
                        best = (root, candidate, metrics)
                        best_score = score
        return best

    def _find_dynamic_resume_target(self, roots) -> tuple[object, object, dict[str, float]] | None:
        marker = "[data-hrclaw-resume-target='1']"
        for root in roots:
            try:
                result = root.evaluate(
                    """
                    ({positiveMarkers, negativeMarkers}) => {
                      document.querySelectorAll('[data-hrclaw-resume-target="1"]').forEach((el) => {
                        el.removeAttribute('data-hrclaw-resume-target');
                      });
                      const dialog =
                        document.querySelector('.dialog-wrap.active')
                        || document.querySelector("div[data-type='boss-dialog'].active")
                        || document.querySelector('[role="dialog"]');
                      if (!dialog) {
                        return null;
                      }
                      const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1440;
                      const dialogRect = dialog.getBoundingClientRect();
                      const dialogLeft = dialogRect.left || 0;
                      const dialogRight = dialogRect.right || viewportWidth;
                      const dialogWidth = dialogRect.width || Math.max(1, dialogRight - dialogLeft);
                      const leftBoundary = dialogLeft + Math.max(16, dialogWidth * 0.04);
                      const rightBoundary = dialogLeft + dialogWidth * 0.54;
                      const candidates = [...dialog.querySelectorAll('*')];
                      let best = null;
                      let bestScore = -Infinity;
                      for (const el of candidates) {
                        if (!(el instanceof HTMLElement)) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 320 || rect.height < 120) continue;
                        if (rect.left < dialogLeft || rect.right > dialogRight) continue;
                        const centerX = rect.left + rect.width / 2;
                        if (rect.left < leftBoundary - 120) continue;
                        if (centerX > rightBoundary) continue;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') === 0) continue;
                        const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (text.length < 120) continue;
                        let score = text.length;
                        if (el.scrollHeight > el.clientHeight + 60) score += 20000;
                        if (rect.width > 520) score += 6000;
                        if (rect.height > 420) score += 3000;
                        if (rect.width > dialogWidth * 0.7) score -= 24000;
                        if (rect.width > dialogWidth * 0.62) score -= 16000;
                        if (rect.left < dialogLeft + dialogWidth * 0.08) score -= 14000;
                        if (rect.left >= leftBoundary && rect.left <= dialogLeft + dialogWidth * 0.35) score += 9000;
                        if (centerX <= dialogLeft + dialogWidth * 0.38) score += 8000;
                        if (rect.right <= dialogLeft + dialogWidth * 0.58) score += 6000;
                        const classId = `${el.className || ''} ${el.id || ''}`.toLowerCase();
                        if (classId.includes('iboss-left')) score += 18000;
                        if (classId.includes('resume-content') || classId.includes('geek-resume-wrap')) score += 7000;
                        if (classId.includes('resume-detail-wrap')) score -= 12000;
                        if (classId.includes('card-inner') || classId.includes('card-content')) score -= 12000;
                        if (classId.includes('overview') || classId.includes('summary')) score -= 12000;
                        if (/\\b\\d{2}岁\\b/.test(text)) score += 5000;
                        if (/(本科|硕士|博士|大专)/.test(text)) score += 3500;
                        if (/(离职-|在职-|随时到岗|期望职位|最近关注)/.test(text)) score += 4500;
                        for (const marker of positiveMarkers) {
                          if (text.includes(marker)) score += 2500;
                        }
                        for (const marker of negativeMarkers) {
                          if (text.includes(marker)) score -= 25000;
                        }
                        if (text.includes('经历概览')) score -= 45000;
                        if (text.includes('继续沟通') || text.includes('打招呼')) score -= 12000;
                        const dateLikeHits = (text.match(/\\d{4}[./-]\\d{1,2}\\s*[—-至]\\s*(?:\\d{4}[./-]\\d{1,2}|至今)/g) || []).length;
                        const paragraphHits = (text.match(/[。；;]/g) || []).length;
                        if (dateLikeHits >= 3 && paragraphHits === 0) score -= 18000;
                        if (score > bestScore) {
                          best = el;
                          bestScore = score;
                        }
                      }
                      if (!best) return null;
                      best.setAttribute('data-hrclaw-resume-target', '1');
                      const rect = best.getBoundingClientRect();
                      const style = window.getComputedStyle(best);
                      return {
                        width: rect.width || 0,
                        height: rect.height || 0,
                        left: rect.left || 0,
                        right: rect.right || 0,
                        client_height: best.clientHeight || 0,
                        scroll_height: best.scrollHeight || 0,
                        overflow_y: style.overflowY || '',
                        overflow: style.overflow || '',
                      };
                    }
                    """,
                    {
                        "positiveMarkers": list(_RESUME_POSITIVE_MARKERS),
                        "negativeMarkers": list(_RESUME_NEGATIVE_MARKERS),
                    },
                )
            except Exception:
                continue
            if not result:
                continue
            try:
                locator = root.locator(marker)
                if locator.count() == 0:
                    continue
                return (root, locator.first, result)
            except Exception:
                continue
        return None

    def _find_resume_scrollable_target(self):
        target = self._find_resume_content_target()
        if target is None:
            return None
        _root, _locator, metrics = target
        if float(metrics.get("scroll_height") or 0) <= float(metrics.get("client_height") or 0) + 20:
            return None
        return target

    def _extract_resume_scrollable_content(self, *, target=None) -> dict[str, Any]:
        target = target or self._find_resume_content_target()
        if target is None:
            return {"text": "", "html_fragments": []}
        _root, locator, metrics = target
        if metrics["client_height"] <= 0 or metrics["scroll_height"] <= 0:
            return {"text": "", "html_fragments": []}
        try:
            snapshot = locator.evaluate(
                """
                (el) => ({
                  scrollTop: el.scrollTop || 0,
                  style: {
                    height: el.style.height || "",
                    maxHeight: el.style.maxHeight || "",
                    minHeight: el.style.minHeight || "",
                    overflow: el.style.overflow || "",
                    overflowX: el.style.overflowX || "",
                    overflowY: el.style.overflowY || "",
                  }
                })
                """
            )
            locator.evaluate(
                """
                (el) => {
                  const h = Math.max(el.clientHeight || 0, 200);
                  el.style.height = `${h}px`;
                  el.style.maxHeight = `${h}px`;
                  el.style.minHeight = `${h}px`;
                  el.style.overflow = "auto";
                  el.style.overflowX = "hidden";
                  el.style.overflowY = "auto";
                }
                """
            )
            page = self._require_page()
            page.wait_for_timeout(160)
            viewport_height = max(1, int(metrics["client_height"]))
            scroll_height = max(viewport_height, int(metrics["scroll_height"]))
            positions: list[int] = []
            position = 0
            while position < scroll_height:
                positions.append(position)
                position += viewport_height
            last_position = max(0, scroll_height - viewport_height)
            if not positions or positions[-1] != last_position:
                positions.append(last_position)

            text_variants: list[str] = []
            html_fragments: list[str] = []
            seen_text = set()
            seen_html = set()
            for position in positions:
                locator.evaluate("(el, top) => { el.scrollTop = top; }", position)
                page.wait_for_timeout(180)
                try:
                    text = self._cleanup_resume_text(locator.inner_text())
                except Exception:
                    text = ""
                if text:
                    sig = hashlib.sha1(text.encode("utf-8")).hexdigest()
                    if sig not in seen_text:
                        seen_text.add(sig)
                        text_variants.append(text)
                try:
                    html = locator.inner_html()
                except Exception:
                    html = ""
                if html:
                    sig = hashlib.sha1(html.encode("utf-8")).hexdigest()
                    if sig not in seen_html:
                        seen_html.add(sig)
                        html_fragments.append(html)
            if not text_variants:
                try:
                    text_variants.append(self._cleanup_resume_text(locator.inner_text()))
                except Exception:
                    pass
            if not html_fragments:
                try:
                    html_fragments.append(locator.inner_html())
                except Exception:
                    pass
            merged_text = self._merge_markdown_blocks(text_variants) if text_variants else ""
            merged_html = "\n".join(fragment for fragment in html_fragments if fragment)
            return {"text": merged_text, "html_fragments": html_fragments, "html": merged_html, "selector": ""}
        except Exception:
            return {"text": "", "html_fragments": []}
        finally:
            try:
                locator.evaluate(
                    """
                    (el, payload) => {
                      if (!payload) return;
                      el.scrollTop = payload.scrollTop || 0;
                      el.style.height = payload.style?.height || "";
                      el.style.maxHeight = payload.style?.maxHeight || "";
                      el.style.minHeight = payload.style?.minHeight || "";
                      el.style.overflow = payload.style?.overflow || "";
                      el.style.overflowX = payload.style?.overflowX || "";
                      el.style.overflowY = payload.style?.overflowY || "";
                    }
                    """,
                    snapshot if "snapshot" in locals() else None,
                )
            except Exception:
                pass

    def _restore_scroll_after_capture(self) -> None:
        page = self._require_page()
        try:
            page.evaluate(
                """
                () => {
                  const state = window.__hrclawResumeCaptureState || [];
                  for (const item of state) {
                    if (!item || !item.el) continue;
                    try {
                      item.el.scrollTop = item.scrollTop || 0;
                      item.el.style.height = item.height || "";
                      item.el.style.maxHeight = item.maxHeight || "";
                      item.el.style.minHeight = item.minHeight || "";
                      item.el.style.overflow = item.overflow || "";
                      item.el.style.overflowX = item.overflowX || "";
                      item.el.style.overflowY = item.overflowY || "";
                    } catch (error) {
                      // Ignore stale detached nodes.
                    }
                  }
                  window.__hrclawResumeCaptureState = [];
                  try {
                    document.documentElement.style.height = "";
                    document.documentElement.style.overflow = "";
                    document.documentElement.style.overflowX = "";
                    document.documentElement.style.overflowY = "";
                  } catch (error) {
                    // Ignore document root failures.
                  }
                  try {
                    document.body.style.height = "";
                    document.body.style.overflow = "";
                    document.body.style.overflowX = "";
                    document.body.style.overflowY = "";
                  } catch (error) {
                    // Ignore body failures.
                  }
                  window.scrollTo(0, 0);
                }
                """
            )
            page.wait_for_timeout(120)
        except Exception:
            return
