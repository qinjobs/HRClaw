from __future__ import annotations

import json

from src.screening.boss_auth import save_boss_storage_state
from src.screening.config import load_local_env


def main() -> None:
    load_local_env()
    summary = save_boss_storage_state(headless=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary.get("login_detected"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
