#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.screening.config import load_local_env
from src.screening.db import init_db
from src.screening.hr_users import list_hr_users, update_hr_user
from src.screening.jd_scorecard_repositories import get_jd_scorecard


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate DB for email resume ingest and optional user defaults.")
    parser.add_argument(
        "--default-scorecard-id",
        default="",
        help="Bind this scorecard as default for matched HR users.",
    )
    parser.add_argument(
        "--apply-to-missing-only",
        action="store_true",
        help="Only apply when user's default scorecard is empty.",
    )
    parser.add_argument(
        "--enable-email-ingest",
        action="store_true",
        help="Enable email ingest for matched HR users.",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Email ingest interval when --enable-email-ingest is set.",
    )
    parser.add_argument(
        "--source",
        default="boss_email",
        help="Email ingest source (boss_email|email_import).",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        default=[],
        help="Apply only to specific user ids, can be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only.")
    return parser


def _pick_targets(users: list[dict[str, Any]], user_ids: list[str]) -> list[dict[str, Any]]:
    normalized = {str(item).strip() for item in (user_ids or []) if str(item).strip()}
    if not normalized:
        return users
    return [item for item in users if str(item.get("id") or "") in normalized]


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    args = _build_parser().parse_args(argv)
    init_db()

    scorecard_id = str(args.default_scorecard_id or "").strip()
    if scorecard_id and not get_jd_scorecard(scorecard_id):
        raise SystemExit(f"default scorecard not found: {scorecard_id}")

    users = [item for item in list_hr_users() if str(item.get("role") or "hr") == "hr"]
    targets = _pick_targets(users, args.user_id)
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for user in targets:
        user_id = str(user.get("id") or "")
        current_scorecard = str(user.get("default_scorecard_id") or "").strip()
        if args.apply_to_missing_only and current_scorecard:
            skipped.append({"user_id": user_id, "reason": "has_default_scorecard"})
            continue

        payload: dict[str, Any] = {}
        if scorecard_id:
            payload["default_scorecard_id"] = scorecard_id
        if args.enable_email_ingest:
            payload["email_ingest_enabled"] = True
            payload["email_ingest_interval_minutes"] = max(5, int(args.interval_minutes or 60))
            payload["email_ingest_source"] = str(args.source or "boss_email")

        if not payload:
            skipped.append({"user_id": user_id, "reason": "no_update_payload"})
            continue

        if args.dry_run:
            updated.append({"user_id": user_id, "dry_run": True, **payload})
            continue

        result = update_hr_user(
            user_id=user_id,
            default_scorecard_id=payload.get("default_scorecard_id"),
            email_ingest_enabled=payload.get("email_ingest_enabled"),
            email_ingest_interval_minutes=payload.get("email_ingest_interval_minutes"),
            email_ingest_source=payload.get("email_ingest_source"),
            operator="migration.email_resume_ingest",
        )
        updated.append(
            {
                "user_id": user_id,
                "default_scorecard_id": result.get("default_scorecard_id"),
                "email_ingest_enabled": bool(result.get("email_ingest_enabled")),
                "email_ingest_interval_minutes": int(result.get("email_ingest_interval_minutes") or 60),
                "email_ingest_source": result.get("email_ingest_source"),
            }
        )

    print(
        json.dumps(
            {
                "ok": True,
                "total_hr_users": len(users),
                "target_users": len(targets),
                "updated": updated,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
