from __future__ import annotations

import json
from pathlib import Path

from src.screening.boss_selectors import load_boss_selectors
from src.screening.browser_runtime import PlaywrightBrowserRuntime
from src.screening.config import load_local_env, project_root


def count_selector(page, selector: str) -> int:
    try:
        return page.locator(selector).count()
    except Exception:
        return 0


def main() -> None:
    load_local_env()
    selectors = load_boss_selectors()
    runtime = PlaywrightBrowserRuntime(headless=False, start_url=selectors.search_url)
    session_id = runtime.start()
    try:
        print(f"Browser session started: {session_id}")
        input("Log into BOSS and navigate to the target list page, then press Enter here...")
        page = runtime._require_page()
        report = {
            "current_url": runtime.current_url,
            "selector_counts": {
                "list_ready": {selector: count_selector(page, selector) for selector in selectors.list_ready},
                "candidate_card": {selector: count_selector(page, selector) for selector in selectors.candidate_card},
                "candidate_name": {selector: count_selector(page, selector) for selector in selectors.candidate_name},
                "candidate_link": {selector: count_selector(page, selector) for selector in selectors.candidate_link},
                "next_page": {selector: count_selector(page, selector) for selector in selectors.next_page},
            },
        }
        screenshot_path = runtime.persist_screenshot("probe_page")
        report["screenshot_path"] = screenshot_path
        output_path = project_root() / "data" / "boss_probe_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Saved report to {output_path}")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
