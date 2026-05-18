from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EmailResumeFile:
    user_id: str
    source_date: str
    file_path: Path
    file_name: str
    file_size: int
    modified_at: float


@dataclass(slots=True)
class EmailIngestDecision:
    decision: str
    total_score: float
    hard_filter_pass: bool
    hard_filter_fail_reasons: list[str] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    blocked_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EmailIngestResult:
    ingest_record_id: str
    file_sha1: str
    parse_status: str
    resume_profile_id: str | None
    candidate_id: str | None
    decision: str
    total_score: float
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmailIngestRunSummary:
    ok: bool
    user_id: str
    scorecard_id: str
    source: str
    trigger: str
    scan_directory: str | None = None
    scanned_files: int = 0
    new_files: int = 0
    duplicate_files: int = 0
    processed_files: int = 0
    recommend_count: int = 0
    review_count: int = 0
    reject_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    task_id: str | None = None
    batch_id: str | None = None
    errors: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
