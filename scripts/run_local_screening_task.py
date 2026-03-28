from __future__ import annotations

import argparse
import json

from src.screening.config import load_local_env
from src.screening.db import init_db
from src.screening.orchestrator import ScreeningOrchestrator
from src.screening.repositories import create_task, get_task, list_candidates_for_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Playwright screening task without starting the HTTP server.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--search-mode", default="recommend")
    parser.add_argument("--sort-by", default="active")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--keyword", default="")
    parser.add_argument("--city", default="")
    return parser.parse_args()


def main() -> None:
    load_local_env()
    init_db()
    args = parse_args()
    task_id = create_task(
        {
            "job_id": args.job_id,
            "search_mode": args.search_mode,
            "sort_by": args.sort_by,
            "max_candidates": args.max_candidates,
            "max_pages": args.max_pages,
            "search_config": {"keyword": args.keyword, "city": args.city},
            "require_hr_confirmation": True,
        }
    )
    orchestrator = ScreeningOrchestrator()
    result = orchestrator.run_task(task_id)
    print(json.dumps({"task": get_task(task_id), "result": result, "candidates": list_candidates_for_task(task_id)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
