from __future__ import annotations

import argparse
import json
import threading
from dataclasses import asdict
from typing import Any

from ..config import load_local_env
from ..search_service import ResumeSearchService
from .service import EmailResumeIngestService


class EmailResumeIngestScheduler:
    def __init__(self, *, service: EmailResumeIngestService | None = None) -> None:
        self.service = service or EmailResumeIngestService(search_service=ResumeSearchService())
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

    def run_once(self) -> dict[str, Any]:
        return self.service.run_due_users()

    def run_loop(self, *, poll_seconds: int = 60) -> dict[str, Any]:
        return self.service.run_scheduler_loop(poll_seconds=poll_seconds, once=False)

    def start_in_background(self, *, poll_seconds: int = 60) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event = threading.Event()
        interval = max(5, int(poll_seconds))

        def _runner() -> None:
            while self._stop_event and not self._stop_event.is_set():
                self.service.run_due_users()
                self._stop_event.wait(interval)

        self._thread = threading.Thread(target=_runner, name="email-resume-ingest-scheduler", daemon=True)
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(0.0, float(timeout_seconds)))
        self._thread = None
        self._stop_event = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run email resume ingest scheduler.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_once_parser = sub.add_parser("run-once", help="Run due users once")
    run_once_parser.add_argument("--user-id", default="", help="Optional user_id for manual one-shot")
    run_once_parser.add_argument("--max-files", type=int, default=0, help="Max files for manual run-once mode")

    run_due_parser = sub.add_parser("run-due", help="Run due users (once or loop)")
    run_due_parser.add_argument("--loop", action="store_true", help="Keep running forever")
    run_due_parser.add_argument("--poll-seconds", type=int, default=60, help="Scheduler polling interval")

    retry_parser = sub.add_parser("retry-failed", help="Retry failed ingest records")
    retry_parser.add_argument("--user-id", default="", help="Optional user_id")
    retry_parser.add_argument("--max-retry", type=int, default=3, help="Max retry threshold")
    retry_parser.add_argument("--limit", type=int, default=50, help="Max records per execution")

    return parser


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    search_service = ResumeSearchService()
    scheduler = EmailResumeIngestScheduler(service=EmailResumeIngestService(search_service=search_service))
    try:
        if args.command == "run-once":
            user_id = str(args.user_id or "").strip()
            if user_id:
                summary = scheduler.service.run_once(
                    user_id=user_id,
                    trigger="manual_cli",
                    max_files=int(args.max_files or 0) or None,
                )
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0
            summary = scheduler.run_once()
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "run-due":
            if args.loop:
                scheduler.run_loop(poll_seconds=max(5, int(args.poll_seconds or 60)))
                return 0
            summary = scheduler.run_once()
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        if args.command == "retry-failed":
            summary = scheduler.service.retry_failed(
                user_id=str(args.user_id or "").strip() or None,
                max_retry=max(1, int(args.max_retry or 3)),
                limit=max(1, int(args.limit or 50)),
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        parser.error("unknown command")
        return 2
    finally:
        scheduler.stop()
        if hasattr(search_service, "close"):
            search_service.close()


if __name__ == "__main__":
    raise SystemExit(main())
