from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

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
    "转发",
    "转发牛人",
    "打招呼",
    "立即沟通",
    "立即开聊",
    "下载简历",
    "经历概览",
    "最近关注",
    "牛人最近7天沟通过的职位",
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
        self._recommend_expected_card: dict[str, Any] | None = None

    def start(self) -> str:
        if sync_playwright is None:
            raise BrowserRuntimeError("Playwright is not installed. Install with: python3 -m pip install playwright && python3 -m playwright install chromium")

        self.session_id = str(uuid.uuid4())
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.resume_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        attached = self._try_attach_to_existing_browser()
        if not attached:
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

    def _try_attach_to_existing_browser(self) -> bool:
        if not self.cdp_url:
            return False
        if self._playwright is None:
            return False

        attempted: list[str] = []
        errors: list[str] = []
        for endpoint in self._candidate_cdp_urls():
            if endpoint in attempted:
                continue
            attempted.append(endpoint)
            connect_target = self._resolve_cdp_connect_target(endpoint)
            try:
                browser = self._playwright.chromium.connect_over_cdp(connect_target)
                contexts = list(getattr(browser, "contexts", []) or [])
                if not contexts:
                    try:
                        browser.close()
                    except Exception:
                        pass
                    raise BrowserRuntimeError(
                        f"No browser context available on attached Chrome session: {connect_target}. "
                        "Start Chrome with a visible profile and remote debugging enabled."
                    )
                self._browser = browser
                self._owns_browser = False
                self._context = contexts[0]
                self._owns_context = False
                self._page = self._select_attached_page(self._context.pages)
                if self._page is None:
                    self._page = self._context.new_page()
                    self._owns_page = True
                else:
                    self._owns_page = False
                self.cdp_url = connect_target
                self.attached_to_existing_browser = True
                if self.start_url and self._is_blank_page_url(self._page.url):
                    self._page.goto(self.start_url, wait_until="domcontentloaded")
                return True
            except Exception as exc:
                errors.append(f"{endpoint} (connect={connect_target}) -> {exc}")

        require_attach = str(os.getenv("SCREENING_BROWSER_CDP_REQUIRED", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if require_attach:
            raise BrowserRuntimeError(
                "Unable to attach to Chrome CDP endpoint. "
                f"Tried: {', '.join(attempted)}. "
                f"Errors: {' | '.join(errors)}"
            )

        # Fall back to launching a managed browser when CDP endpoint is stale
        # (for example, when Chrome restarts and random remote-debugging ports rotate).
        self.cdp_url = None
        self.attached_to_existing_browser = False
        return False

    def _candidate_cdp_urls(self) -> tuple[str, ...]:
        candidates: list[str] = []

        def add_candidate(value: Any) -> None:
            normalized = self._normalize_cdp_url(value)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

        add_candidate(self.cdp_url)
        fallback_ports = os.getenv("SCREENING_BROWSER_FALLBACK_CDP_PORTS", "9222,9223")
        for token in re.split(r"[,\s]+", str(fallback_ports or "").strip()):
            if token:
                add_candidate(token)
        return tuple(candidates)

    def _resolve_cdp_connect_target(self, endpoint: str) -> str:
        normalized = self._normalize_cdp_url(endpoint) or endpoint
        if normalized.startswith(("ws://", "wss://")):
            return normalized
        if not normalized.startswith(("http://", "https://")):
            return normalized
        discovered_ws = self._discover_cdp_websocket_url(normalized)
        return discovered_ws or normalized

    def _discover_cdp_websocket_url(self, endpoint: str) -> str | None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"}:
            return None
        base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        if not base:
            return None
        probe_paths = (
            "/json/version",
            "/json/version/",
            "/json",
            "/json/list",
        )
        for path in probe_paths:
            url = f"{base}{path}"
            payload = self._http_json(url)
            ws_url = self._extract_websocket_debugger_url(payload)
            if ws_url:
                return ws_url
        return None

    @staticmethod
    def _http_json(url: str, *, timeout_seconds: float = 1.5):
        try:
            request = urllib_request.Request(url, headers={"Accept": "application/json"})
            with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError):
            return None
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_websocket_debugger_url(payload: Any) -> str | None:
        if isinstance(payload, dict):
            value = payload.get("webSocketDebuggerUrl")
            return str(value).strip() if value else None
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                value = item.get("webSocketDebuggerUrl")
                if value:
                    return str(value).strip()
        return None

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
        if target is None:
            target = self._find_resume_dialog_panel_target()
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
        iframe_target = self._find_recommend_resume_iframe_target()
        if iframe_target is not None:
            _root, locator, _metrics = iframe_target
            try:
                return locator.screenshot(type="png")
            except Exception:
                pass
        if self._is_recommend_page_url(self.current_url) or self._has_recommend_resume_frame():
            try:
                active_dialog = self._active_recommend_dialog_locator()
            except Exception:
                active_dialog = None
            if active_dialog is not None:
                try:
                    if active_dialog.count() > 0:
                        return active_dialog.first.screenshot(type="png")
                except Exception:
                    pass
        self._prepare_long_resume_capture()
        try:
            try:
                return self._page.screenshot(type="png", full_page=True)
            except Exception:
                return self._page.screenshot(type="png")
        finally:
            self._restore_scroll_after_capture()

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
            active_dialog = self._active_recommend_dialog_locator()
            if active_dialog is None:
                return None
            try:
                return active_dialog.first.screenshot(type="png")
            except Exception:
                return None
        try:
            return page.screenshot(type="png", clip=clip)
        except Exception:
            active_dialog = self._active_recommend_dialog_locator()
            if active_dialog is None:
                return None
            try:
                return active_dialog.first.screenshot(type="png")
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

    def _wait_for_any_global(self, selectors: Sequence[str], *, timeout_ms: int = 10000) -> str | None:
        if not selectors:
            return None
        page = self._require_page()
        deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
        while time.monotonic() <= deadline:
            roots = [page, *self._page_frames(page)]
            for root in roots:
                for selector in selectors:
                    try:
                        if root.locator(selector).count() > 0:
                            return selector
                    except Exception:
                        continue
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            try:
                page.wait_for_timeout(min(250, max(50, remaining_ms)))
            except Exception:
                break
        return None

    def goto_search_page(self, selectors: BossSelectors) -> str:
        return self.goto(selectors.search_url)

    def prepare_recommend_login(
        self,
        *,
        login_url: str | None = None,
        wait_timeout_ms: int = 15000,
    ) -> dict[str, Any]:
        if not self.attached_to_existing_browser or not self._is_loopback_cdp_port(9222):
            return {"opened": False, "waited": False, "reason": "cdp_9222_not_attached"}

        if self._context is None:
            raise BrowserRuntimeError("Browser context is not ready for recommend login preparation.")

        target_url = login_url or "https://www.zhipin.com/web/user/?ka=header-login"
        page = None
        reused_current_page = False
        try:
            page = self._context.new_page()
            self._owns_page = True
        except Exception:
            page = self._require_page()
            reused_current_page = True
            self._owns_page = False

        self._page = page
        try:
            try:
                page.bring_to_front()
            except Exception:
                pass
            should_navigate = True
            try:
                current = str(page.url or "").strip()
            except Exception:
                current = ""
            if current:
                current_parsed = urlparse(current)
                target_parsed = urlparse(target_url)
                should_navigate = not (
                    current_parsed.scheme == target_parsed.scheme
                    and current_parsed.netloc == target_parsed.netloc
                    and current_parsed.path.rstrip("/") == target_parsed.path.rstrip("/")
                    and current_parsed.query == target_parsed.query
                )
            if should_navigate:
                page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(max(1000, wait_timeout_ms))
            return {
                "opened": True,
                "waited": True,
                "reused_current_page": reused_current_page,
                "url": page.url,
            }
        except Exception as exc:
            raise BrowserRuntimeError(f"Failed to prepare recommend login page: {exc}") from exc

    def goto_recommend_page(self, selectors: BossSelectors) -> str:
        page = self._require_page()
        if self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=True):
            return self.current_url
        current_url = (self.current_url or "").lower()
        chat_home_url = os.getenv("SCREENING_BOSS_CHAT_URL", "https://www.zhipin.com/web/chat/index")
        if "/web/chat/" not in current_url:
            page.goto(chat_home_url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
        if self._open_recommend_from_chat_menu(selectors):
            if self.wait_for_recommend_list_ready(selectors, timeout_ms=8000):
                return self.current_url
            if self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=True):
                return self.current_url
            return page.url
        url = self.goto(selectors.recommend_url)
        if self.wait_for_recommend_list_ready(selectors, timeout_ms=6000):
            return url
        if self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=True):
            return self.current_url
        return url

    def is_login_scan_page(self) -> bool:
        page = self._require_page()
        current_url = (self.current_url or "").lower()
        try:
            body_text = page.locator("body").inner_text()[:3000]
        except Exception:
            return False
        normalized = body_text.lower()
        markers = (
            "app扫码登录",
            "扫码登录",
            "扫码帮助",
            "验证码登录/注册",
            "登录/注册",
            "请先登录",
            "登录后查看",
        )
        marker_hit = any(marker in normalized for marker in markers)
        if not marker_hit:
            return False

        login_url_hint = any(token in current_url for token in ("/web/user", "/login", "login", "register"))
        if login_url_hint:
            return True

        # Some anti-bot redirects land on the homepage/login overlay instead of
        # explicit /login routes. Detect common login containers before waiting.
        login_selectors = (
            "div.login-wrap",
            "div.login-box",
            "form[action*='login']",
            "input[type='password']",
            "input[placeholder*='手机号']",
            "button:has-text('登录')",
            "a:has-text('登录')",
            "text=扫码登录",
        )
        for selector in login_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        # Fallback: homepage-like URL with login markers should still trigger a
        # short manual wait so HR can finish QR scan without automatic retries.
        if "/web/chat/" not in current_url and "/web/geek/" not in current_url and "/web/boss/" not in current_url:
            return True
        return False

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
        try:
            initial_count = card_locator.count() if card_locator is not None else 0
        except Exception:
            initial_count = 0
        if initial_count <= 0 and self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=True):
            scope = self._resolve_recommend_scope(selectors)
            card_locator = self._locator_for_any(selectors.recommend_candidate_card, scope=scope)
            if card_locator is None:
                card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
        if card_locator is None:
            return []

        self._expand_cards_by_scrolling(card_locator, limit=limit, scope=scope)

        def resolve_card_locator():
            fresh_scope = self._resolve_recommend_scope(selectors)
            fresh_locator = self._locator_for_any(selectors.recommend_candidate_card, scope=fresh_scope)
            if fresh_locator is None:
                fresh_locator = self._locator_for_any(selectors.candidate_card, scope=fresh_scope)
            return fresh_scope, fresh_locator

        def card_snapshot(index: int):
            last_error: Exception | None = None
            for _ in range(2):
                fresh_scope, fresh_locator = resolve_card_locator()
                if fresh_locator is None:
                    return None
                try:
                    count = fresh_locator.count()
                except Exception as exc:
                    last_error = exc
                    continue
                if index >= count:
                    return None
                card = fresh_locator.nth(index)
                try:
                    raw_href = self._attribute_from_scope(card, selectors.recommend_candidate_name_link, "href")
                    detail_url = None if not raw_href or raw_href.startswith("javascript") else self._absolute_url(raw_href)
                    try:
                        full_card_text = card.inner_text().strip()
                    except Exception:
                        full_card_text = ""
                    name = self._text_from_scope(card, selectors.candidate_name) or self._text_from_scope(
                        card,
                        selectors.recommend_candidate_name_link,
                    )
                    current_title = self._text_from_scope(card, selectors.candidate_title)
                    current_company = self._text_from_scope(card, selectors.candidate_company)
                    years_experience = self._extract_years(self._text_from_scope(card, selectors.candidate_experience))
                    education_level = self._text_from_scope(card, selectors.candidate_education)
                    location = self._text_from_scope(card, selectors.candidate_location)
                    last_active_time = self._text_from_scope(card, selectors.candidate_active_time)
                    external_id = self._extract_external_id(
                        card,
                        selectors.recommend_candidate_external_id,
                        detail_url,
                        index + 1,
                        fallback_text=full_card_text,
                    )
                    return {
                        "card_index": index,
                        "external_id": external_id,
                        "name": name,
                        "current_title": current_title,
                        "current_company": current_company,
                        "years_experience": years_experience,
                        "education_level": education_level,
                        "location": location,
                        "last_active_time": last_active_time,
                        "detail_url": detail_url,
                        "summary_text": full_card_text,
                    }
                except Exception as exc:
                    last_error = exc
                    continue
            if last_error is not None:
                raise last_error
            return None

        items = []
        try:
            total_count = card_locator.count()
        except Exception:
            _fresh_scope, fresh_locator = resolve_card_locator()
            total_count = fresh_locator.count() if fresh_locator is not None else 0
        scan_count = min(total_count, max(limit * 6, limit + 8, 12))
        for index in range(scan_count):
            try:
                snapshot = card_snapshot(index)
            except Exception:
                continue
            if snapshot is None:
                continue
            if not self._is_meaningful_recommend_card(
                full_card_text=snapshot.get("summary_text"),
                detail_url=snapshot.get("detail_url"),
                name=snapshot.get("name"),
                current_title=snapshot.get("current_title"),
                current_company=snapshot.get("current_company"),
                years_experience=snapshot.get("years_experience"),
                education_level=snapshot.get("education_level"),
                location=snapshot.get("location"),
                last_active_time=snapshot.get("last_active_time"),
            ):
                continue
            items.append(snapshot)
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _is_meaningful_recommend_card(
        *,
        full_card_text: str | None,
        detail_url: str | None,
        name: str | None,
        current_title: str | None,
        current_company: str | None,
        years_experience: float | None,
        education_level: str | None,
        location: str | None,
        last_active_time: str | None,
    ) -> bool:
        summary = str(full_card_text or "").strip()
        if detail_url:
            return True
        if any(
            value not in (None, "")
            for value in (
                name,
                current_title,
                current_company,
                years_experience,
                education_level,
                location,
                last_active_time,
            )
        ):
            return True
        return len(summary) >= 20

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

    def _recommend_detail_signature(self) -> str | None:
        try:
            panel_target = self._find_resume_dialog_panel_target()
        except Exception:
            panel_target = None
        if panel_target is not None:
            try:
                _root, locator, _metrics = panel_target
                text = self._cleanup_resume_text(locator.inner_text())
                if len(text) >= 40:
                    return text[:1200]
            except Exception:
                pass
        try:
            active_dialog = self._active_recommend_dialog_locator()
        except Exception:
            active_dialog = None
        if active_dialog is None:
            return None
        try:
            text = self._cleanup_resume_text(active_dialog.first.inner_text())
        except Exception:
            return None
        if len(text) < 40:
            return None
        return text[:1200]

    def _recommend_expected_name_hint(self) -> str:
        card = self._recommend_expected_card if isinstance(self._recommend_expected_card, dict) else {}
        return str(card.get("name") or "").strip()

    @staticmethod
    def _detail_text_matches_expected_candidate(
        text: str | None,
        *,
        expected_name: str,
        expected_external_id: str,
    ) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        if expected_external_id and expected_external_id in normalized:
            return True
        if expected_name and expected_name in normalized:
            return True
        return False

    def _recommend_detail_matches_card(
        self,
        selectors: BossSelectors,
        card: dict[str, Any],
        *,
        detail_state: dict[str, Any] | None = None,
    ) -> bool:
        expected_name = str(card.get("name") or "").strip()
        expected_external_id = str(card.get("external_id") or "").strip()
        if not expected_name and not expected_external_id:
            return True
        if expected_external_id.startswith("playwright-"):
            expected_external_id = ""

        texts: list[str] = []

        def add_text(value: str | None) -> None:
            normalized = self._cleanup_resume_text(value)
            if normalized and normalized not in texts:
                texts.append(normalized[:2400])

        if isinstance(detail_state, dict):
            add_text(detail_state.get("signature"))
        try:
            target = self._find_resume_content_target(selectors)
        except Exception:
            target = None
        if target is not None:
            try:
                _root, locator, _metrics = target
                add_text(locator.inner_text())
            except Exception:
                pass
        try:
            panel_target = self._find_resume_dialog_panel_target()
        except Exception:
            panel_target = None
        if panel_target is not None:
            try:
                _root, locator, _metrics = panel_target
                add_text(locator.inner_text())
            except Exception:
                pass
        add_text(self._recommend_detail_signature())
        try:
            active_dialog = self._active_recommend_dialog_locator()
        except Exception:
            active_dialog = None
        if active_dialog is not None:
            try:
                add_text(active_dialog.first.inner_text())
            except Exception:
                pass
        try:
            iframe_target = self._find_recommend_resume_iframe_target()
        except Exception:
            iframe_target = None
        if iframe_target is not None:
            try:
                _root, locator, _metrics = iframe_target
                add_text(locator.get_attribute("src"))
            except Exception:
                pass
        add_text(self.current_url)
        try:
            for frame in self._page_frames(self._require_page()):
                add_text(self._frame_url_value(frame))
        except Exception:
            pass

        return any(
            self._detail_text_matches_expected_candidate(
                text,
                expected_name=expected_name,
                expected_external_id=expected_external_id,
            )
            for text in texts
        ) or (
            isinstance(detail_state, dict)
            and bool(detail_state.get("has_resume_frame"))
            and self._recommend_card_has_opened_state(self._resolve_recommend_card_scope(selectors, card))
        )

    @staticmethod
    def _recommend_card_has_opened_state(card_scope: Any) -> bool:
        if card_scope is None:
            return False
        try:
            state = card_scope.evaluate(
                """
                (root) => {
                  const targets = [
                    root,
                    root.querySelector('.candidate-card-wrap'),
                    root.querySelector('.card-inner.common-wrap'),
                    root.querySelector('.card-inner'),
                  ].filter(Boolean);
                  return targets.map((node) => ({
                    className: String(node.className || '').toLowerCase(),
                    ariaExpanded: String(node.getAttribute('aria-expanded') || '').toLowerCase(),
                    ariaSelected: String(node.getAttribute('aria-selected') || '').toLowerCase(),
                    dataStatus: String(node.getAttribute('data-status') || '').toLowerCase(),
                  }));
                }
                """
            )
        except Exception:
            return False
        for item in state or []:
            class_name = str(item.get("className") or "")
            if "has-viewed" in class_name or "active" in class_name or "selected" in class_name:
                return True
            if str(item.get("ariaExpanded") or "") == "true":
                return True
            if str(item.get("ariaSelected") or "") == "true":
                return True
            if str(item.get("dataStatus") or "") in {"active", "selected", "opened", "viewed"}:
                return True
        return False

    @staticmethod
    def _is_loading_resume_text(text: str | None) -> bool:
        normalized = str(text or "").strip().lower()
        if not normalized:
            return False
        if "加载中，请稍候" in normalized:
            return True
        markers = ("加载中", "请稍候", "loading")
        return len(normalized) <= 80 and any(marker in normalized for marker in markers)

    def _has_recommend_resume_frame(self) -> bool:
        page = self._require_page()
        for frame in self._page_frames(page):
            frame_url = self._frame_url_value(frame).lower()
            if "/web/frame/c-resume/" in frame_url or "/web/geek/job-recommend/" in frame_url:
                return True
        return False

    def _find_recommend_resume_iframe_target(self) -> tuple[object, object, dict[str, float]] | None:
        page = self._require_page()
        iframe_selectors = (
            "iframe[src*='/web/frame/c-resume/']",
            "iframe[src*='/web/geek/job-recommend/']",
        )
        best: tuple[object, object, dict[str, float]] | None = None
        best_score = -1.0
        for root in [page, *self._page_frames(page)]:
            frame_url = self._frame_url_value(root).lower()
            for selector in iframe_selectors:
                try:
                    locator = root.locator(selector)
                except Exception:
                    continue
                try:
                    count = min(locator.count(), 4)
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        box = candidate.bounding_box()
                    except Exception:
                        box = None
                    width = float((box or {}).get("width") or 0)
                    height = float((box or {}).get("height") or 0)
                    if box is not None and width < 120 and height < 120:
                        continue
                    try:
                        src = str(candidate.get_attribute("src") or "").lower()
                    except Exception:
                        src = ""
                    score = width + height
                    if "/web/frame/c-resume/" in src:
                        score += 5000
                    if "/web/geek/job-recommend/" in src:
                        score += 2500
                    if "/web/frame/recommend/" in frame_url:
                        score += 1000
                    if score > best_score:
                        left = float((box or {}).get("x") or 0)
                        top = float((box or {}).get("y") or 0)
                        metrics = {
                            "width": width,
                            "height": height,
                            "left": left,
                            "top": top,
                            "right": left + width,
                            "bottom": top + height,
                        }
                        best = (root, candidate, metrics)
                        best_score = score
        return best

    def _has_recommend_resume_surface(self) -> bool:
        if self._page is None:
            return False
        try:
            if self._find_recommend_resume_iframe_target() is not None:
                return True
        except Exception:
            pass
        try:
            return self._has_recommend_resume_frame()
        except Exception:
            return False

    @staticmethod
    def _is_canvas_only_resume_html(content_html: str | None) -> bool:
        normalized = str(content_html or "").lower()
        if not normalized or "<canvas" not in normalized:
            return False
        text_tags = ("<p", "<li", "<span", "<section", "<article", "<h1", "<h2", "<h3", "<h4", "<dl", "<dt", "<dd")
        return not any(tag in normalized for tag in text_tags)

    @staticmethod
    def _is_recommend_overview_markup(selector: str | None = None, content_html: str | None = None) -> bool:
        markers = (
            "boss-popup__wrapper",
            "boss-dialog__wrapper",
            "dialog-lib-resume",
            "recommendv2",
            "lib-standard-resume",
            "resume-right-side",
            "resume-simple-box",
            "resume-item-detail",
            "resume-summary",
        )
        normalized_selector = re.sub(r"\s+", " ", str(selector or "")).strip().lower()
        if normalized_selector and any(marker in normalized_selector for marker in markers):
            return True
        normalized_html = str(content_html or "").lower()
        return bool(normalized_html) and any(marker in normalized_html for marker in markers)

    @classmethod
    def _looks_like_recommend_overview_text(cls, text: str | None) -> bool:
        normalized = cls._cleanup_resume_text(text)
        if not normalized:
            return False
        lowered = normalized.lower()
        if "经历概览" in normalized or "experience overview" in lowered:
            return True
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if len(lines) < 3:
            return False
        long_lines = sum(1 for line in lines if len(line) >= 28)
        date_like_lines = sum(
            1
            for line in lines
            if re.search(r"(19|20)\d{2}", line)
            and any(token in line.lower() for token in ("-", "/", ".", "至今", "present"))
        )
        return long_lines == 0 and date_like_lines >= max(2, len(lines) // 2)

    def _sanitize_recommend_resume_target(self, target):
        if target is None or not self._has_recommend_resume_surface():
            return target
        _root, locator, _metrics = target
        try:
            selector = locator.evaluate("(el) => `${el.className || ''} ${el.id || ''}`")
        except Exception:
            selector = ""
        try:
            content_html = locator.inner_html()
        except Exception:
            content_html = None
        if self._is_recommend_overview_markup(selector, content_html):
            return None
        return target

    def _extract_recommend_resume_iframe_payload(self) -> dict[str, Any] | None:
        page = self._page
        if page is None:
            return None
        best_payload: dict[str, Any] | None = None
        best_score = float("-inf")
        for frame in self._page_frames(page):
            frame_url = self._frame_url_value(frame).lower()
            if "/web/frame/c-resume/" not in frame_url and "/web/geek/job-recommend/" not in frame_url:
                continue
            page_text = ""
            content_html = None
            page_html = None
            try:
                body = frame.locator("body")
                if body.count() > 0:
                    page_text = self._cleanup_resume_text(body.first.inner_text())
                    content_html = body.first.inner_html()
            except Exception:
                pass
            try:
                page_html = frame.content()
            except Exception:
                page_html = None
            content_html = content_html or page_html
            canvas_only = self._is_canvas_only_resume_html(content_html or page_html)
            score = len(page_text)
            if "/web/frame/c-resume/" in frame_url:
                score += 10000
            if "/web/geek/job-recommend/" in frame_url:
                score += 2000
            if canvas_only:
                score += 500
            elif content_html:
                score += min(len(content_html), 4000)
            payload = {
                "detail_url": self.current_url,
                "page_text": page_text,
                "content_html": None if canvas_only else content_html,
                "page_html": page_html,
                "content_selector": "recommend_resume_iframe",
                "_canvas_only": canvas_only,
            }
            if score > best_score:
                best_payload = payload
                best_score = score
        return best_payload

    def _recommend_detail_state(self, selectors: BossSelectors) -> dict[str, Any]:
        try:
            active_dialog = self._active_recommend_dialog_locator()
        except Exception:
            active_dialog = None
        has_dialog = False
        if active_dialog is not None:
            try:
                has_dialog = active_dialog.count() > 0
            except Exception:
                has_dialog = False
        has_panel = False
        try:
            has_panel = self._find_resume_dialog_panel_target() is not None
        except Exception:
            has_panel = False
        has_resume_iframe = False
        try:
            has_resume_iframe = self._find_recommend_resume_iframe_target() is not None
        except Exception:
            has_resume_iframe = False
        signature = self._recommend_detail_signature()
        content_ready = bool(signature) and not self._is_loading_resume_text(signature)
        if has_resume_iframe:
            content_ready = True
        return {
            "ready_visible": bool(has_dialog or has_panel or has_resume_iframe),
            "has_dialog": has_dialog,
            "has_panel": has_panel,
            "has_resume_frame": self._has_recommend_resume_frame(),
            "has_resume_iframe": has_resume_iframe,
            "signature": signature,
            "content_ready": content_ready,
        }

    def _has_inline_recommend_detail(self, selectors: BossSelectors) -> bool:
        try:
            if self._find_recommend_resume_iframe_target() is not None:
                return True
        except Exception:
            pass
        try:
            if self._find_resume_dialog_panel_target() is not None:
                return True
        except Exception:
            pass
        return self._has_active_recommend_dialog()

    def _recommend_detail_is_open(
        self,
        selectors: BossSelectors,
        *,
        detail_state: dict[str, Any] | None = None,
    ) -> bool:
        state = detail_state if isinstance(detail_state, dict) else self._recommend_detail_state(selectors)
        return bool(
            state.get("ready_visible")
            or state.get("has_dialog")
            or state.get("has_panel")
            or state.get("has_resume_frame")
            or state.get("has_resume_iframe")
        )

    def _recommend_card_locator(self, selectors: BossSelectors, scope: Any):
        card_locator = self._locator_for_any(selectors.recommend_candidate_card, scope=scope)
        if card_locator is None:
            card_locator = self._locator_for_any(selectors.candidate_card, scope=scope)
        return card_locator

    def _recommend_card_identity(
        self,
        card_scope: Any,
        selectors: BossSelectors,
    ) -> dict[str, str | None]:
        try:
            summary_text = card_scope.inner_text().strip()
        except Exception:
            summary_text = ""
        name = self._text_from_scope(card_scope, selectors.candidate_name) or self._text_from_scope(
            card_scope,
            selectors.recommend_candidate_name_link,
        )
        external_id = self._extract_external_id(
            card_scope,
            selectors.recommend_candidate_external_id,
            None,
            1,
            fallback_text=summary_text,
        )
        return {
            "external_id": external_id,
            "name": name,
            "summary_text": summary_text,
        }

    def _recommend_card_matches(
        self,
        card_scope: Any,
        selectors: BossSelectors,
        expected_card: dict[str, Any],
    ) -> bool:
        current = self._recommend_card_identity(card_scope, selectors)
        expected_external_id = str(expected_card.get("external_id") or "").strip()
        current_external_id = str(current.get("external_id") or "").strip()
        expected_name = str(expected_card.get("name") or "").strip()
        current_name = str(current.get("name") or "").strip()
        if (
            expected_external_id
            and current_external_id
            and not expected_external_id.startswith("playwright-")
        ):
            return current_external_id == expected_external_id
        if expected_external_id and current_external_id and not expected_external_id.startswith("playwright-"):
            return False
        if expected_name and current_name:
            return current_name == expected_name
        expected_summary = str(expected_card.get("summary_text") or "").strip()
        current_summary = str(current.get("summary_text") or "").strip()
        if expected_summary and current_summary and not expected_name and not expected_external_id:
            expected_prefix = expected_summary[:120]
            current_prefix = current_summary[:120]
            if expected_prefix == current_prefix:
                return True
        return False

    @staticmethod
    def _recommend_card_has_identity(expected_card: dict[str, Any]) -> bool:
        return any(str(expected_card.get(field) or "").strip() for field in ("external_id", "name", "summary_text"))

    def _resolve_recommend_card_scope(self, selectors: BossSelectors, card: dict[str, Any]):
        scope = self._resolve_recommend_scope(selectors)
        card_locator = self._recommend_card_locator(selectors, scope)
        if card_locator is None:
            return None
        try:
            count = card_locator.count()
        except Exception:
            count = 0
        card_index = int(card.get("card_index") or 0)
        if 0 <= card_index < count:
            scoped = card_locator.nth(card_index)
            try:
                if self._recommend_card_matches(scoped, selectors, card):
                    return scoped
            except Exception:
                if not self._recommend_card_has_identity(card):
                    return scoped
        for index in range(min(count, 12)):
            try:
                scoped = card_locator.nth(index)
                if self._recommend_card_matches(scoped, selectors, card):
                    return scoped
            except Exception:
                continue
        if 0 <= card_index < count:
            return card_locator.nth(card_index)
        return None

    @staticmethod
    def _is_probable_anchor_locator(locator: Any) -> bool:
        if locator is None:
            return False
        try:
            href = locator.first.get_attribute("href")
        except Exception:
            href = None
        href_value = str(href or "").strip().lower()
        return bool(href_value and not href_value.startswith("javascript"))

    @staticmethod
    def _click_locator(locator: Any, *, timeout_ms: int = 5000, position: dict[str, float] | None = None) -> bool:
        if locator is None:
            return False
        click_kwargs: dict[str, Any] = {"timeout": timeout_ms}
        if position is not None:
            click_kwargs["position"] = position
        for force in (False, True):
            try:
                if force:
                    locator.click(force=True, **click_kwargs)
                else:
                    locator.click(**click_kwargs)
                return True
            except Exception:
                continue
        return False

    def _click_recommend_resume_hotspot(self, card_scope: Any) -> bool:
        hotspot_specs = (
            (("span.name", ".name", ".row.name-wrap .name", ".name-wrap .name"), None),
            ((".row.name-wrap", ".name-wrap"), {"x": 20, "y": 10}),
            ((":scope > div:first-child", ":scope > div:first-child > div:first-child"), {"x": 32, "y": 24}),
            ((".avatar-wrap",), {"x": 18, "y": 18}),
            ((".card-inner.common-wrap", ".card-inner"), None),
            ((".candidate-card-wrap",), None),
            ((".col-2",), None),
            ((".col-2",), {"x": 32, "y": 20}),
        )
        for selectors, position in hotspot_specs:
            locator = self._locator_for_any(selectors, scope=card_scope)
            if locator is None:
                continue
            try:
                candidate = locator.first
            except Exception:
                candidate = locator
            try:
                candidate.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            if self._click_locator(candidate, timeout_ms=5000):
                return True
            if position is not None and self._click_locator(candidate, timeout_ms=5000, position=position):
                return True
        if self._click_locator(card_scope, timeout_ms=5000):
            return True
        for position in ({"x": 160, "y": 40}, {"x": 120, "y": 36}, {"x": 80, "y": 24}):
            if self._click_locator(card_scope, timeout_ms=5000, position=position):
                return True
        return False

    @staticmethod
    def _dispatch_recommend_card_click(card_scope: Any) -> bool:
        if card_scope is None:
            return False
        selectors = (
            ":scope > div:first-child",
            ":scope > div:first-child > div:first-child",
            ".avatar-wrap",
            ".card-inner.common-wrap",
            ".card-inner",
            ".candidate-card-wrap",
            ".col-2",
            ".row.name-wrap",
            ".name",
        )
        try:
            return bool(
                card_scope.evaluate(
                    """
                    (root, {selectors}) => {
                      const candidates = [];
                      for (const selector of selectors) {
                        if (typeof root.matches === 'function' && root.matches(selector)) {
                          candidates.push(root);
                        }
                        candidates.push(...root.querySelectorAll(selector));
                      }
                      const ordered = [...new Set(candidates.filter(Boolean))];
                      const trigger = (target) => {
                        if (!(target instanceof HTMLElement)) return false;
                        target.scrollIntoView({block: 'center', inline: 'center'});
                        const rect = target.getBoundingClientRect();
                        const clientX = rect.left + Math.max(12, Math.min(rect.width - 12, rect.width * 0.35));
                        const clientY = rect.top + Math.max(12, Math.min(rect.height - 12, rect.height * 0.35));
                        for (const type of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
                          target.dispatchEvent(
                            new MouseEvent(type, {
                              bubbles: true,
                              cancelable: true,
                              composed: true,
                              view: window,
                              clientX,
                              clientY,
                              button: 0,
                              buttons: 1,
                            }),
                          );
                        }
                        return true;
                      };
                      for (const target of ordered) {
                        if (trigger(target)) {
                          return true;
                        }
                      }
                      return trigger(root);
                    }
                    """,
                    {"selectors": list(selectors)},
                )
            )
        except Exception:
            return False

    def _recommend_list_looks_healthy(self, selectors: BossSelectors, *, timeout_ms: int = 1500) -> bool:
        try:
            ready = self.wait_for_recommend_list_ready(selectors, timeout_ms=timeout_ms)
            return bool(ready and int(ready.get("card_count") or 0) > 0)
        except Exception:
            return False

    def _refresh_recommend_card_scope(
        self,
        selectors: BossSelectors,
        card: dict[str, Any],
        current_card_scope: Any,
    ) -> Any:
        try:
            refreshed = self._resolve_recommend_card_scope(selectors, card)
        except Exception:
            refreshed = None
        return refreshed if refreshed is not None else current_card_scope

    def open_recommend_candidate(self, card: dict[str, Any], selectors: BossSelectors) -> str:
        previous_expected_card = self._recommend_expected_card
        self._recommend_expected_card = dict(card or {})
        opened = False
        latest_detail_state: dict[str, Any] | None = None
        initial_state = self._recommend_detail_state(selectors)
        if initial_state.get("ready_visible") or initial_state.get("has_resume_frame") or initial_state.get("has_resume_iframe"):
            try:
                self.close_recommend_detail(selectors)
            except Exception:
                pass
            self._dismiss_blocking_dialogs()
        card_scope = self._resolve_recommend_card_scope(selectors, card)
        if card_scope is None and self.recover_recommend_list(selectors, timeout_ms=5000):
            self._dismiss_blocking_dialogs()
            card_scope = self._resolve_recommend_card_scope(selectors, card)
        if card_scope is None:
            try:
                self.wait_for_recommend_list_ready(selectors, timeout_ms=5000)
            except Exception:
                pass
            self._dismiss_blocking_dialogs()
            card_scope = self._resolve_recommend_card_scope(selectors, card)
        if card_scope is None:
            raise BrowserRuntimeError("Recommend candidate card is no longer available on the list page.")
        link_locator = self._locator_for_any(selectors.recommend_candidate_name_link, scope=card_scope)
        if link_locator is None:
            link_locator = self._locator_for_any(selectors.candidate_link, scope=card_scope)

        before_state = self._recommend_detail_state(selectors)

        def detail_opened(timeout_ms: int) -> str:
            nonlocal latest_detail_state
            page = self._require_page()
            deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
            saw_resume_frame = False
            saw_structural_open = False
            while time.monotonic() <= deadline:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                wait_slice = min(400, max(50, remaining_ms))
                ready_hit = self._wait_for_any_global(selectors.recommend_detail_ready, timeout_ms=wait_slice)
                current_state = self._recommend_detail_state(selectors)
                latest_detail_state = current_state
                if current_state["has_resume_frame"] and not before_state["has_resume_frame"]:
                    saw_resume_frame = True
                    if current_state.get("has_dialog") or ready_hit:
                        return "opened"
                if ready_hit and not before_state["ready_visible"]:
                    saw_structural_open = True
                if current_state["has_dialog"] and not before_state["has_dialog"]:
                    saw_structural_open = True
                if current_state["has_panel"] and not before_state["has_panel"]:
                    saw_structural_open = True
                if current_state.get("has_resume_iframe") and not before_state.get("has_resume_iframe"):
                    saw_structural_open = True
                if current_state.get("has_resume_iframe") and not before_state.get("has_resume_iframe"):
                    return "opened"
                if current_state.get("content_ready") and current_state["has_resume_frame"] and not before_state["has_resume_frame"]:
                    return "opened"
                if current_state.get("content_ready") and current_state["has_panel"] and not before_state["has_panel"]:
                    return "opened"
                if current_state.get("content_ready") and current_state["signature"] and current_state["signature"] != before_state["signature"]:
                    return "opened"
                if current_state.get("content_ready") and ready_hit and not before_state["ready_visible"]:
                    return "opened"
                if remaining_ms <= 0:
                    break
                try:
                    page.wait_for_timeout(min(200, max(50, remaining_ms)))
                except Exception:
                    break
            if saw_resume_frame:
                return "resume_frame_pending"
            if saw_structural_open:
                return "dialog_pending"
            return "none"

        def wait_for_pending_open(result: str, *, extra_timeout_ms: int = 6000) -> bool:
            if result == "opened":
                return True
            if result in {"resume_frame_pending", "dialog_pending"}:
                self._require_page().wait_for_timeout(1200)
                return detail_opened(timeout_ms=extra_timeout_ms) == "opened"
            return False

        def attempt_resume_open(current_card_scope: Any) -> tuple[bool, Any]:
            scope = current_card_scope
            for attempt in range(2):
                if self._click_recommend_resume_hotspot(scope):
                    self._require_page().wait_for_timeout(900)
                    result = detail_opened(timeout_ms=3500)
                    if wait_for_pending_open(result, extra_timeout_ms=5000):
                        return True, scope
                if attempt == 0:
                    scope = self._refresh_recommend_card_scope(selectors, card, scope)
            return False, scope

        def attempt_card_click(current_card_scope: Any) -> tuple[bool, Any]:
            scope = current_card_scope
            for attempt in range(2):
                card_clicked = self._click_locator(scope, timeout_ms=5000)
                if not card_clicked and scope is not None:
                    card_clicked = self._click_locator(scope, timeout_ms=5000, position={"x": 160, "y": 40})
                if card_clicked:
                    return True, scope
                if attempt == 0:
                    scope = self._refresh_recommend_card_scope(selectors, card, scope)
            return False, scope

        def attempt_dom_dispatch(current_card_scope: Any) -> tuple[bool, Any]:
            scope = current_card_scope
            for attempt in range(2):
                if self._dispatch_recommend_card_click(scope):
                    return True, scope
                if attempt == 0:
                    scope = self._refresh_recommend_card_scope(selectors, card, scope)
            return False, scope

        link_clicked = False
        if self._is_probable_anchor_locator(link_locator):
            link_clicked = False
            try:
                self._dismiss_blocking_dialogs()
                link_locator.first.click(timeout=5000)
                link_clicked = True
            except Exception:
                self._dismiss_blocking_dialogs()
                try:
                    link_locator.first.click(timeout=5000, force=True)
                    link_clicked = True
                except Exception:
                    link_locator = None

        def detail_matches_expected() -> bool:
            nonlocal latest_detail_state
            try:
                latest_detail_state = self._recommend_detail_state(selectors)
            except Exception:
                pass
            if not self._recommend_detail_is_open(selectors, detail_state=latest_detail_state):
                return False
            if self._recommend_detail_matches_card(selectors, card, detail_state=latest_detail_state):
                return True
            try:
                self.close_recommend_detail(selectors)
            except Exception:
                pass
            self._dismiss_blocking_dialogs()
            return False

        try:
            if link_locator is not None and link_clicked:
                self._require_page().wait_for_timeout(900)
                link_result = detail_opened(timeout_ms=2500)
                if wait_for_pending_open(link_result, extra_timeout_ms=6000):
                    if detail_matches_expected():
                        opened = True
                        return self._require_page().url
                else:
                    raise BrowserRuntimeError("Recommend candidate detail did not open from the current resume link.")

            resume_opened, card_scope = attempt_resume_open(card_scope)
            if resume_opened and detail_matches_expected():
                opened = True
                return self._require_page().url
            if resume_opened:
                refreshed_card_scope = self._resolve_recommend_card_scope(selectors, card)
                if refreshed_card_scope is not None:
                    card_scope = refreshed_card_scope
                    reopened, card_scope = attempt_resume_open(card_scope)
                    if reopened and detail_matches_expected():
                        opened = True
                        return self._require_page().url

            card_clicked, card_scope = attempt_card_click(card_scope)
            if card_clicked:
                self._require_page().wait_for_timeout(1200)
                if wait_for_pending_open(detail_opened(timeout_ms=15000), extra_timeout_ms=8000) and detail_matches_expected():
                    opened = True
                    return self._require_page().url
            dispatched, card_scope = attempt_dom_dispatch(card_scope)
            if dispatched:
                self._require_page().wait_for_timeout(1200)
                if wait_for_pending_open(detail_opened(timeout_ms=12000), extra_timeout_ms=8000) and detail_matches_expected():
                    opened = True
                    return self._require_page().url
            if not self._recommend_list_looks_healthy(selectors, timeout_ms=2000) and self.recover_recommend_list(
                selectors,
                timeout_ms=5000,
            ):
                self._dismiss_blocking_dialogs()
                card_scope = self._resolve_recommend_card_scope(selectors, card)
                if card_scope is not None:
                    reopened, card_scope = attempt_resume_open(card_scope)
                    if reopened and detail_matches_expected():
                        opened = True
                        return self._require_page().url
                    card_clicked, card_scope = attempt_card_click(card_scope)
                    if card_clicked:
                        self._require_page().wait_for_timeout(1200)
                        if wait_for_pending_open(detail_opened(timeout_ms=12000), extra_timeout_ms=8000) and detail_matches_expected():
                            opened = True
                            return self._require_page().url
                    dispatched, card_scope = attempt_dom_dispatch(card_scope)
                    if dispatched:
                        self._require_page().wait_for_timeout(1200)
                        if wait_for_pending_open(detail_opened(timeout_ms=12000), extra_timeout_ms=8000) and detail_matches_expected():
                            opened = True
                            return self._require_page().url
            raise BrowserRuntimeError("Recommend candidate detail did not open from the current list card.")
        finally:
            if not opened:
                self._recommend_expected_card = previous_expected_card

    def download_resume(self, selectors: BossSelectors, external_id: str | None = None, *, timeout_ms: int = 12000) -> dict[str, Any]:
        page = self._require_page()
        active_dialog = self._active_recommend_dialog_locator()
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
        scopes: list[Any] = []
        active_dialog = self._active_recommend_dialog_locator()
        if active_dialog is not None:
            try:
                scopes.append(active_dialog.first)
            except Exception:
                pass
        expected_card = self._recommend_expected_card if isinstance(self._recommend_expected_card, dict) else None
        if expected_card:
            try:
                card_scope = self._resolve_recommend_card_scope(selectors, expected_card)
            except Exception:
                card_scope = None
            if card_scope is not None:
                scopes.append(card_scope)
        try:
            panel_target = self._find_resume_dialog_panel_target()
        except Exception:
            panel_target = None
        if panel_target is not None:
            try:
                _root, panel_locator, _metrics = panel_target
                scopes.append(panel_locator)
            except Exception:
                pass

        locator = None
        seen_scope_ids: set[int] = set()
        for scope in scopes:
            if scope is None:
                continue
            scope_id = id(scope)
            if scope_id in seen_scope_ids:
                continue
            seen_scope_ids.add(scope_id)
            try:
                locator = self._locator_for_any(selectors.recommend_greet_button, scope=scope)
            except Exception:
                locator = None
            if locator is not None:
                break
        if locator is None:
            locator = self._locator_for_any_global(selectors.recommend_greet_button)
        if locator is None:
            if self._click_recommend_greet_by_text(selectors, scopes=scopes):
                return {"clicked": True}
            if self._click_recommend_greet_by_position(selectors):
                return {"clicked": True}
            return {"clicked": False, "reason": "greet_button_not_found"}
        try:
            locator.first.click(timeout=5000, force=True)
            self._require_page().wait_for_timeout(500)
            return {"clicked": True}
        except Exception as exc:
            if self._click_recommend_greet_by_text(selectors, scopes=scopes):
                return {"clicked": True}
            if self._click_recommend_greet_by_position(selectors):
                return {"clicked": True}
            return {"clicked": False, "reason": str(exc)}

    @staticmethod
    def _recommend_greet_text_labels() -> tuple[str, ...]:
        return ("打招呼", "立即沟通", "立即开聊", "继续沟通")

    @staticmethod
    def _locator_for_visible_text(root: Any, label: str, *, exact: bool) -> Any | None:
        getter = getattr(root, "get_by_text", None)
        if not callable(getter):
            return None
        try:
            locator = getter(label, exact=exact)
        except TypeError:
            locator = getter(label)
        except Exception:
            return None
        try:
            return locator if locator.count() > 0 else None
        except Exception:
            return None

    def _click_recommend_greet_by_text(
        self,
        selectors: BossSelectors,
        *,
        scopes: Sequence[Any],
    ) -> bool:
        try:
            detail_state = self._recommend_detail_state(selectors)
        except Exception:
            detail_state = None
        if not self._recommend_detail_is_open(selectors, detail_state=detail_state):
            return False

        page = self._require_page()
        roots: list[Any] = [scope for scope in scopes if scope is not None]
        for frame in self._page_frames(page):
            frame_url = self._frame_url_value(frame).lower()
            if (
                "/web/frame/c-resume/" in frame_url
                or "/web/geek/job-recommend/" in frame_url
                or "/web/frame/recommend/" in frame_url
            ):
                roots.append(frame)
        roots.append(page)

        seen_root_ids: set[int] = set()
        for root in roots:
            root_id = id(root)
            if root_id in seen_root_ids:
                continue
            seen_root_ids.add(root_id)
            for exact in (True, False):
                for label in self._recommend_greet_text_labels():
                    locator = self._locator_for_visible_text(root, label, exact=exact)
                    if locator is None:
                        continue
                    try:
                        target = locator.first
                    except Exception:
                        target = locator
                    if self._click_locator(target, timeout_ms=5000):
                        page.wait_for_timeout(500)
                        return True
        return False

    def _click_recommend_greet_by_position(self, selectors: BossSelectors) -> bool:
        try:
            detail_state = self._recommend_detail_state(selectors)
        except Exception:
            detail_state = None
        if not self._recommend_detail_is_open(selectors, detail_state=detail_state):
            return False

        page = self._require_page()
        click_points: list[tuple[float, float]] = []

        active_dialog = self._active_recommend_dialog_locator()
        if active_dialog is not None:
            try:
                dialog_box = active_dialog.first.bounding_box()
            except Exception:
                dialog_box = None
            if dialog_box:
                click_points.append(
                    (
                        float(dialog_box["x"]) + float(dialog_box["width"]) * 0.84,
                        float(dialog_box["y"]) + min(220.0, float(dialog_box["height"]) * 0.18),
                    )
                )

        if not click_points:
            try:
                panel_target = self._find_resume_dialog_panel_target()
            except Exception:
                panel_target = None
            if panel_target is not None:
                _root, _panel_locator, metrics = panel_target
                click_points.append(
                    (
                        min(float(self.width) * 0.9, float(metrics.get("right") or 0.0) + 320.0),
                        max(120.0, float(metrics.get("top") or 0.0) + 100.0),
                    )
                )

        if not click_points:
            click_points.append((float(self.width) * 0.83, float(self.height) * 0.18))

        for x, y in click_points:
            try:
                page.mouse.click(x, y)
                page.wait_for_timeout(500)
                return True
            except Exception:
                continue
        return False

    def close_recommend_detail(self, selectors: BossSelectors) -> bool:
        page = self._require_page()
        for _ in range(3):
            locator = self._locator_for_any_global(selectors.recommend_close_button)
            if locator is not None:
                try:
                    locator.first.click(timeout=1500, force=True)
                    page.wait_for_timeout(300)
                    self._recommend_expected_card = None
                    return True
                except Exception:
                    pass
            if not self._has_active_recommend_dialog() and not self._has_inline_recommend_detail(selectors):
                self._recommend_expected_card = None
                return True
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
            except Exception:
                return False
            if not self._has_active_recommend_dialog() and not self._has_inline_recommend_detail(selectors):
                self._recommend_expected_card = None
                return True
        if self._has_inline_recommend_detail(selectors):
            # Avoid hard-refreshing the whole recommend page when the detail
            # panel looks stuck. Let the caller decide how to recover so we do
            # not disrupt the HR's current tab state with an unexpected reload.
            return False
        cleared = not self._has_active_recommend_dialog()
        if cleared:
            self._recommend_expected_card = None
        return cleared

    def extract_recommend_detail_payload(self, selectors: BossSelectors) -> dict[str, Any]:
        iframe_payload = self._extract_recommend_resume_iframe_payload()
        iframe_text = self._cleanup_resume_text(iframe_payload.get("page_text")) if iframe_payload else ""
        if iframe_text and not self._is_loading_resume_text(iframe_text):
            preferred = dict(iframe_payload)
            preferred["page_text"] = iframe_text
            preferred.pop("_canvas_only", None)
            if not preferred.get("detail_url"):
                preferred["detail_url"] = self.current_url
            return preferred

        detail = self.extract_detail_payload(selectors)
        detail_text = self._cleanup_resume_text(detail.get("page_text"))
        detail_markup_is_overview = self._is_recommend_overview_markup(
            detail.get("content_selector"),
            detail.get("content_html"),
        )
        if detail_text and not self._is_loading_resume_text(detail_text) and not self._looks_like_recommend_overview_text(
            detail_text
        ):
            normalized = dict(detail)
            normalized["page_text"] = detail_text
            if iframe_payload is not None and detail_markup_is_overview:
                normalized["content_html"] = iframe_payload.get("content_html")
                normalized["page_html"] = iframe_payload.get("page_html")
                normalized["content_selector"] = iframe_payload.get("content_selector")
            if not normalized.get("detail_url"):
                normalized["detail_url"] = self.current_url
            return normalized

        if iframe_payload is not None:
            fallback = dict(iframe_payload)
            fallback["page_text"] = iframe_text or ""
            fallback.pop("_canvas_only", None)
            if not fallback.get("detail_url"):
                fallback["detail_url"] = self.current_url
            return fallback

        active_dialog = self._active_recommend_dialog_locator()
        if active_dialog is not None:
            try:
                text = self._cleanup_resume_text(active_dialog.first.inner_text())
                if text and not self._is_loading_resume_text(text):
                    fallback = dict(detail)
                    fallback["detail_url"] = fallback.get("detail_url") or self.current_url
                    fallback["page_text"] = text
                    return fallback
            except Exception:
                pass
        return detail

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

    def go_to_next_recommend_page(self, selectors: BossSelectors) -> bool:
        scope = self._resolve_recommend_scope(selectors)
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
            self._wait_for_any(
                selectors.recommend_list_ready + selectors.list_ready,
                timeout_ms=15000,
                scope=scope,
            )
            return True
        except Exception:
            return False

    def wait_for_recommend_list_ready(self, selectors: BossSelectors, *, timeout_ms: int = 10000) -> dict[str, Any] | None:
        ready = self._wait_for_recommend_cards_ready(selectors, timeout_ms=timeout_ms)
        if ready is not None:
            return ready
        if self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=True):
            return self._wait_for_recommend_cards_ready(selectors, timeout_ms=max(1000, timeout_ms // 2))
        return None

    def recover_recommend_list(self, selectors: BossSelectors, *, timeout_ms: int = 5000) -> bool:
        try:
            page = self._require_page()
            if not page.is_closed():
                if self.wait_for_recommend_list_ready(selectors, timeout_ms=timeout_ms):
                    return True
        except Exception:
            pass
        if self._reuse_existing_recommend_page(selectors, min_cards=1, close_previous_owned=False):
            return bool(self.wait_for_recommend_list_ready(selectors, timeout_ms=timeout_ms))
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

    def _is_loopback_cdp_port(self, expected_port: int) -> bool:
        normalized = self._normalize_cdp_url(self.cdp_url)
        if not normalized:
            return False
        parsed = urlparse(normalized)
        return parsed.hostname in {"127.0.0.1", "::1", "localhost"} and parsed.port == expected_port

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

    @staticmethod
    def _page_url_value(page: Any) -> str:
        try:
            url = page.url
            return str(url() if callable(url) else url or "")
        except Exception:
            return ""

    @staticmethod
    def _frame_name_value(frame: Any) -> str:
        try:
            name = frame.name
            return str(name() if callable(name) else name or "")
        except Exception:
            return ""

    @staticmethod
    def _frame_url_value(frame: Any) -> str:
        try:
            url = frame.url
            return str(url() if callable(url) else url or "")
        except Exception:
            return ""

    @staticmethod
    def _page_frames(page: Any) -> list[Any]:
        try:
            frames = page.frames
            if callable(frames):
                frames = frames()
            return list(frames or [])
        except Exception:
            return []

    @staticmethod
    def _is_recommend_page_url(url: str | None) -> bool:
        return "/web/chat/recommend" in str(url or "").lower()

    def _adopt_page(self, page: Any, *, owns_page: bool = False, close_previous_owned: bool = False) -> None:
        previous_page = self._page
        previous_owned = self._owns_page
        self._page = page
        self._owns_page = owns_page
        try:
            page.bring_to_front()
        except Exception:
            pass
        if close_previous_owned and previous_owned and previous_page is not None and previous_page is not page:
            try:
                previous_page.close()
            except Exception:
                pass

    def _recommend_scope_info(self, scope: Any) -> dict[str, Any]:
        frame_name = self._frame_name_value(scope)
        frame_url = self._frame_url_value(scope)
        if not frame_url:
            frame_url = self._page_url_value(scope)
        info: dict[str, Any] = {}
        if frame_name:
            info["frame_name"] = frame_name
        if frame_url:
            info["frame_url"] = frame_url
        return info

    @staticmethod
    def _recommend_scope_has_valid_jobid(scope_info: dict[str, Any]) -> bool:
        frame_url = str(scope_info.get("frame_url") or "").strip()
        if not frame_url:
            return True
        parsed = urlparse(frame_url)
        if "/web/frame/recommend/" not in parsed.path:
            return True
        jobid_values = parse_qs(parsed.query).get("jobid", [])
        if not jobid_values:
            return False
        jobid = str(jobid_values[0] or "").strip().lower()
        return jobid not in {"", "null", "none", "undefined"}

    def _recommend_card_count_for_scope(self, selectors: BossSelectors, scope: Any) -> int:
        try:
            locator = self._locator_for_any(selectors.recommend_candidate_card, scope=scope)
            if locator is None:
                locator = self._locator_for_any(selectors.candidate_card, scope=scope)
            if locator is None:
                return 0
            return int(locator.count())
        except Exception:
            return 0

    def _wait_for_recommend_cards_ready(
        self,
        selectors: BossSelectors,
        *,
        timeout_ms: int = 10000,
    ) -> dict[str, Any] | None:
        page = self._require_page()
        deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
        while time.monotonic() <= deadline:
            remaining_ms = max(250, int((deadline - time.monotonic()) * 1000))
            scope = self._resolve_recommend_scope(
                selectors,
                timeout_ms=min(1000, max(250, remaining_ms)),
            )
            matched = self._wait_for_any(
                selectors.recommend_list_ready,
                timeout_ms=min(1000, max(250, remaining_ms)),
                scope=scope,
            )
            if matched is not None:
                scope_info = self._recommend_scope_info(scope)
                if not self._recommend_scope_has_valid_jobid(scope_info):
                    if remaining_ms <= 250:
                        break
                    try:
                        page.wait_for_timeout(min(250, remaining_ms))
                    except Exception:
                        break
                    continue
                card_count = self._recommend_card_count_for_scope(selectors, scope)
                if card_count > 0:
                    return {
                        "ready_selector": matched,
                        "card_count": card_count,
                        **scope_info,
                    }
            if remaining_ms <= 250:
                break
            try:
                page.wait_for_timeout(min(250, remaining_ms))
            except Exception:
                break
        return None

    def _recommend_card_count_on_page(
        self,
        page: Any,
        selectors: BossSelectors,
        *,
        timeout_ms: int = 2000,
    ) -> int:
        previous_page = self._page
        previous_owned = self._owns_page
        try:
            self._page = page
            self._owns_page = False
            scope = self._resolve_scope(
                selectors.recommend_frame_name,
                selectors.recommend_frame_url_contains,
                page=page,
                timeout_ms=timeout_ms,
            )
            return self._recommend_card_count_for_scope(selectors, scope)
        except Exception:
            return 0
        finally:
            self._page = previous_page
            self._owns_page = previous_owned

    def _find_existing_recommend_page(self, selectors: BossSelectors, *, min_cards: int = 1) -> Any | None:
        if self._context is None:
            return None
        pages = list(getattr(self._context, "pages", []) or [])
        if not pages:
            return None

        current_page = self._page
        ordered_pages = [page for page in reversed(pages) if page is not current_page]
        if current_page is not None:
            ordered_pages.append(current_page)

        fallback_page = None
        for page in ordered_pages:
            url = self._page_url_value(page)
            if self._is_blank_page_url(url) or not self._is_recommend_page_url(url):
                continue
            if min_cards <= 0:
                return page
            card_count = self._recommend_card_count_on_page(page, selectors, timeout_ms=1500)
            if card_count >= min_cards:
                return page
            if fallback_page is None:
                fallback_page = page
        return fallback_page if min_cards <= 0 else None

    def _reuse_existing_recommend_page(
        self,
        selectors: BossSelectors,
        *,
        min_cards: int = 1,
        close_previous_owned: bool = False,
    ) -> bool:
        page = self._find_existing_recommend_page(selectors, min_cards=min_cards)
        if page is None or page is self._page:
            return False
        self._adopt_page(page, owns_page=False, close_previous_owned=close_previous_owned)
        return True

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

    def _resolve_search_scope(self, selectors: BossSelectors, **kwargs):
        return self._resolve_scope(selectors.search_frame_name, selectors.search_frame_url_contains, **kwargs)

    def _resolve_recommend_scope(self, selectors: BossSelectors, **kwargs):
        return self._resolve_scope(selectors.recommend_frame_name, selectors.recommend_frame_url_contains, **kwargs)

    def _resolve_scope(
        self,
        frame_name: str | None,
        frame_url_contains: str | None,
        *,
        page=None,
        timeout_ms: int = 15000,
    ):
        root_page = page or self._require_page()
        attempts = max(1, timeout_ms // 250)
        for _ in range(attempts):
            for frame in self._page_frames(root_page):
                frame_name_value = self._frame_name_value(frame)
                frame_url_value = self._frame_url_value(frame)
                if frame_name and frame_name_value == frame_name:
                    return frame
                if frame_url_contains and frame_url_contains in frame_url_value:
                    return frame
            iframe_frame = self._resolve_iframe_scope(root_page, frame_name, frame_url_contains)
            if iframe_frame is not None:
                return iframe_frame
            try:
                root_page.wait_for_timeout(250)
            except Exception:
                break
        return root_page

    def _resolve_iframe_scope(self, page: Any, frame_name: str | None, frame_url_contains: str | None):
        iframe_selectors: list[str] = []
        if frame_name:
            iframe_selectors.append(f'iframe[name="{frame_name}"]')
        if frame_url_contains:
            iframe_selectors.append(f'iframe[src*="{frame_url_contains}"]')
        for selector in iframe_selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(min(count, 3)):
                try:
                    handle = locator.nth(index).element_handle(timeout=1000)
                    if handle is None:
                        continue
                    frame = handle.content_frame()
                    if frame is not None:
                        return frame
                except Exception:
                    continue
        return None

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
        roots = [page, *self._page_frames(page)]
        for root in roots:
            locator = self._locator_for_any(selectors, scope=root)
            if locator is not None:
                return locator
        return None

    @staticmethod
    def _recommend_dialog_selectors() -> tuple[str, ...]:
        return (
            "div.dialog-wrap.active",
            "div[data-type='boss-dialog'].active",
            "[role='dialog']",
        )

    def _active_recommend_dialog_locator(self):
        return self._locator_for_any_global(self._recommend_dialog_selectors())

    def _has_active_recommend_dialog(self) -> bool:
        locator = self._active_recommend_dialog_locator()
        if locator is None:
            return False
        try:
            return locator.count() > 0
        except Exception:
            return False

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
            if not isinstance(getattr(node, "tag", None), str):
                continue
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
        dynamic_target = self._sanitize_recommend_resume_target(self._find_dynamic_resume_target(roots))
        if dynamic_target is not None:
            return dynamic_target
        dialog_target = self._sanitize_recommend_resume_target(self._find_resume_dialog_panel_target())
        if dialog_target is not None:
            return dialog_target
        expected_name = self._recommend_expected_name_hint()
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
                    if expected_name and expected_name in preview_text:
                        score += 50000
                    if left > self.width * 0.65:
                        score -= 25000
                    if right > self.width * 0.82:
                        score -= 12000
                    if width < 420:
                        score -= 8000
                    if score > best_score:
                        best = (root, candidate, metrics)
                        best_score = score
        return self._sanitize_recommend_resume_target(best)

    def _find_resume_dialog_panel_target(self) -> tuple[object, object, dict[str, float]] | None:
        active_dialog = self._active_recommend_dialog_locator()
        if active_dialog is None:
            return None
        dialog = active_dialog.first
        marker = "[data-hrclaw-dialog-resume-panel='1']"
        expected_name = self._recommend_expected_name_hint()
        try:
            result = dialog.evaluate(
                """
                ({marker, positiveMarkers, negativeMarkers, expectedName}) => {
                  dialog.querySelectorAll(marker).forEach((el) => {
                    el.removeAttribute('data-hrclaw-dialog-resume-panel');
                  });
                  const dialogRect = dialog.getBoundingClientRect();
                  const dialogWidth = dialogRect.width || 0;
                  const dialogHeight = dialogRect.height || 0;
                  if (dialogWidth < 420 || dialogHeight < 180) {
                    return null;
                  }
                  const leftBoundary = dialogWidth * 0.04;
                  const rightBoundary = dialogWidth * 0.58;
                  let best = null;
                  let bestScore = -Infinity;
                  for (const el of dialog.querySelectorAll('*')) {
                    if (!(el instanceof HTMLElement)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 320 || rect.height < 120) continue;
                    const localLeft = rect.left - dialogRect.left;
                    const localRight = rect.right - dialogRect.left;
                    const centerX = localLeft + rect.width / 2;
                    if (localLeft < leftBoundary - 40) continue;
                    if (centerX > rightBoundary) continue;
                    if (localRight > dialogWidth * 0.7) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') === 0) continue;
                    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (text.length < 80) continue;
                    let score = text.length + rect.width * 1.8 + rect.height;
                    if (el.scrollHeight > el.clientHeight + 40) score += 22000;
                    if (rect.width > dialogWidth * 0.62) score -= 18000;
                    if (localLeft >= leftBoundary && localLeft <= dialogWidth * 0.32) score += 7000;
                    if (centerX <= dialogWidth * 0.36) score += 6000;
                    const classId = `${el.className || ''} ${el.id || ''}`.toLowerCase();
                    if (classId.includes('iboss-left')) score += 22000;
                    if (classId.includes('resume-content') || classId.includes('geek-resume-wrap')) score += 9000;
                    if (classId.includes('resume-detail-wrap')) score -= 9000;
                    if (classId.includes('card-inner') || classId.includes('card-content')) score -= 16000;
                    if (text.includes('经历概览')) score -= 45000;
                    if (text.includes('继续沟通') || text.includes('打招呼')) score -= 14000;
                    if (expectedName && text.includes(expectedName)) score += 50000;
                    for (const markerText of positiveMarkers) {
                      if (text.includes(markerText)) score += 2500;
                    }
                    for (const markerText of negativeMarkers) {
                      if (text.includes(markerText)) score -= 22000;
                    }
                    if (/\\b\\d{2}岁\\b/.test(text)) score += 4500;
                    if (/(本科|硕士|博士|大专)/.test(text)) score += 3000;
                    if (/(工作经历|项目经历|最近关注|期望职位)/.test(text)) score += 3500;
                    if (score > bestScore) {
                      best = el;
                      bestScore = score;
                    }
                  }
                  if (!best) return null;
                  best.setAttribute('data-hrclaw-dialog-resume-panel', '1');
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
                    "marker": marker,
                    "positiveMarkers": list(_RESUME_POSITIVE_MARKERS),
                    "negativeMarkers": list(_RESUME_NEGATIVE_MARKERS),
                    "expectedName": expected_name,
                },
            )
        except Exception:
            return None
        if not result:
            return None
        try:
            locator = dialog.locator(marker)
            if locator.count() == 0:
                return None
            return (self._require_page(), locator.first, result)
        except Exception:
            return None

    def _find_dynamic_resume_target(self, roots) -> tuple[object, object, dict[str, float]] | None:
        marker = "[data-hrclaw-resume-target='1']"
        expected_name = self._recommend_expected_name_hint()
        for root in roots:
            try:
                result = root.evaluate(
                    """
                    ({positiveMarkers, negativeMarkers, expectedName}) => {
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
                        if (expectedName && text.includes(expectedName)) score += 50000;
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
                        "expectedName": expected_name,
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
