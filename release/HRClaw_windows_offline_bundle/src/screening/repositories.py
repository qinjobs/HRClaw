from __future__ import annotations

import hashlib
import re
import uuid

from .db import connect, dumps, loads
from .gpt_extractor import summarize_model_error
from .jd_scorecard_repositories import get_jd_scorecard


def _archive_snapshot_fields(evidence_map: dict | None) -> dict[str, object | None]:
    evidence_map = evidence_map or {}
    full_screenshot_error = evidence_map.get("resume_full_screenshot_error") or evidence_map.get("screenshot_error")
    markdown_error = evidence_map.get("resume_markdown_error")
    return {
        "resume_full_screenshot_path": evidence_map.get("resume_full_screenshot_path"),
        "resume_full_screenshot_error": _summarize_capture_error(full_screenshot_error) if full_screenshot_error else None,
        "resume_full_screenshot_fallback_used": bool(evidence_map.get("resume_full_screenshot_fallback_used")),
        "resume_markdown_path": evidence_map.get("resume_markdown_path"),
        "resume_markdown_filename": evidence_map.get("resume_markdown_filename"),
        "resume_markdown_error": _summarize_capture_error(markdown_error) if markdown_error else None,
    }


def _summarize_capture_error(detail: object) -> str:
    if isinstance(detail, BaseException):
        text = str(detail)
    else:
        text = str(detail or "")
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return "已发生截图或归档错误"
    if len(normalized) > 220:
        return f"{normalized[:217]}..."
    return normalized


def list_jobs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select
                j.*,
                js.name as scorecard_name,
                js.scorecard as unified_scorecard,
                js.scorecard_kind,
                js.engine_type,
                js.schema_version
            from jobs j
            left join jd_scorecards js on js.id = j.id and js.active = 1
            where j.active = 1
            order by j.id asc
            """
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["name"] = item.get("scorecard_name") or item.get("name")
            item["scorecard"] = loads(item.get("unified_scorecard") or item["scorecard"])
            item["kind"] = item.get("scorecard_kind")
            item["engine_type"] = item.get("engine_type")
            item["schema_version"] = item.get("schema_version")
            item.pop("scorecard_name", None)
            item.pop("unified_scorecard", None)
            items.append(item)
        return items


def create_task(payload: dict) -> str:
    task_id = str(uuid.uuid4())
    search_mode = str(payload.get("search_mode") or "recommend").strip().lower() or "recommend"
    with connect() as conn:
        conn.execute(
            """
            insert into screening_tasks (
                id, job_id, status, search_mode, sort_by, max_candidates, max_pages, search_config, require_hr_confirmation
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                payload["job_id"],
                "created",
                search_mode,
                payload.get("sort_by", "active"),
                payload["max_candidates"],
                payload.get("max_pages", 1),
                dumps(payload.get("search_config", {})),
                1 if payload.get("require_hr_confirmation", True) else 0,
            ),
        )
    return task_id


def get_task(task_id: str):
    with connect() as conn:
        row = conn.execute("select * from screening_tasks where id = ?", (task_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["search_config"] = loads(item.get("search_config")) or {}
        item["token_usage"] = loads(item.get("token_usage")) or {}
        return item


def list_recent_tasks(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from screening_tasks
            order by created_at desc
            limit ?
            """,
            (max(1, limit),),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["require_hr_confirmation"] = bool(item["require_hr_confirmation"])
            item["search_config"] = loads(item.get("search_config")) or {}
            item["token_usage"] = loads(item.get("token_usage")) or {}
            items.append(item)
        return items


def _normalize_pipeline_state_row(row: dict | None, *, candidate_id: str) -> dict:
    if not row:
        return {
            "candidate_id": candidate_id,
            "owner": None,
            "current_stage": "new",
            "reason_code": None,
            "reason_notes": None,
            "final_decision": None,
            "last_contacted_at": None,
            "last_contact_result": None,
            "next_follow_up_at": None,
            "reusable_flag": False,
            "do_not_contact": False,
            "manual_stage_locked": False,
            "talent_pool_status": None,
            "updated_at": None,
            "created_at": None,
        }
    item = dict(row)
    item["reusable_flag"] = bool(item.get("reusable_flag"))
    item["do_not_contact"] = bool(item.get("do_not_contact"))
    item["manual_stage_locked"] = bool(item.get("manual_stage_locked"))
    return item


def get_candidate_pipeline_state(candidate_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "select * from candidate_pipeline_state where candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    return _normalize_pipeline_state_row(row, candidate_id=candidate_id)


def upsert_candidate_pipeline_state(
    candidate_id: str,
    *,
    owner: str | None = None,
    current_stage: str | None = None,
    reason_code: str | None = None,
    reason_notes: str | None = None,
    final_decision: str | None = None,
    last_contacted_at: str | None = None,
    last_contact_result: str | None = None,
    next_follow_up_at: str | None = None,
    reusable_flag: bool | None = None,
    do_not_contact: bool | None = None,
    manual_stage_locked: bool | None = None,
    talent_pool_status: str | None = None,
) -> dict:
    with connect() as conn:
        conn.execute(
            "insert into candidate_pipeline_state (candidate_id) values (?) on conflict(candidate_id) do nothing",
            (candidate_id,),
        )
        existing = conn.execute(
            "select * from candidate_pipeline_state where candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        merged = _normalize_pipeline_state_row(existing, candidate_id=candidate_id)
        if owner is not None:
            merged["owner"] = owner or None
        if current_stage is not None:
            merged["current_stage"] = current_stage or "new"
        if reason_code is not None:
            merged["reason_code"] = reason_code or None
        if reason_notes is not None:
            merged["reason_notes"] = reason_notes or None
        if final_decision is not None:
            merged["final_decision"] = final_decision or None
        if last_contacted_at is not None:
            merged["last_contacted_at"] = last_contacted_at or None
        if last_contact_result is not None:
            merged["last_contact_result"] = last_contact_result or None
        if next_follow_up_at is not None:
            merged["next_follow_up_at"] = next_follow_up_at or None
        if reusable_flag is not None:
            merged["reusable_flag"] = bool(reusable_flag)
        if do_not_contact is not None:
            merged["do_not_contact"] = bool(do_not_contact)
        if manual_stage_locked is not None:
            merged["manual_stage_locked"] = bool(manual_stage_locked)
        if talent_pool_status is not None:
            merged["talent_pool_status"] = talent_pool_status or None
        conn.execute(
            """
            update candidate_pipeline_state
            set owner = ?,
                current_stage = ?,
                reason_code = ?,
                reason_notes = ?,
                final_decision = ?,
                last_contacted_at = ?,
                last_contact_result = ?,
                next_follow_up_at = ?,
                reusable_flag = ?,
                do_not_contact = ?,
                manual_stage_locked = ?,
                talent_pool_status = ?,
                updated_at = current_timestamp
            where candidate_id = ?
            """,
            (
                merged.get("owner"),
                merged.get("current_stage") or "new",
                merged.get("reason_code"),
                merged.get("reason_notes"),
                merged.get("final_decision"),
                merged.get("last_contacted_at"),
                merged.get("last_contact_result"),
                merged.get("next_follow_up_at"),
                1 if merged.get("reusable_flag") else 0,
                1 if merged.get("do_not_contact") else 0,
                1 if merged.get("manual_stage_locked") else 0,
                merged.get("talent_pool_status"),
                candidate_id,
            ),
        )
    return get_candidate_pipeline_state(candidate_id)


def add_candidate_tag(candidate_id: str, tag: str, created_by: str, *, tag_type: str = "manual") -> str:
    normalized_tag = str(tag or "").strip()
    if not normalized_tag:
        raise ValueError("tag 不能为空")
    with connect() as conn:
        existing = conn.execute(
            "select id from candidate_tags where candidate_id = ? and tag = ?",
            (candidate_id, normalized_tag),
        ).fetchone()
        if existing:
            tag_id = str(existing["id"])
            conn.execute(
                """
                update candidate_tags
                set tag_type = ?, created_by = ?, created_at = current_timestamp
                where id = ?
                """,
                (tag_type, created_by, tag_id),
            )
            return tag_id
        tag_id = str(uuid.uuid4())
        conn.execute(
            """
            insert into candidate_tags (id, candidate_id, tag, tag_type, created_by)
            values (?, ?, ?, ?, ?)
            """,
            (tag_id, candidate_id, normalized_tag, tag_type, created_by),
        )
    return tag_id


def list_candidate_tags(candidate_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from candidate_tags
            where candidate_id = ?
            order by created_at desc, tag asc
            """,
            (candidate_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_candidate_timeline_event(
    candidate_id: str,
    event_type: str,
    operator: str | None,
    payload: dict | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into candidate_timeline_events (id, candidate_id, event_type, event_payload, operator)
            values (?, ?, ?, ?, ?)
            """,
            (event_id, candidate_id, event_type, dumps(payload or {}), operator),
        )
    return event_id


def list_candidate_timeline(candidate_id: str, *, limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from candidate_timeline_events
            where candidate_id = ?
            order by created_at desc
            limit ?
            """,
            (candidate_id, max(1, limit)),
        ).fetchall()
    return [{**dict(row), "event_payload": loads(row["event_payload"]) or {}} for row in rows]


_EXTENSION_IDENTITY_STOP_LINES = {
    "经历概览",
    "其他相似经历的牛人",
    "其他名企大厂经历牛人",
}
_EXTENSION_IDENTITY_NOISE_LINES = {
    "打招呼",
    "继续沟通",
    "收藏",
    "举报",
    "转发牛人",
    "不合适",
    "推荐牛人",
    "最近关注",
}
_WORKBENCH_STAGE_PRIORITY = {
    "do_not_contact": 120,
    "rejected": 115,
    "interview_scheduled": 110,
    "interview_invited": 100,
    "awaiting_reply": 90,
    "contacted": 85,
    "needs_followup": 80,
    "to_contact": 75,
    "to_review": 70,
    "talent_pool": 65,
    "scored": 30,
    "new": 20,
}


def _normalize_extension_identity_text(value: str | None) -> str:
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line in _EXTENSION_IDENTITY_STOP_LINES:
            break
        if line in _EXTENSION_IDENTITY_NOISE_LINES:
            continue
        if line.startswith("!function(){var e=document"):
            continue
        lines.append(line)
        if len(lines) >= 32 or sum(len(item) for item in lines) >= 1600:
            break
    return "\n".join(lines)


def _hash_extension_identity_text(value: str | None) -> str:
    normalized = _normalize_extension_identity_text(value)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _workbench_item_priority(item: dict) -> tuple:
    pipeline_state = item.get("pipeline_state") or {}
    stage = str(pipeline_state.get("current_stage") or "new")
    score_value = item.get("total_score")
    try:
        total_score = float(score_value) if score_value is not None else -1.0
    except (TypeError, ValueError):
        total_score = -1.0
    return (
        1 if pipeline_state.get("manual_stage_locked") else 0,
        _WORKBENCH_STAGE_PRIORITY.get(stage, 10),
        1 if score_value is not None else 0,
        (
            str(item.get("extension_last_scored_at") or ""),
            str(pipeline_state.get("updated_at") or ""),
            str(item.get("extension_last_seen_at") or ""),
            str(item.get("candidate_created_at") or ""),
            str(item.get("candidate_id") or ""),
        ),
        total_score,
    )


def _build_workbench_dedupe_keys(item: dict) -> list[str]:
    source = str(item.get("source") or "pipeline")
    if source != "boss_extension":
        return [f"candidate:{item.get('candidate_id')}"]
    keys: list[str] = []
    source_candidate_key = str(item.get("extension_source_candidate_key") or "").strip()
    external_id = str(item.get("external_id") or item.get("extension_external_id") or "").strip()
    if external_id:
        keys.append(f"boss_extension:external:{external_id}")
    if source_candidate_key:
        keys.append(f"boss_extension:key:{source_candidate_key}")
    name = str(item.get("name") or "").strip()
    summary_hash = _hash_extension_identity_text(item.get("raw_summary"))
    if name and summary_hash:
        keys.append(f"boss_extension:summary:{name}:{summary_hash}")
    if not keys:
        keys.append(f"candidate:{item.get('candidate_id')}")
    return keys


def _dedupe_hr_workbench_items(items: list[dict]) -> list[dict]:
    chosen_by_anchor: dict[str, dict] = {}
    anchor_keys: dict[str, set[str]] = {}
    key_to_anchor: dict[str, str] = {}
    order: list[str] = []
    for item in items:
        dedupe_keys = _build_workbench_dedupe_keys(item)
        anchors = []
        seen_anchors: set[str] = set()
        for dedupe_key in dedupe_keys:
            anchor = key_to_anchor.get(dedupe_key)
            if anchor and anchor not in seen_anchors:
                anchors.append(anchor)
                seen_anchors.add(anchor)
        if not anchors:
            anchor = dedupe_keys[0]
            chosen_by_anchor[anchor] = item
            anchor_keys[anchor] = set(dedupe_keys)
            order.append(anchor)
        else:
            anchor = anchors[0]
            best_item = chosen_by_anchor[anchor]
            for other_anchor in anchors[1:]:
                other_item = chosen_by_anchor.pop(other_anchor)
                other_keys = anchor_keys.pop(other_anchor, set())
                if _workbench_item_priority(other_item) > _workbench_item_priority(best_item):
                    best_item = other_item
                anchor_keys.setdefault(anchor, set()).update(other_keys)
                if other_anchor in order:
                    order.remove(other_anchor)
            if _workbench_item_priority(item) > _workbench_item_priority(best_item):
                best_item = item
            chosen_by_anchor[anchor] = best_item
            anchor_keys.setdefault(anchor, set()).update(dedupe_keys)
        for dedupe_key in anchor_keys.get(anchor, set(dedupe_keys)):
            key_to_anchor[dedupe_key] = anchor
    return [chosen_by_anchor[key] for key in order]


def _is_valid_workbench_candidate_row(row: dict) -> bool:
    source = str(row.get("source") or "pipeline")
    if source != "boss_extension":
        return True
    name = str(row.get("name") or "").strip()
    page_url = str(row.get("page_url") or "").lower()
    current_title = str(row.get("current_title") or "").strip()
    raw_summary = str(row.get("raw_summary") or "").strip()
    invalid_names = {"职位管理", "速览", "个人资料", "推荐牛人"}
    invalid_titles = {"BOSS直聘", "PDF预览"}
    if not name or name in invalid_names:
        return False
    if current_title in invalid_titles:
        return False
    if "/web/chat/recommend" in page_url or "/bzl-office/pdf-viewer-b" in page_url:
        return False
    if raw_summary.startswith("JD 速览") or raw_summary.startswith("职位管理") or raw_summary.startswith("!function(){var e=document"):
        return False
    return True


def list_hr_workbench_items(
    *,
    task_id: str | None = None,
    job_id: str | None = None,
    source: str | None = None,
    keyword: str | None = None,
    stage: str | None = None,
    decision: str | None = None,
    greet_status: str | None = None,
    owner: str | None = None,
    reusable_only: bool = False,
    do_not_contact: bool | None = None,
    manual_stage_locked: bool | None = None,
    needs_follow_up: bool = False,
    unreviewed_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    keyword_like = f"%{keyword.strip()}%" if keyword and keyword.strip() else None
    with connect() as conn:
        rows = conn.execute(
            """
            select
                c.id as candidate_id,
                c.task_id,
                c.source,
                c.external_id,
                c.name,
                c.age,
                c.education_level,
                c.years_experience,
                c.current_company,
                c.current_title,
                c.expected_salary,
                c.location,
                c.last_active_time,
                c.raw_summary,
                c.created_at as candidate_created_at,
                t.job_id,
                coalesce(js.name, j.name) as job_name,
                t.status as task_status,
                score.total_score,
                score.decision,
                score.review_reasons,
                score.hard_filter_fail_reasons,
                review.action as review_action,
                review.final_decision as review_final_decision,
                review.reviewer,
                review.created_at as review_created_at,
                greet.status as greet_status,
                greet.detail as greet_detail,
                greet.created_at as greet_created_at,
                snap.screenshot_path,
                snap.extracted_text,
                snap.evidence_map,
                ps.owner,
                ps.current_stage,
                ps.reason_code,
                ps.reason_notes,
                ps.final_decision as pipeline_final_decision,
                ps.last_contacted_at,
                ps.last_contact_result,
                ps.next_follow_up_at,
                ps.reusable_flag,
                ps.do_not_contact,
                ps.manual_stage_locked,
                ps.talent_pool_status,
                ps.updated_at as pipeline_updated_at,
                bind.source_candidate_key as extension_source_candidate_key,
                bind.external_id as extension_external_id,
                bind.page_url as extension_page_url,
                bind.last_seen_at as extension_last_seen_at,
                bind.last_scored_at as extension_last_scored_at,
                tagset.tags_text
            from candidates c
            join screening_tasks t on t.id = c.task_id
            left join jobs j on j.id = t.job_id
            left join jd_scorecards js on js.id = t.job_id
            left join candidate_scores score on score.id = (
                select s2.id
                from candidate_scores s2
                where s2.candidate_id = c.id
                order by s2.created_at desc
                limit 1
            )
            left join candidate_snapshots snap on snap.id = (
                select x.id
                from candidate_snapshots x
                where x.candidate_id = c.id
                order by x.created_at desc
                limit 1
            )
            left join review_actions review on review.id = (
                select r.id
                from review_actions r
                where r.candidate_id = c.id
                order by r.created_at desc
                limit 1
            )
            left join candidate_actions greet on greet.id = (
                select a.id
                from candidate_actions a
                where a.candidate_id = c.id and a.action_type = 'send_greeting'
                order by a.created_at desc
                limit 1
            )
            left join candidate_pipeline_state ps on ps.candidate_id = c.id
            left join extension_candidate_bindings bind on bind.id = (
                select b2.id
                from extension_candidate_bindings b2
                where b2.candidate_id = c.id
                order by b2.updated_at desc, b2.created_at desc, b2.id desc
                limit 1
            )
            left join (
                select candidate_id, group_concat(tag, '||') as tags_text
                from candidate_tags
                group by candidate_id
            ) tagset on tagset.candidate_id = c.id
            where (? is null or c.task_id = ?)
              and (? is null or t.job_id = ?)
              and (? is null or c.source = ?)
              and (? is null or coalesce(ps.current_stage, 'new') = ?)
              and (? is null or score.decision = ?)
              and (? is null or greet.status = ?)
              and (? is null or ps.owner = ?)
              and (? = 0 or coalesce(ps.reusable_flag, 0) = 1)
              and (? is null or coalesce(ps.do_not_contact, 0) = ?)
              and (? is null or coalesce(ps.manual_stage_locked, 0) = ?)
              and (? = 0 or ps.next_follow_up_at is not null)
              and (? = 0 or review.id is null)
              and (
                    ? is null
                    or c.name like ?
                    or c.current_company like ?
                    or c.current_title like ?
                    or c.raw_summary like ?
                    or c.external_id like ?
                  )
            order by
                case when ps.next_follow_up_at is not null then 0 else 1 end asc,
                ps.next_follow_up_at asc,
                c.created_at desc
            limit ?
            """,
            (
                task_id,
                task_id,
                job_id,
                job_id,
                source,
                source,
                stage,
                stage,
                decision,
                decision,
                greet_status,
                greet_status,
                owner,
                owner,
                1 if reusable_only else 0,
                None if do_not_contact is None else (1 if do_not_contact else 0),
                None if do_not_contact is None else (1 if do_not_contact else 0),
                None if manual_stage_locked is None else (1 if manual_stage_locked else 0),
                None if manual_stage_locked is None else (1 if manual_stage_locked else 0),
                1 if needs_follow_up else 0,
                1 if unreviewed_only else 0,
                keyword_like,
                keyword_like,
                keyword_like,
                keyword_like,
                keyword_like,
                keyword_like,
                max(1, limit),
            ),
        ).fetchall()
    items = []
    for row in rows:
        if not _is_valid_workbench_candidate_row(
            {
                "source": row["source"],
                "name": row["name"],
                "current_title": row["current_title"],
                "raw_summary": row["raw_summary"],
                "page_url": row["extension_page_url"],
            }
        ):
            continue
        evidence_map = loads(row["evidence_map"]) if row["evidence_map"] else {}
        review_reasons = loads(row["review_reasons"]) if row["review_reasons"] else []
        hard_filter_fail_reasons = loads(row["hard_filter_fail_reasons"]) if row["hard_filter_fail_reasons"] else []
        tags = []
        if row["tags_text"]:
            tags = [tag for tag in str(row["tags_text"]).split("||") if tag]
        archive_fields = _archive_snapshot_fields(evidence_map)
        item = {
            "candidate_id": row["candidate_id"],
            "task_id": row["task_id"],
            "source": row["source"] or "pipeline",
            "external_id": row["external_id"] or row["extension_external_id"],
            "extension_source_candidate_key": row["extension_source_candidate_key"],
            "extension_external_id": row["extension_external_id"],
            "name": row["name"],
            "age": row["age"],
            "education_level": row["education_level"],
            "years_experience": row["years_experience"],
            "current_company": row["current_company"],
            "current_title": row["current_title"],
            "expected_salary": row["expected_salary"],
            "location": row["location"],
            "last_active_time": row["last_active_time"],
            "raw_summary": row["raw_summary"],
            "candidate_created_at": row["candidate_created_at"],
            "job_id": row["job_id"],
            "job_name": row["job_name"],
            "task_status": row["task_status"],
            "total_score": row["total_score"],
            "decision": row["decision"],
            "review_reasons": review_reasons or [],
            "hard_filter_fail_reasons": hard_filter_fail_reasons or [],
            "review_action": row["review_action"],
            "review_final_decision": row["review_final_decision"],
            "reviewer": row["reviewer"],
            "review_created_at": row["review_created_at"],
            "greet_status": row["greet_status"],
            "greet_detail": loads(row["greet_detail"]) if row["greet_detail"] else None,
            "greet_created_at": row["greet_created_at"],
            "screenshot_path": row["screenshot_path"],
            **archive_fields,
            "extracted_text": row["extracted_text"],
            "gpt_extraction_used": evidence_map.get("gpt_extraction_used"),
            "gpt_extraction_error": summarize_model_error(evidence_map.get("gpt_extraction_error"))
            if evidence_map.get("gpt_extraction_error")
            else None,
            "pipeline_state": _normalize_pipeline_state_row(
                {
                    "candidate_id": row["candidate_id"],
                    "owner": row["owner"],
                    "current_stage": row["current_stage"] or "new",
                    "reason_code": row["reason_code"],
                    "reason_notes": row["reason_notes"],
                    "final_decision": row["pipeline_final_decision"],
                    "last_contacted_at": row["last_contacted_at"],
                    "last_contact_result": row["last_contact_result"],
                    "next_follow_up_at": row["next_follow_up_at"],
                    "reusable_flag": row["reusable_flag"],
                    "do_not_contact": row["do_not_contact"],
                    "manual_stage_locked": row["manual_stage_locked"],
                    "talent_pool_status": row["talent_pool_status"],
                    "updated_at": row["pipeline_updated_at"],
                    "created_at": None,
                }
                if row["current_stage"] or row["owner"] or row["reason_code"] or row["next_follow_up_at"] or row["pipeline_updated_at"]
                else None,
                candidate_id=row["candidate_id"],
            ),
            "extension_page_url": row["extension_page_url"],
            "extension_last_seen_at": row["extension_last_seen_at"],
            "extension_last_scored_at": row["extension_last_scored_at"],
            "tags": tags,
        }
        items.append(item)
    return _dedupe_hr_workbench_items(items)


def find_extension_candidate_binding_by_identity(
    *,
    job_id: str,
    source: str,
    candidate_name: str,
    raw_summary: str | None,
) -> dict | None:
    normalized_name = str(candidate_name or "").strip()
    summary_hash = _hash_extension_identity_text(raw_summary)
    if not normalized_name or not summary_hash:
        return None
    with connect() as conn:
        rows = conn.execute(
            """
            select
                bind.*,
                c.raw_summary,
                c.created_at as candidate_created_at,
                ps.current_stage,
                ps.manual_stage_locked,
                ps.updated_at as pipeline_updated_at
            from extension_candidate_bindings bind
            join candidates c on c.id = bind.candidate_id
            left join candidate_pipeline_state ps on ps.candidate_id = c.id
            where bind.job_id = ? and bind.source = ? and c.name = ?
              and bind.id = (
                    select b2.id
                    from extension_candidate_bindings b2
                    where b2.candidate_id = c.id
                    order by b2.updated_at desc, b2.created_at desc, b2.id desc
                    limit 1
              )
            """,
            (job_id, source, normalized_name),
        ).fetchall()
    best: dict | None = None
    best_priority: tuple | None = None
    for row in rows:
        row_dict = dict(row)
        if _hash_extension_identity_text(row_dict.get("raw_summary")) != summary_hash:
            continue
        item = {
            "candidate_id": row_dict["candidate_id"],
            "candidate_created_at": row_dict.get("candidate_created_at"),
            "extension_last_seen_at": row_dict.get("last_seen_at"),
            "total_score": None,
            "pipeline_state": {
                "current_stage": row_dict.get("current_stage") or "new",
                "manual_stage_locked": bool(row_dict.get("manual_stage_locked")),
                "updated_at": row_dict.get("pipeline_updated_at"),
            },
        }
        priority = _workbench_item_priority(item)
        if best is None or priority > (best_priority or ()):
            best = row_dict
            best_priority = priority
    return best


def list_hr_checklist_items(
    *,
    task_id: str | None = None,
    job_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 300,
) -> list[dict]:
    scorecard_cache: dict[str, dict[str, str | None]] = {}

    def enrich_search_config(search_config: dict | None, *, row_job_id: str | None, row_job_name: str | None) -> dict:
        normalized = dict(search_config or {})
        keyword = str(normalized.get("keyword") or "").strip()
        city = str(normalized.get("city") or "").strip()
        cache_key = str(row_job_id or "").strip()
        if cache_key not in scorecard_cache:
            scorecard_row = get_jd_scorecard(cache_key) if cache_key else None
            scorecard = scorecard_row.get("scorecard") if isinstance(scorecard_row, dict) else {}
            filters = scorecard.get("filters") if isinstance(scorecard, dict) else {}
            scorecard_cache[cache_key] = {
                "keyword": str(
                    (scorecard_row or {}).get("name")
                    or (scorecard or {}).get("role_title")
                    or row_job_name
                    or ""
                ).strip()
                or None,
                "city": str((filters or {}).get("location") or "").strip() or None,
            }
        defaults = scorecard_cache.get(cache_key, {})
        if not keyword and defaults.get("keyword"):
            normalized["keyword"] = defaults["keyword"]
        if not city and defaults.get("city"):
            normalized["city"] = defaults["city"]
        return normalized

    with connect() as conn:
        rows = conn.execute(
            """
            select
                c.id as candidate_id,
                c.task_id,
                c.external_id,
                c.name,
                c.age,
                c.education_level,
                c.years_experience,
                c.current_company,
                c.current_title,
                c.expected_salary,
                c.location,
                c.last_active_time,
                c.created_at as candidate_created_at,
                t.job_id,
                coalesce(js.name, j.name) as job_name,
                t.status as task_status,
                t.created_at as task_created_at,
                t.started_at as task_started_at,
                t.finished_at as task_finished_at,
                t.search_config as task_search_config,
                t.token_usage as task_token_usage,
                score.total_score,
                score.decision,
                review.action as review_action,
                review.final_decision,
                review.reviewer,
                review.created_at as review_created_at,
                greet.status as greet_status,
                greet.detail as greet_detail,
                greet.created_at as greet_created_at,
                snap.screenshot_path,
                snap.evidence_map
            from candidates c
            join screening_tasks t on t.id = c.task_id
            left join jobs j on j.id = t.job_id
            left join jd_scorecards js on js.id = t.job_id
            left join candidate_scores score on score.id = (
                select s2.id
                from candidate_scores s2
                where s2.candidate_id = c.id
                order by s2.created_at desc
                limit 1
            )
            left join candidate_snapshots snap on snap.id = (
                select x.id
                from candidate_snapshots x
                where x.candidate_id = c.id
                order by x.created_at desc
                limit 1
            )
            left join review_actions review on review.id = (
                select r.id
                from review_actions r
                where r.candidate_id = c.id
                order by r.created_at desc
                limit 1
            )
            left join candidate_actions greet on greet.id = (
                select a.id
                from candidate_actions a
                where a.candidate_id = c.id and a.action_type = 'send_greeting'
                order by a.created_at desc
                limit 1
            )
            where (? is null or c.task_id = ?)
              and (? is null or t.job_id = ?)
              and (? is null or date(coalesce(t.started_at, t.created_at)) >= date(?))
              and (? is null or date(coalesce(t.started_at, t.created_at)) <= date(?))
            order by c.created_at desc
            limit ?
            """,
            (
                task_id,
                task_id,
                job_id,
                job_id,
                date_from,
                date_from,
                date_to,
                date_to,
                max(1, limit),
            ),
        ).fetchall()
        items = []
        for row in rows:
            evidence_map = loads(row["evidence_map"]) if row["evidence_map"] else {}
            search_config = loads(row["task_search_config"]) if row["task_search_config"] else {}
            task_token_usage = loads(row["task_token_usage"]) if row["task_token_usage"] else {}
            archive_fields = _archive_snapshot_fields(evidence_map)
            item = {
                "candidate_id": row["candidate_id"],
                "task_id": row["task_id"],
                "job_id": row["job_id"],
                "job_name": row["job_name"],
                "task_status": row["task_status"],
                "task_created_at": row["task_created_at"],
                "task_started_at": row["task_started_at"],
                "task_finished_at": row["task_finished_at"],
                "search_config": enrich_search_config(
                    search_config,
                    row_job_id=row["job_id"],
                    row_job_name=row["job_name"],
                ),
                "task_token_usage": task_token_usage or {},
                "external_id": row["external_id"],
                "name": row["name"],
                "age": row["age"],
                "education_level": row["education_level"],
                "years_experience": row["years_experience"],
                "current_company": row["current_company"],
                "current_title": row["current_title"],
                "expected_salary": row["expected_salary"],
                "location": row["location"],
                "last_active_time": row["last_active_time"],
                "candidate_created_at": row["candidate_created_at"],
                "total_score": row["total_score"],
                "decision": row["decision"],
                "review_action": row["review_action"],
                "final_decision": row["final_decision"],
                "reviewer": row["reviewer"],
                "review_created_at": row["review_created_at"],
                "greet_status": row["greet_status"],
                "greet_detail": loads(row["greet_detail"]) if row["greet_detail"] else None,
                "greet_created_at": row["greet_created_at"],
                "screenshot_path": row["screenshot_path"],
                **archive_fields,
                "gpt_extraction_used": evidence_map.get("gpt_extraction_used"),
                "gpt_extraction_error": summarize_model_error(evidence_map.get("gpt_extraction_error"))
                if evidence_map.get("gpt_extraction_error")
                else None,
            }
            items.append(item)
        return items


def list_seen_candidate_external_ids(external_ids: list[str], *, max_age_hours: float | None = None) -> set[str]:
    normalized = sorted({str(item).strip() for item in (external_ids or []) if str(item).strip()})
    if not normalized:
        return set()
    placeholders = ",".join("?" for _ in normalized)
    sql = f"""
        select distinct external_id
        from candidates
        where external_id in ({placeholders})
          and external_id is not null
    """
    params: list[object] = list(normalized)
    if max_age_hours is not None and max_age_hours >= 0:
        sql += " and datetime(created_at) >= datetime('now', ?)"
        params.append(f"-{float(max_age_hours):.6f} hours")
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {str(row["external_id"]) for row in rows if row["external_id"]}


def update_task_status(task_id: str, status: str, *, browser_session_id: str | None = None) -> None:
    with connect() as conn:
        if browser_session_id is None:
            conn.execute(
                "update screening_tasks set status = ? where id = ?",
                (status, task_id),
            )
        else:
            conn.execute(
                "update screening_tasks set status = ?, browser_session_id = ? where id = ?",
                (status, browser_session_id, task_id),
            )


def mark_task_started(task_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "update screening_tasks set started_at = current_timestamp where id = ?",
            (task_id,),
        )


def mark_task_finished(task_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "update screening_tasks set status = ?, finished_at = current_timestamp where id = ?",
            (status, task_id),
        )


def update_task_token_usage(task_id: str, token_usage: dict) -> None:
    with connect() as conn:
        conn.execute(
            "update screening_tasks set token_usage = ? where id = ?",
            (dumps(token_usage or {}), task_id),
        )


def insert_candidate(task_id: str, candidate: dict) -> str:
    candidate_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into candidates (
                id, task_id, source, external_id, name, age, education_level, major, years_experience,
                current_company, current_title, expected_salary, location, last_active_time,
                raw_summary, normalized_fields
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                task_id,
                candidate.get("source") or "pipeline",
                candidate.get("external_id"),
                candidate.get("name"),
                candidate.get("age"),
                candidate.get("education_level"),
                candidate.get("major"),
                candidate.get("years_experience"),
                candidate.get("current_company"),
                candidate.get("current_title"),
                candidate.get("expected_salary"),
                candidate.get("location"),
                candidate.get("last_active_time"),
                candidate.get("raw_summary"),
                dumps(candidate.get("normalized_fields", {})),
            ),
        )
    return candidate_id


def update_candidate(candidate_id: str, candidate: dict) -> None:
    with connect() as conn:
        row = conn.execute("select * from candidates where id = ?", (candidate_id,)).fetchone()
        if not row:
            raise KeyError(f"Candidate not found: {candidate_id}")
        existing = dict(row)
        merged = {
            "source": candidate.get("source") or existing.get("source") or "pipeline",
            "external_id": candidate.get("external_id") or existing.get("external_id"),
            "name": candidate.get("name") or existing.get("name"),
            "age": candidate.get("age") if candidate.get("age") is not None else existing.get("age"),
            "education_level": candidate.get("education_level") or existing.get("education_level"),
            "major": candidate.get("major") or existing.get("major"),
            "years_experience": candidate.get("years_experience") if candidate.get("years_experience") is not None else existing.get("years_experience"),
            "current_company": candidate.get("current_company") or existing.get("current_company"),
            "current_title": candidate.get("current_title") or existing.get("current_title"),
            "expected_salary": candidate.get("expected_salary") or existing.get("expected_salary"),
            "location": candidate.get("location") or existing.get("location"),
            "last_active_time": candidate.get("last_active_time") or existing.get("last_active_time"),
            "raw_summary": candidate.get("raw_summary") or existing.get("raw_summary"),
            "normalized_fields": candidate.get("normalized_fields") or loads(existing.get("normalized_fields")) or {},
        }
        conn.execute(
            """
            update candidates
            set source = ?,
                external_id = ?,
                name = ?,
                age = ?,
                education_level = ?,
                major = ?,
                years_experience = ?,
                current_company = ?,
                current_title = ?,
                expected_salary = ?,
                location = ?,
                last_active_time = ?,
                raw_summary = ?,
                normalized_fields = ?
            where id = ?
            """,
            (
                merged["source"],
                merged["external_id"],
                merged["name"],
                merged["age"],
                merged["education_level"],
                merged["major"],
                merged["years_experience"],
                merged["current_company"],
                merged["current_title"],
                merged["expected_salary"],
                merged["location"],
                merged["last_active_time"],
                merged["raw_summary"],
                dumps(merged["normalized_fields"]),
                candidate_id,
            ),
        )


def insert_snapshot(candidate_id: str, page_type: str, screenshot_path: str, extracted_text: str, evidence_map: dict) -> str:
    snapshot_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into candidate_snapshots (
                id, candidate_id, page_type, screenshot_path, extracted_text, evidence_map
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (snapshot_id, candidate_id, page_type, screenshot_path, extracted_text, dumps(evidence_map)),
        )
    return snapshot_id


def insert_score(candidate_id: str, scorecard_version: str, score: dict) -> str:
    score_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into candidate_scores (
                id, candidate_id, scorecard_version, hard_filter_pass, hard_filter_fail_reasons,
                dimension_scores, total_score, decision, review_reasons
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score_id,
                candidate_id,
                scorecard_version,
                1 if score["hard_filter_pass"] else 0,
                dumps(score["hard_filter_fail_reasons"]),
                dumps(score["dimension_scores"]),
                score["total_score"],
                score["decision"],
                dumps(score["review_reasons"]),
            ),
        )
    return score_id


def insert_candidate_action(candidate_id: str, action_type: str, status: str, detail: dict | None = None) -> str:
    action_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into candidate_actions (id, candidate_id, action_type, status, detail)
            values (?, ?, ?, ?, ?)
            """,
            (action_id, candidate_id, action_type, status, dumps(detail or {})),
        )
    return action_id


def insert_extension_score_event(
    *,
    job_id: str,
    page_url: str,
    external_id: str | None,
    source: str,
    page_title: str | None,
    candidate_hint: str | None,
    decision: str,
    total_score: float,
    fallback_used: bool,
    model_usage: dict | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into extension_score_events (
                id, job_id, page_url, external_id, source, page_title, candidate_hint,
                decision, total_score, fallback_used, model_usage
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                job_id,
                page_url,
                external_id,
                source,
                page_title,
                candidate_hint,
                decision,
                total_score,
                1 if fallback_used else 0,
                dumps(model_usage or {}),
            ),
        )
    return event_id


def get_or_create_extension_task(job_id: str, *, source: str = "boss_extension") -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            select *
            from screening_tasks
            where job_id = ? and search_mode = 'extension_inbox'
            order by created_at asc
            limit 1
            """,
            (job_id,),
        ).fetchone()
        if not row:
            task_id = str(uuid.uuid4())
            conn.execute(
                """
                insert into screening_tasks (
                    id, job_id, status, search_mode, sort_by, max_candidates, max_pages, search_config, require_hr_confirmation
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    job_id,
                    "extension_inbox",
                    "extension_inbox",
                    "manual",
                    500,
                    1,
                    dumps({"source": source}),
                    0,
                ),
            )
            row = conn.execute("select * from screening_tasks where id = ?", (task_id,)).fetchone()
    item = dict(row)
    item["require_hr_confirmation"] = bool(item["require_hr_confirmation"])
    item["search_config"] = loads(item.get("search_config")) or {}
    item["token_usage"] = loads(item.get("token_usage")) or {}
    return item


def get_extension_candidate_binding(
    *,
    job_id: str,
    source: str,
    source_candidate_key: str,
) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            select *
            from extension_candidate_bindings
            where job_id = ? and source = ? and source_candidate_key = ?
            limit 1
            """,
            (job_id, source, source_candidate_key),
        ).fetchone()
    return None if not row else dict(row)


def get_extension_candidate_binding_by_external_id(
    *,
    job_id: str,
    source: str,
    external_id: str,
) -> dict | None:
    normalized_external_id = str(external_id or "").strip()
    if not normalized_external_id:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            select *
            from extension_candidate_bindings
            where job_id = ? and source = ? and external_id = ?
            order by updated_at desc
            limit 1
            """,
            (job_id, source, normalized_external_id),
        ).fetchone()
    return None if not row else dict(row)


def get_extension_candidate_binding_by_candidate_id(candidate_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """
            select *
            from extension_candidate_bindings
            where candidate_id = ?
            order by updated_at desc
            limit 1
            """,
            (candidate_id,),
        ).fetchone()
    return None if not row else dict(row)


def upsert_extension_candidate_binding(
    *,
    candidate_id: str,
    job_id: str,
    task_id: str,
    source: str,
    source_candidate_key: str,
    external_id: str | None,
    page_url: str | None,
    latest_text_hash: str,
    scored: bool = False,
) -> dict:
    binding = get_extension_candidate_binding(job_id=job_id, source=source, source_candidate_key=source_candidate_key)
    binding_id = str((binding or {}).get("id") or uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into extension_candidate_bindings (
                id, candidate_id, job_id, task_id, source, source_candidate_key,
                external_id, page_url, latest_text_hash, last_scored_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(job_id, source, source_candidate_key) do update set
                candidate_id = excluded.candidate_id,
                task_id = excluded.task_id,
                external_id = coalesce(excluded.external_id, extension_candidate_bindings.external_id),
                page_url = coalesce(excluded.page_url, extension_candidate_bindings.page_url),
                latest_text_hash = excluded.latest_text_hash,
                last_seen_at = current_timestamp,
                last_scored_at = coalesce(excluded.last_scored_at, extension_candidate_bindings.last_scored_at),
                updated_at = current_timestamp
            """,
            (
                binding_id,
                candidate_id,
                job_id,
                task_id,
                source,
                source_candidate_key,
                external_id,
                page_url,
                latest_text_hash,
                None,
            ),
        )
        if scored:
            conn.execute(
                """
                update extension_candidate_bindings
                set last_scored_at = current_timestamp,
                    updated_at = current_timestamp
                where job_id = ? and source = ? and source_candidate_key = ?
                """,
                (job_id, source, source_candidate_key),
            )
        row = conn.execute(
            """
            select *
            from extension_candidate_bindings
            where job_id = ? and source = ? and source_candidate_key = ?
            limit 1
            """,
            (job_id, source, source_candidate_key),
        ).fetchone()
    return dict(row)


def list_extension_score_events(*, limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from extension_score_events
            order by created_at desc, id desc
            limit ?
            """,
            (max(1, limit),),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["fallback_used"] = bool(item.get("fallback_used"))
        item["model_usage"] = loads(item.get("model_usage")) or {}
        items.append(item)
    return items


def list_candidates_for_task(task_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.*, s.total_score, s.decision
            from candidates c
            left join candidate_scores s on s.candidate_id = c.id
            where c.task_id = ?
            order by c.created_at asc
            """,
            (task_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["normalized_fields"] = loads(item["normalized_fields"])
            items.append(item)
        return items


def get_candidate(candidate_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("select * from candidates where id = ?", (candidate_id,)).fetchone()
        if not row:
            return None
        candidate = dict(row)
        candidate["normalized_fields"] = loads(candidate["normalized_fields"])
        score_row = conn.execute(
            "select * from candidate_scores where candidate_id = ? order by created_at desc limit 1",
            (candidate_id,),
        ).fetchone()
        snapshot_row = conn.execute(
            "select * from candidate_snapshots where candidate_id = ? order by created_at desc limit 1",
            (candidate_id,),
        ).fetchone()
        review_rows = conn.execute(
            "select * from review_actions where candidate_id = ? order by created_at asc",
            (candidate_id,),
        ).fetchall()
        action_rows = conn.execute(
            "select * from candidate_actions where candidate_id = ? order by created_at asc",
            (candidate_id,),
        ).fetchall()
        snapshot = None
        if snapshot_row:
            evidence_map = loads(snapshot_row["evidence_map"])
            snapshot = {**dict(snapshot_row), "evidence_map": evidence_map, **_archive_snapshot_fields(evidence_map)}
        return {
            "candidate": candidate,
            "score": None
            if not score_row
            else {
                **dict(score_row),
                "hard_filter_fail_reasons": loads(score_row["hard_filter_fail_reasons"]),
                "dimension_scores": loads(score_row["dimension_scores"]),
                "review_reasons": loads(score_row["review_reasons"]),
            },
            "snapshot": snapshot,
            "reviews": [dict(row) for row in review_rows],
            "actions": [{**dict(row), "detail": loads(row["detail"])} for row in action_rows],
        }


def get_candidate_workbench(candidate_id: str) -> dict | None:
    payload = get_candidate(candidate_id)
    if not payload:
        return None
    candidate = payload["candidate"]
    task = get_task(str(candidate["task_id"]))
    job = None
    if task:
        with connect() as conn:
            job_row = conn.execute("select * from jobs where id = ?", (task["job_id"],)).fetchone()
            unified_job = get_jd_scorecard(str(task["job_id"]))
            if unified_job:
                job = unified_job
            elif job_row:
                job = dict(job_row)
                job["scorecard"] = loads(job["scorecard"])
    return {
        **payload,
        "task": task,
        "job": job,
        "pipeline_state": get_candidate_pipeline_state(candidate_id),
        "extension_binding": get_extension_candidate_binding_by_candidate_id(candidate_id),
        "tags": list_candidate_tags(candidate_id),
        "timeline": list_candidate_timeline(candidate_id),
    }


def add_review_action(candidate_id: str, reviewer: str, action: str, comment: str | None, final_decision: str | None) -> str:
    review_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into review_actions (id, candidate_id, reviewer, action, comment, final_decision)
            values (?, ?, ?, ?, ?, ?)
            """,
            (review_id, candidate_id, reviewer, action, comment, final_decision),
        )
    return review_id


def save_candidate_stage_action(
    candidate_id: str,
    *,
    operator: str,
    current_stage: str,
    reason_code: str | None,
    reason_notes: str | None,
    final_decision: str | None,
    owner: str | None,
    reusable_flag: bool | None,
    do_not_contact: bool | None,
    talent_pool_status: str | None,
    last_contacted_at: str | None,
    last_contact_result: str | None,
    next_follow_up_at: str | None,
) -> dict:
    state = upsert_candidate_pipeline_state(
        candidate_id,
        owner=owner,
        current_stage=current_stage,
        reason_code=reason_code,
        reason_notes=reason_notes,
        final_decision=final_decision,
        last_contacted_at=last_contacted_at,
        last_contact_result=last_contact_result,
        next_follow_up_at=next_follow_up_at,
        reusable_flag=reusable_flag,
        do_not_contact=do_not_contact,
        manual_stage_locked=True,
        talent_pool_status=talent_pool_status,
    )
    add_candidate_timeline_event(
        candidate_id,
        "stage_updated",
        operator,
        {
            "current_stage": current_stage,
            "reason_code": reason_code,
            "reason_notes": reason_notes,
            "final_decision": final_decision,
            "owner": owner,
            "reusable_flag": bool(state.get("reusable_flag")),
            "do_not_contact": bool(state.get("do_not_contact")),
            "talent_pool_status": talent_pool_status,
            "last_contacted_at": last_contacted_at,
            "last_contact_result": last_contact_result,
            "next_follow_up_at": next_follow_up_at,
        },
    )
    return state


def save_candidate_follow_up(
    candidate_id: str,
    *,
    operator: str,
    next_follow_up_at: str | None,
    last_contact_result: str | None,
    comment: str | None,
) -> dict:
    state = upsert_candidate_pipeline_state(
        candidate_id,
        current_stage="needs_followup",
        next_follow_up_at=next_follow_up_at,
        last_contact_result=last_contact_result,
        manual_stage_locked=True,
    )
    add_candidate_timeline_event(
        candidate_id,
        "follow_up_scheduled",
        operator,
        {
            "next_follow_up_at": next_follow_up_at,
            "last_contact_result": last_contact_result,
            "comment": comment,
        },
    )
    return state


def advance_candidate_stage_if_unlocked(
    candidate_id: str,
    *,
    current_stage: str,
    final_decision: str | None = None,
    operator: str = "boss_extension_v1",
) -> dict:
    state = get_candidate_pipeline_state(candidate_id)
    if state.get("manual_stage_locked"):
        return state
    if state.get("current_stage") not in {"new", "scored", None, ""}:
        return state
    updated = upsert_candidate_pipeline_state(
        candidate_id,
        current_stage=current_stage,
        final_decision=final_decision,
        manual_stage_locked=False,
    )
    add_candidate_timeline_event(
        candidate_id,
        "stage_updated",
        operator,
        {
            "current_stage": updated.get("current_stage"),
            "final_decision": updated.get("final_decision"),
            "auto_advanced": True,
        },
    )
    return updated


def add_log(task_id: str, level: str, event_type: str, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            "insert into run_logs (task_id, level, event_type, payload) values (?, ?, ?, ?)",
            (task_id, level, event_type, dumps(payload)),
        )


def list_logs_for_task(task_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "select * from run_logs where task_id = ? order by id asc",
            (task_id,),
        ).fetchall()
        return [{**dict(row), "payload": loads(row["payload"])} for row in rows]


def upsert_collection_pipeline(payload: dict) -> str:
    pipeline_id = str(payload.get("id") or uuid.uuid4())
    schedule_minutes = max(1, int(payload.get("schedule_minutes", 60)))
    search_configs = payload.get("search_configs")
    if not isinstance(search_configs, list) or not search_configs:
        search_configs = [payload.get("search_config") or {}]
    runtime_options = payload.get("runtime_options") if isinstance(payload.get("runtime_options"), dict) else {}
    with connect() as conn:
        existing = conn.execute("select id, next_run_at from collection_pipelines where id = ?", (pipeline_id,)).fetchone()
        next_run_at = payload.get("next_run_at")
        if existing and next_run_at is None:
            next_run_at = existing["next_run_at"]
        conn.execute(
            """
            insert into collection_pipelines (
                id, name, job_id, search_mode, sort_by, max_candidates, max_pages,
                schedule_minutes, enabled, search_configs, runtime_options,
                next_run_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, coalesce(?, current_timestamp), current_timestamp)
            on conflict(id) do update set
                name = excluded.name,
                job_id = excluded.job_id,
                search_mode = excluded.search_mode,
                sort_by = excluded.sort_by,
                max_candidates = excluded.max_candidates,
                max_pages = excluded.max_pages,
                schedule_minutes = excluded.schedule_minutes,
                enabled = excluded.enabled,
                search_configs = excluded.search_configs,
                runtime_options = excluded.runtime_options,
                next_run_at = coalesce(excluded.next_run_at, collection_pipelines.next_run_at),
                updated_at = current_timestamp
            """,
            (
                pipeline_id,
                str(payload.get("name") or pipeline_id),
                payload["job_id"],
                str(payload.get("search_mode") or "recommend").strip().lower() or "recommend",
                str(payload.get("sort_by") or "active"),
                max(1, int(payload.get("max_candidates", 50))),
                max(1, int(payload.get("max_pages", 10))),
                schedule_minutes,
                1 if payload.get("enabled", True) else 0,
                dumps(search_configs),
                dumps(runtime_options),
                next_run_at,
            ),
        )
    return pipeline_id


def get_collection_pipeline(pipeline_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("select * from collection_pipelines where id = ?", (pipeline_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    item["search_configs"] = loads(item.get("search_configs")) or []
    item["runtime_options"] = loads(item.get("runtime_options")) or {}
    return item


def list_collection_pipelines(*, active_only: bool = False) -> list[dict]:
    sql = "select * from collection_pipelines"
    params: list[object] = []
    if active_only:
        sql += " where enabled = 1"
    sql += " order by created_at asc"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    items: list[dict] = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["search_configs"] = loads(item.get("search_configs")) or []
        item["runtime_options"] = loads(item.get("runtime_options")) or {}
        items.append(item)
    return items


def list_due_collection_pipelines() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from collection_pipelines
            where enabled = 1
              and (next_run_at is null or datetime(next_run_at) <= datetime('now'))
            order by coalesce(next_run_at, created_at) asc, created_at asc
            """
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["search_configs"] = loads(item.get("search_configs")) or []
        item["runtime_options"] = loads(item.get("runtime_options")) or {}
        items.append(item)
    return items


def mark_collection_pipeline_running(pipeline_id: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            update collection_pipelines
            set last_run_status = 'running',
                last_error = null,
                last_run_started_at = current_timestamp,
                updated_at = current_timestamp
            where id = ?
            """,
            (pipeline_id,),
        )


def mark_collection_pipeline_finished(
    pipeline_id: str,
    *,
    status: str,
    next_run_at: str | None,
    last_task_id: str | None = None,
    last_error: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            update collection_pipelines
            set last_run_status = ?,
                last_run_finished_at = current_timestamp,
                next_run_at = ?,
                last_task_id = coalesce(?, last_task_id),
                last_error = ?,
                updated_at = current_timestamp
            where id = ?
            """,
            (status, next_run_at, last_task_id, last_error, pipeline_id),
        )


def insert_collection_pipeline_run(pipeline_id: str, *, status: str = "running") -> str:
    run_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            insert into collection_pipeline_runs (id, pipeline_id, status)
            values (?, ?, ?)
            """,
            (run_id, pipeline_id, status),
        )
    return run_id


def finish_collection_pipeline_run(
    run_id: str,
    *,
    status: str,
    task_ids: list[str],
    summary: dict,
    error: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            update collection_pipeline_runs
            set status = ?,
                task_ids = ?,
                summary = ?,
                error = ?,
                finished_at = current_timestamp
            where id = ?
            """,
            (status, dumps(task_ids or []), dumps(summary or {}), error, run_id),
        )


def list_collection_pipeline_runs(pipeline_id: str, *, limit: int = 20) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select *
            from collection_pipeline_runs
            where pipeline_id = ?
            order by created_at desc
            limit ?
            """,
            (pipeline_id, max(1, limit)),
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        item = dict(row)
        item["task_ids"] = loads(item.get("task_ids")) or []
        item["summary"] = loads(item.get("summary")) or {}
        items.append(item)
    return items


def get_system_state(key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("select * from system_state where key = ?", (key,)).fetchone()
    return None if not row else dict(row)


def set_system_state(key: str, value: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into system_state (key, value, updated_at)
            values (?, ?, current_timestamp)
            on conflict(key) do update set
                value = excluded.value,
                updated_at = current_timestamp
            """,
            (key, dumps(value or {})),
        )
