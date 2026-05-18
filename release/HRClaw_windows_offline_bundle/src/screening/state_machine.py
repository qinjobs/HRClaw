from __future__ import annotations

from .models import TaskStatus


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.BOOTING_BROWSER, TaskStatus.FAILED},
    TaskStatus.BOOTING_BROWSER: {TaskStatus.LOGGING_IN, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.LOGGING_IN: {TaskStatus.OPENING_SEARCH_PAGE, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.OPENING_SEARCH_PAGE: {TaskStatus.CONFIGURING_FILTERS, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.CONFIGURING_FILTERS: {TaskStatus.SCANNING_CANDIDATE_LIST, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.SCANNING_CANDIDATE_LIST: {TaskStatus.OPENING_CANDIDATE, TaskStatus.AWAITING_HR_REVIEW, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.OPENING_CANDIDATE: {TaskStatus.CAPTURING_SNAPSHOT, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.CAPTURING_SNAPSHOT: {TaskStatus.EXTRACTING_FIELDS, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.EXTRACTING_FIELDS: {TaskStatus.SCORING_CANDIDATE, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.SCORING_CANDIDATE: {TaskStatus.OPENING_CANDIDATE, TaskStatus.AWAITING_HR_REVIEW, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.AWAITING_HR_REVIEW: {TaskStatus.RESUMING, TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.RESUMING: {TaskStatus.OPENING_CANDIDATE, TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.BLOCKED: {TaskStatus.RESUMING, TaskStatus.FAILED},
    TaskStatus.FAILED: set(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: str, target: str) -> None:
    current_status = TaskStatus(current)
    target_status = TaskStatus(target)
    if not can_transition(current_status, target_status):
        raise ValueError(f"Invalid task state transition: {current} -> {target}")
