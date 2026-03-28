from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .scorecards import SCORECARDS


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "screening.db"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def dumps(value):
    return json.dumps(value, ensure_ascii=True)


def loads(value):
    if value is None:
        return None
    return json.loads(value)


def init_db() -> None:
    seed_builtin_scorecards = os.getenv("SCREENING_SEED_BUILTIN_SCORECARDS", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists jobs (
                id text primary key,
                name text not null,
                version text not null,
                scorecard text not null,
                active integer not null default 1,
                created_at text not null default current_timestamp
            );

            create table if not exists screening_tasks (
                id text primary key,
                job_id text not null,
                status text not null,
                search_mode text not null,
                sort_by text not null,
                max_candidates integer not null,
                max_pages integer not null default 1,
                search_config text not null default '{}',
                token_usage text,
                require_hr_confirmation integer not null default 1,
                browser_session_id text,
                started_at text,
                finished_at text,
                created_at text not null default current_timestamp
            );

            create table if not exists candidates (
                id text primary key,
                task_id text not null,
                source text not null default 'pipeline',
                external_id text,
                name text,
                age integer,
                education_level text,
                major text,
                years_experience real,
                current_company text,
                current_title text,
                expected_salary text,
                location text,
                last_active_time text,
                raw_summary text,
                normalized_fields text not null,
                created_at text not null default current_timestamp
            );

            create index if not exists idx_candidates_external_id on candidates(external_id);
            create index if not exists idx_candidates_task_created on candidates(task_id, created_at);

            create table if not exists candidate_snapshots (
                id text primary key,
                candidate_id text not null,
                page_type text not null,
                screenshot_path text not null,
                extracted_text text,
                evidence_map text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists candidate_scores (
                id text primary key,
                candidate_id text not null,
                scorecard_version text not null,
                hard_filter_pass integer not null,
                hard_filter_fail_reasons text not null,
                dimension_scores text not null,
                total_score real not null,
                decision text not null,
                review_reasons text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists review_actions (
                id text primary key,
                candidate_id text not null,
                reviewer text not null,
                action text not null,
                comment text,
                final_decision text,
                created_at text not null default current_timestamp
            );

            create table if not exists candidate_actions (
                id text primary key,
                candidate_id text not null,
                action_type text not null,
                status text not null,
                detail text not null default '{}',
                created_at text not null default current_timestamp
            );

            create table if not exists candidate_pipeline_state (
                candidate_id text primary key,
                owner text,
                current_stage text not null default 'new',
                reason_code text,
                reason_notes text,
                final_decision text,
                last_contacted_at text,
                last_contact_result text,
                next_follow_up_at text,
                reusable_flag integer not null default 0,
                do_not_contact integer not null default 0,
                manual_stage_locked integer not null default 0,
                talent_pool_status text,
                updated_at text not null default current_timestamp,
                created_at text not null default current_timestamp
            );

            create index if not exists idx_candidate_pipeline_stage on candidate_pipeline_state(current_stage, updated_at);
            create index if not exists idx_candidate_pipeline_owner on candidate_pipeline_state(owner, updated_at);
            create index if not exists idx_candidate_pipeline_followup on candidate_pipeline_state(next_follow_up_at, updated_at);

            create table if not exists candidate_tags (
                id text primary key,
                candidate_id text not null,
                tag text not null,
                tag_type text not null default 'manual',
                created_by text not null,
                created_at text not null default current_timestamp,
                unique(candidate_id, tag)
            );

            create index if not exists idx_candidate_tags_candidate on candidate_tags(candidate_id, created_at);

            create table if not exists candidate_timeline_events (
                id text primary key,
                candidate_id text not null,
                event_type text not null,
                event_payload text not null default '{}',
                operator text,
                created_at text not null default current_timestamp
            );

            create index if not exists idx_candidate_timeline_candidate on candidate_timeline_events(candidate_id, created_at);

            create table if not exists run_logs (
                id integer primary key autoincrement,
                task_id text not null,
                level text not null,
                event_type text not null,
                payload text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists extension_score_events (
                id text primary key,
                job_id text not null,
                page_url text not null,
                external_id text,
                source text not null default 'boss_extension_v1',
                page_title text,
                candidate_hint text,
                decision text not null,
                total_score real not null,
                fallback_used integer not null default 0,
                model_usage text not null default '{}',
                created_at text not null default current_timestamp
            );

            create index if not exists idx_extension_score_events_created on extension_score_events(created_at);
            create index if not exists idx_extension_score_events_page on extension_score_events(page_url, created_at);

            create table if not exists extension_candidate_bindings (
                id text primary key,
                candidate_id text not null,
                job_id text not null,
                task_id text not null,
                source text not null,
                source_candidate_key text not null,
                external_id text,
                page_url text,
                latest_text_hash text not null,
                first_seen_at text not null default current_timestamp,
                last_seen_at text not null default current_timestamp,
                last_scored_at text,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                unique(job_id, source, source_candidate_key)
            );

            create index if not exists idx_ext_bindings_candidate on extension_candidate_bindings(candidate_id, updated_at);
            create index if not exists idx_ext_bindings_external on extension_candidate_bindings(job_id, external_id, updated_at);
            create index if not exists idx_ext_bindings_task on extension_candidate_bindings(task_id, updated_at);

            create table if not exists resume_profiles (
                id text primary key,
                source text not null,
                external_id text not null,
                source_candidate_id text,
                name text,
                city text,
                years_experience real,
                education_level text,
                latest_title text,
                latest_company text,
                skills text not null default '[]',
                industry_tags text not null default '[]',
                raw_profile text not null,
                raw_resume_entry text not null default '{}',
                updated_at text not null default current_timestamp,
                created_at text not null default current_timestamp,
                unique(source, external_id)
            );

            create index if not exists idx_resume_profiles_source_candidate on resume_profiles(source_candidate_id);

            create table if not exists resume_chunks (
                id text primary key,
                resume_profile_id text not null,
                source_candidate_id text,
                chunk_type text not null,
                chunk_index integer not null,
                content text not null,
                title text,
                city text,
                experience_years real,
                skills text not null default '[]',
                updated_at text not null default current_timestamp,
                created_at text not null default current_timestamp
            );

            create index if not exists idx_resume_chunks_profile on resume_chunks(resume_profile_id);
            create index if not exists idx_resume_chunks_candidate on resume_chunks(source_candidate_id);

            create table if not exists search_runs (
                id text primary key,
                jd_text text,
                query_text text,
                filters text not null default '{}',
                top_k integer not null default 20,
                explain integer not null default 0,
                status text not null,
                query_intent text,
                degraded text not null default '[]',
                model_summary text not null default '{}',
                retrieval_latency_ms integer not null default 0,
                rerank_latency_ms integer not null default 0,
                total_latency_ms integer not null default 0,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_search_runs_created_at on search_runs(created_at);

            create table if not exists search_results (
                id text primary key,
                search_run_id text not null,
                rank integer not null,
                resume_profile_id text not null,
                source_candidate_id text,
                retrieval_score real not null default 0,
                fit_score real,
                final_score real not null default 0,
                hard_filter_pass integer not null default 1,
                matched_evidence text not null default '[]',
                gaps text not null default '[]',
                risk_flags text not null default '[]',
                interview_questions text not null default '[]',
                final_recommendation text,
                explanation_status text not null default 'pending',
                created_at text not null default current_timestamp
            );

            create index if not exists idx_search_results_run_rank on search_results(search_run_id, rank);

            create table if not exists collection_pipelines (
                id text primary key,
                name text not null,
                job_id text not null,
                search_mode text not null default 'recommend',
                sort_by text not null default 'active',
                max_candidates integer not null default 50,
                max_pages integer not null default 10,
                schedule_minutes integer not null default 60,
                enabled integer not null default 1,
                search_configs text not null default '[]',
                runtime_options text not null default '{}',
                last_task_id text,
                last_run_status text,
                last_run_started_at text,
                last_run_finished_at text,
                next_run_at text,
                last_error text,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_collection_pipelines_next_run on collection_pipelines(enabled, next_run_at);

            create table if not exists collection_pipeline_runs (
                id text primary key,
                pipeline_id text not null,
                status text not null,
                task_ids text not null default '[]',
                summary text not null default '{}',
                error text,
                started_at text not null default current_timestamp,
                finished_at text,
                created_at text not null default current_timestamp
            );

            create index if not exists idx_collection_pipeline_runs_pipeline on collection_pipeline_runs(pipeline_id, created_at);

            create table if not exists custom_scorecards (
                id text primary key,
                name text not null,
                jd_text text,
                scorecard text not null,
                created_by text not null default 'hr_ui',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_custom_scorecards_updated on custom_scorecards(updated_at, created_at);

            create table if not exists jd_scorecards (
                id text primary key,
                name text not null,
                jd_text text,
                scorecard text not null,
                scorecard_kind text not null,
                engine_type text not null,
                schema_version text not null,
                supports_resume_import integer not null default 0,
                editable integer not null default 1,
                system_managed integer not null default 0,
                active integer not null default 1,
                created_by text not null default 'hr_ui',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_jd_scorecards_kind on jd_scorecards(scorecard_kind, active, updated_at);
            create index if not exists idx_jd_scorecards_engine on jd_scorecards(engine_type, active, updated_at);
            create index if not exists idx_jd_scorecards_importable on jd_scorecards(supports_resume_import, active, updated_at);

            create table if not exists resume_import_batches (
                id text primary key,
                scorecard_id text not null,
                scorecard_name text not null,
                batch_name text not null,
                created_by text not null default 'hr_ui',
                total_files integer not null default 0,
                processed_files integer not null default 0,
                recommend_count integer not null default 0,
                review_count integer not null default 0,
                reject_count integer not null default 0,
                summary text not null default '{}',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_resume_import_batches_created on resume_import_batches(created_at);

            create table if not exists resume_import_results (
                id text primary key,
                batch_id text not null,
                scorecard_id text not null,
                resume_profile_id text,
                filename text not null,
                file_path text not null,
                parse_status text not null,
                extracted_name text,
                years_experience real,
                education_level text,
                location text,
                total_score real,
                decision text,
                hard_filter_pass integer not null default 0,
                hard_filter_fail_reasons text not null default '[]',
                matched_terms text not null default '[]',
                missing_terms text not null default '[]',
                dimension_scores text not null default '{}',
                summary text,
                detail text not null default '{}',
                created_at text not null default current_timestamp
            );

            create index if not exists idx_resume_import_results_batch on resume_import_results(batch_id, created_at);

            create table if not exists hr_users (
                id text primary key,
                username text not null unique collate nocase,
                display_name text not null,
                password_hash text not null,
                role text not null default 'hr',
                active integer not null default 1,
                notes text not null default '',
                last_login_at text,
                system_managed integer not null default 0,
                created_by text not null default 'system',
                updated_by text not null default 'system',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_hr_users_role_active on hr_users(role, active, created_at);

            create table if not exists system_state (
                key text primary key,
                value text not null,
                updated_at text not null default current_timestamp
            );
            """
        )
        try:
            conn.execute(
                """
                create virtual table if not exists resume_chunks_fts using fts5(
                    chunk_id unindexed,
                    content,
                    title,
                    city,
                    skills
                )
                """
            )
        except sqlite3.OperationalError:
            # Some sqlite builds may omit FTS5; search service will degrade gracefully.
            pass
        columns = {row["name"] for row in conn.execute("pragma table_info(screening_tasks)").fetchall()}
        if "max_pages" not in columns:
            conn.execute("alter table screening_tasks add column max_pages integer not null default 1")
        if "search_config" not in columns:
            conn.execute("alter table screening_tasks add column search_config text not null default '{}'")
        if "token_usage" not in columns:
            conn.execute("alter table screening_tasks add column token_usage text")
        candidate_columns = {row["name"] for row in conn.execute("pragma table_info(candidates)").fetchall()}
        if "source" not in candidate_columns:
            conn.execute("alter table candidates add column source text not null default 'pipeline'")
        pipeline_columns = {row["name"] for row in conn.execute("pragma table_info(candidate_pipeline_state)").fetchall()}
        if "manual_stage_locked" not in pipeline_columns:
            conn.execute("alter table candidate_pipeline_state add column manual_stage_locked integer not null default 0")
        conn.execute("create index if not exists idx_candidates_source_created on candidates(source, created_at)")
        conn.execute(
            "create index if not exists idx_candidate_pipeline_manual_lock on candidate_pipeline_state(manual_stage_locked, updated_at)"
        )
        if seed_builtin_scorecards:
            for job_id, scorecard in SCORECARDS.items():
                conn.execute(
                    """
                    insert into jobs (id, name, version, scorecard, active)
                    values (?, ?, ?, ?, 1)
                    on conflict(id) do update set
                        name = excluded.name,
                        version = excluded.version,
                        scorecard = excluded.scorecard,
                        active = excluded.active
                    """,
                    (job_id, scorecard["name"], job_id, dumps(scorecard)),
                )
                conn.execute(
                    """
                    insert into jd_scorecards (
                        id, name, jd_text, scorecard, scorecard_kind, engine_type, schema_version,
                        supports_resume_import, editable, system_managed, active, created_by
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do nothing
                    """,
                    (
                        job_id,
                        scorecard["name"],
                        "",
                        dumps(scorecard),
                        "builtin_phase1",
                        "builtin_formula",
                        "phase1_builtin_v1",
                        0,
                        1,
                        1,
                        1,
                        "system",
                    ),
                )
        custom_rows = conn.execute("select * from custom_scorecards").fetchall()
        for row in custom_rows:
            item = dict(row)
            scorecard = loads(item.get("scorecard")) or {}
            conn.execute(
                """
                insert into jd_scorecards (
                    id, name, jd_text, scorecard, scorecard_kind, engine_type, schema_version,
                    supports_resume_import, editable, system_managed, active, created_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do nothing
                """,
                (
                    str(item.get("id") or ""),
                    str(item.get("name") or scorecard.get("name") or item.get("id") or ""),
                    str(item.get("jd_text") or scorecard.get("jd_text") or ""),
                    dumps(scorecard),
                    "custom_phase2",
                    "generic_resume_match",
                    str(scorecard.get("schema_version") or "phase2_scorecard_v1"),
                    1,
                    1,
                    0,
                    1,
                    str(item.get("created_by") or "hr_ui"),
                    str(item.get("created_at") or "current_timestamp"),
                    str(item.get("updated_at") or item.get("created_at") or "current_timestamp"),
                ),
            )
    from .hr_users import ensure_default_admin_user

    ensure_default_admin_user(
        os.getenv("SCREENING_WEB_USERNAME", "admin"),
        os.getenv("SCREENING_WEB_PASSWORD", "admin"),
    )
