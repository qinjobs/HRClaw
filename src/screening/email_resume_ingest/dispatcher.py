from __future__ import annotations

import uuid
from typing import Any

from ..db import connect, dumps
from ..repositories import (
    add_candidate_timeline_event,
    insert_candidate_action,
    upsert_candidate_pipeline_state,
)


class EmailResumeDispatcher:
    def dispatch(
        self,
        *,
        ingest_record_id: str,
        candidate_id: str,
        user: dict[str, Any],
        decision: str,
        score: float,
        source: str,
    ) -> dict[str, Any]:
        normalized_decision = str(decision or "reject").strip().lower() or "reject"
        user_id = str(user.get("id") or "")
        owner = str(user.get("username") or user.get("display_name") or "").strip() or None
        push_record_id: str | None = None

        if normalized_decision == "recommend":
            state = upsert_candidate_pipeline_state(
                candidate_id,
                owner=owner,
                current_stage="to_contact",
                final_decision="recommend",
                manual_stage_locked=False,
            )
            push_record_id = self._create_push_record(
                ingest_record_id=ingest_record_id,
                user_id=user_id,
                candidate_id=candidate_id,
                push_type="recommend_to_hr",
                payload={
                    "decision": normalized_decision,
                    "score": float(score),
                    "source": source,
                    "owner": owner,
                },
            )
            insert_candidate_action(
                candidate_id,
                "email_recommend_push",
                "queued",
                {
                    "push_record_id": push_record_id,
                    "source": source,
                    "target_user_id": user_id,
                    "target_owner": owner,
                },
            )
            add_candidate_timeline_event(
                candidate_id,
                "email_recommend_pushed",
                source,
                {
                    "push_record_id": push_record_id,
                    "target_user_id": user_id,
                    "owner": owner,
                    "score": float(score),
                },
            )
            return {
                "pipeline_state": state,
                "push_record_id": push_record_id,
            }

        if normalized_decision == "review":
            state = upsert_candidate_pipeline_state(
                candidate_id,
                owner=owner,
                current_stage="to_review",
                final_decision="review",
                manual_stage_locked=False,
            )
            add_candidate_timeline_event(
                candidate_id,
                "email_review_queued",
                source,
                {
                    "owner": owner,
                    "score": float(score),
                },
            )
            return {
                "pipeline_state": state,
                "push_record_id": None,
            }

        state = upsert_candidate_pipeline_state(
            candidate_id,
            owner=owner,
            current_stage="rejected",
            final_decision="reject",
            manual_stage_locked=False,
        )
        add_candidate_timeline_event(
            candidate_id,
            "email_reject_archived",
            source,
            {
                "owner": owner,
                "score": float(score),
            },
        )
        return {
            "pipeline_state": state,
            "push_record_id": None,
        }

    def _create_push_record(
        self,
        *,
        ingest_record_id: str,
        user_id: str,
        candidate_id: str,
        push_type: str,
        payload: dict[str, Any],
    ) -> str:
        push_record_id = str(uuid.uuid4())
        with connect() as conn:
            conn.execute(
                """
                insert into email_resume_push_records (
                    id, ingest_record_id, user_id, candidate_id, push_type, status, payload
                ) values (?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    push_record_id,
                    str(ingest_record_id or "").strip(),
                    str(user_id or "").strip(),
                    str(candidate_id or "").strip(),
                    str(push_type or "").strip(),
                    dumps(payload or {}),
                ),
            )
        return push_record_id

