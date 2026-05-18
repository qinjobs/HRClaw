from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    CREATED = "created"
    BOOTING_BROWSER = "booting_browser"
    LOGGING_IN = "logging_in"
    OPENING_SEARCH_PAGE = "opening_search_page"
    CONFIGURING_FILTERS = "configuring_filters"
    SCANNING_CANDIDATE_LIST = "scanning_candidate_list"
    OPENING_CANDIDATE = "opening_candidate"
    CAPTURING_SNAPSHOT = "capturing_snapshot"
    EXTRACTING_FIELDS = "extracting_fields"
    SCORING_CANDIDATE = "scoring_candidate"
    AWAITING_HR_REVIEW = "awaiting_hr_review"
    RESUMING = "resuming"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class CandidateDecision(StrEnum):
    RECOMMEND = "recommend"
    REVIEW = "review"
    REJECT = "reject"


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    HOLD = "hold"


class ConfirmableAction(StrEnum):
    SEND_GREETING = "send_greeting"
    DOWNLOAD_RESUME = "download_resume"
    ADVANCE_PIPELINE = "advance_pipeline"


@dataclass(slots=True)
class TaskCreateRequest:
    job_id: str
    search_mode: str
    sort_by: str
    max_candidates: int
    max_pages: int = 1
    search_config: dict[str, Any] = field(default_factory=dict)
    require_hr_confirmation: bool = True


@dataclass(slots=True)
class CandidateExtract:
    external_id: str
    name: str | None = None
    age: int | None = None
    education_level: str | None = None
    major: str | None = None
    years_experience: float | None = None
    current_company: str | None = None
    current_title: str | None = None
    expected_salary: str | None = None
    location: str | None = None
    last_active_time: str | None = None
    raw_summary: str | None = None
    normalized_fields: dict[str, Any] = field(default_factory=dict)
    evidence_map: dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""


@dataclass(slots=True)
class ScoreResult:
    hard_filter_pass: bool
    hard_filter_fail_reasons: list[str]
    dimension_scores: dict[str, float]
    total_score: float
    decision: CandidateDecision
    review_reasons: list[str]
