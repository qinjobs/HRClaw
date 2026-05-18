from __future__ import annotations

import json

from src.screening.browser_runtime import PlaywrightBrowserRuntime
from src.screening.config import load_local_env


def main() -> None:
    load_local_env()
    runtime = PlaywrightBrowserRuntime(
        headless=False,
        start_url="https://www.zhipin.com/web/chat/search",
    )
    try:
        if not runtime.has_storage_state():
            raise SystemExit(f"Storage state not found: {runtime.storage_state_path}")
        runtime.start()
        page = runtime._require_page()
        page.wait_for_timeout(5000)
        screenshot_path = None
        screenshot_error = None
        try:
            screenshot_path = runtime.persist_screenshot("auth_state_check")
        except Exception as exc:
            screenshot_error = str(exc)
        result = {
            "storage_state_path": str(runtime.storage_state_path),
            "current_url": runtime.current_url,
            "title": page.title(),
            "body_snippet": "",
            "logged_in": False,
            "reason": "",
            "screenshot_path": screenshot_path,
            "screenshot_error": screenshot_error,
        }
        try:
            result["body_snippet"] = page.locator("body").inner_text()[:800]
        except Exception:
            pass
        if "/web/user" in result["current_url"]:
            result["reason"] = "on_login_page"
        elif "当前登录状态已失效" in result["body_snippet"]:
            result["reason"] = "session_invalid"
        elif "推荐牛人" in result["body_snippet"] or "/web/chat/" in result["current_url"]:
            result["logged_in"] = True
            result["reason"] = "recruiter_ui_detected"
        else:
            result["reason"] = "recruiter_ui_not_detected"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
