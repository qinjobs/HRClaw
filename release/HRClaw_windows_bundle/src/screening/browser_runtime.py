from __future__ import annotations

import base64
import hashlib
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

from .boss_selectors import BossSelectors


class BrowserRuntimeError(RuntimeError):
    pass


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
        self.load_storage_state = load_storage_state
        self.persist_storage_state_on_stop = persist_storage_state_on_stop
        self.session_id: str | None = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self) -> str:
        if sync_playwright is None:
            raise BrowserRuntimeError("Playwright is not installed. Install with: python3 -m pip install playwright && python3 -m playwright install chromium")

        self.session_id = str(uuid.uuid4())
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.resume_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        context_kwargs: dict[str, Any] = {
            "viewport": {"width": self.width, "height": self.height},
            "accept_downloads": True,
        }
        if self.load_storage_state and self.storage_state_path.exists():
            context_kwargs["storage_state"] = str(self.storage_state_path)
        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()
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

        self._prepare_long_resume_capture()
        try:
            return self._page.screenshot(type="png", full_page=True)
        except Exception:
            return self._page.screenshot(type="png")
        finally:
            self._restore_scroll_after_capture()

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
        timeout_ms: int = 20000,
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
        try:
            body_text = page.locator("body").inner_text()[:2000]
        except Exception:
            return False
        markers = (
            "请完成验证",
            "点击按钮开始验证",
            "拖动滑块",
            "安全验证",
            "请点击图中",
            "verify-slider",
        )
        return any(marker in body_text for marker in markers)

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
        text = self.text_content_any(selectors.detail_main_text) or self.text_content_any(("body",)) or ""
        return {"detail_url": self.current_url, "page_text": text.strip()}

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
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()

    def _require_page(self):
        if self._page is None:
            raise BrowserRuntimeError("Browser session not started.")
        return self._page

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
                    ".dialog-wrap.active .resume-detail-wrap",
                    ".dialog-wrap.active .iboss-left",
                    "div.resume-detail-wrap",
                    "div.geek-resume-wrap",
                    ".iboss-left",
                    "main",
                    "body"
                  ];
                  for (const selector of selectorList) {
                    for (const el of document.querySelectorAll(selector)) {
                      if (el && el.scrollHeight > el.clientHeight + 80) {
                        el.scrollTop = el.scrollHeight;
                      }
                    }
                  }
                  window.scrollTo(0, document.body.scrollHeight || 0);
                }
                """
            )
            page.wait_for_timeout(350)
        except Exception:
            return

    def _restore_scroll_after_capture(self) -> None:
        page = self._require_page()
        try:
            page.evaluate(
                """
                () => {
                  const selectorList = [
                    ".dialog-wrap.active .resume-detail-wrap",
                    ".dialog-wrap.active .iboss-left",
                    "div.resume-detail-wrap",
                    "div.geek-resume-wrap",
                    ".iboss-left",
                    "main",
                    "body"
                  ];
                  for (const selector of selectorList) {
                    for (const el of document.querySelectorAll(selector)) {
                      if (el && el.scrollTop) {
                        el.scrollTop = 0;
                      }
                    }
                  }
                  window.scrollTo(0, 0);
                }
                """
            )
            page.wait_for_timeout(120)
        except Exception:
            return
