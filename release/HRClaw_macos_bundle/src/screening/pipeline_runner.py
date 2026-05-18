from __future__ import annotations

import argparse
import json

from .config import load_local_env
from .pipeline_service import CollectionPipelineService
from .search_service import ResumeSearchService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run scheduled BOSS collection pipelines.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List configured collection pipelines")

    create_parser = sub.add_parser("upsert", help="Create or update a collection pipeline from JSON")
    create_parser.add_argument("--json", required=True, help="Pipeline JSON payload")

    run_parser = sub.add_parser("run", help="Run one pipeline immediately")
    run_parser.add_argument("--pipeline-id", required=True, help="Collection pipeline id")

    due_parser = sub.add_parser("run-due", help="Run all due pipelines once")
    due_parser.add_argument("--poll-seconds", type=int, default=60, help="Scheduler poll interval")
    due_parser.add_argument("--loop", action="store_true", help="Keep polling instead of running once")

    return parser


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    service = CollectionPipelineService(search_service=ResumeSearchService())
    try:
        if args.command == "list":
            print(json.dumps(service.list_pipelines(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "upsert":
            payload = json.loads(args.json)
            print(json.dumps(service.upsert_pipeline(payload), ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            print(json.dumps(service.run_pipeline(args.pipeline_id, force=True), ensure_ascii=False, indent=2))
            return 0
        if args.command == "run-due":
            summary = service.run_scheduler_loop(poll_seconds=args.poll_seconds, once=not args.loop)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        parser.error("unknown command")
        return 2
    finally:
        if hasattr(service.search_service, "close"):
            service.search_service.close()


if __name__ == "__main__":
    raise SystemExit(main())
