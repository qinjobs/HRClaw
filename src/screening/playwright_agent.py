from __future__ import annotations

import hashlib
import os
import random
import re
import time
from typing import Any

from .boss_selectors import BossSelectors, load_boss_selectors
from .browser_runtime import PlaywrightBrowserRuntime
from .candidate_heuristics import (
    build_fallback_normalized_fields,
    extract_age,
    extract_education_level,
    extract_salary,
    extract_years_experience,
    infer_candidate_item,
)
from .config import load_local_env
from .gpt_extractor import GPTFieldExtractor
from .models import CandidateExtract
from .repositories import list_seen_candidate_external_ids
from .scoring import score_candidate


def _extract_external_id(detail_url: str | None, fallback_index: int, fallback_text: str | None = None) -> str:
    if detail_url:
        match = re.search(r"/([A-Za-z0-9_-]{6,})\.html", detail_url)
        if match:
            return match.group(1)
    source = re.sub(r"\s+", " ", str(fallback_text or "")).strip()
    if source:
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
        return f"playwright-fp-{digest}"
    return f"playwright-{fallback_index}"


class PlaywrightLocalAgent:
    def __init__(
        self,
        *,
        runtime: PlaywrightBrowserRuntime | None = None,
        selectors: BossSelectors | None = None,
        extractor: GPTFieldExtractor | None = None,
        existing_candidate_checker=None,
    ) -> None:
        load_local_env()
        self.runtime = runtime or PlaywrightBrowserRuntime()
        self.selectors = selectors or load_boss_selectors()
        self.extractor = extractor or GPTFieldExtractor()
        self.existing_candidate_checker = existing_candidate_checker or list_seen_candidate_external_ids
        self.session_id: str | None = None
        self._greet_count = 0

    def start_session(self) -> str:
        self.session_id = self.runtime.start()
        self._greet_count = 0
        return self.session_id

    def stop_session(self) -> None:
        self.runtime.stop()
        self.session_id = None

    def collect_candidates(
        self,
        job_id: str,
        max_candidates: int,
        *,
        search_mode: str | None = None,
        search_config: dict[str, Any] | None = None,
        sort_by: str | None = None,
        max_pages: int = 1,
    ) -> list[CandidateExtract]:
        if self.session_id is None:
            raise RuntimeError("Browser session is not started. Call start_session() first.")

        normalized_mode = (search_mode or "").strip().lower()
        if normalized_mode in {"recommend", "recommend_flow", "recommendation"}:
            return self._collect_recommend_candidates(
                job_id,
                max_candidates=max_candidates,
                max_pages=max_pages,
                search_config=search_config or {},
            )
        return self._collect_search_candidates(
            job_id,
            max_candidates=max_candidates,
            search_config=search_config or {},
            sort_by=sort_by,
            max_pages=max_pages,
        )

    def _collect_search_candidates(
        self,
        job_id: str,
        *,
        max_candidates: int,
        search_config: dict[str, Any],
        sort_by: str | None,
        max_pages: int,
    ) -> list[CandidateExtract]:
        self.runtime.goto_search_page(self.selectors)
        self._handle_login_scan_wait(search_config, flow="search")
        self._handle_manual_verification(search_config, flow="search")
        if not self.runtime.wait_for_any(self.selectors.list_ready, timeout_ms=15000):
            self._handle_login_scan_wait(search_config, flow="search")
            self._handle_manual_verification(search_config, flow="search")
            raise RuntimeError(
                "Candidate list did not become ready. Check login state or update BOSS selectors."
            )

        applied_filters = self.runtime.apply_search_filters(self.selectors, search_config, sort_by)
        queued_cards: list[dict[str, Any]] = []
        seen_external_ids: set[str] = set()
        page_index = 1
        while page_index <= max(1, max_pages) and len(queued_cards) < max_candidates:
            cards = self.runtime.collect_candidate_cards(self.selectors, max_candidates * 2)
            recent_seen = self._recent_seen_external_ids(cards, search_config)
            for card in cards:
                external_id = card.get("external_id")
                if external_id in seen_external_ids or external_id in recent_seen:
                    continue
                seen_external_ids.add(external_id)
                card["page_index"] = page_index
                queued_cards.append(card)
                if len(queued_cards) >= max_candidates:
                    break
            if len(queued_cards) >= max_candidates:
                break
            self._pause_for_human_browse(search_config, stage="page_turn")
            if not self.runtime.go_to_next_page(self.selectors):
                break
            page_index += 1

        candidates = []
        for index, card in enumerate(queued_cards[:max_candidates], start=1):
            self._pause_for_human_browse(search_config, stage="open_candidate")
            self.runtime.open_candidate_card(card, self.selectors)
            detail = self.runtime.extract_detail_payload(self.selectors)
            screenshot_base64, screenshot_base64_error = self._safe_screenshot_base64()
            screenshot_path, screenshot_error = self._safe_persist_screenshot(f"{job_id}_candidate_{index}")
            merged_text = "\n".join(
                part for part in (card.get("summary_text"), detail.get("page_text")) if part
            )
            heuristic_item = infer_candidate_item(job_id, merged_text)
            extraction_error: str | None = None
            extracted: dict[str, Any] = {}
            extraction_usage: dict[str, Any] | None = None
            try:
                extracted = self.extractor.extract_candidate(job_id, detail.get("page_text") or merged_text, screenshot_base64)
                extraction_usage = getattr(self.extractor, "last_usage", None)
            except Exception as exc:
                extraction_error = str(exc)
                extraction_usage = getattr(self.extractor, "last_usage", None)
            item = self.extractor.merge_with_fallback(job_id, extracted, heuristic_item)
            candidates.append(
                CandidateExtract(
                    external_id=card.get("external_id")
                    or _extract_external_id(detail.get("detail_url"), index, merged_text),
                    name=item.get("name") or card.get("name"),
                    age=item.get("age") or extract_age(merged_text),
                    education_level=item.get("education_level") or card.get("education_level") or extract_education_level(merged_text),
                    major=item.get("major"),
                    years_experience=item.get("years_experience") or card.get("years_experience") or extract_years_experience(merged_text),
                    current_company=item.get("current_company") or card.get("current_company"),
                    current_title=item.get("current_title") or card.get("current_title"),
                    expected_salary=item.get("expected_salary") or extract_salary(merged_text),
                    location=item.get("location") or card.get("location"),
                    last_active_time=item.get("last_active_time") or card.get("last_active_time"),
                    raw_summary=item.get("resume_summary") or detail.get("page_text") or card.get("summary_text"),
                    normalized_fields=item.get("normalized_fields") or build_fallback_normalized_fields(job_id, item),
                    evidence_map={
                        "list_summary": card.get("summary_text"),
                        "list_url": card.get("detail_url"),
                        "detail_url": detail.get("detail_url"),
                        "detail_excerpt": (detail.get("page_text") or "")[:500],
                        "selector_mode": "playwright_local",
                        "gpt_extraction_enabled": getattr(self.extractor, "enabled", False),
                        "gpt_extraction_used": bool(extracted),
                        "model_name": getattr(self.extractor, "model", None),
                        "model_usage": extraction_usage,
                        **({"gpt_extraction_error": extraction_error} if extraction_error else {}),
                        **({"screenshot_error": screenshot_error} if screenshot_error else {}),
                        **({"screenshot_base64_error": screenshot_base64_error} if screenshot_base64_error else {}),
                        "page_index": card.get("page_index"),
                        "applied_filters": applied_filters,
                        **item.get("evidence_map", {}),
                    },
                    screenshot_path=screenshot_path or "",
                )
            )

        return candidates

    def _collect_recommend_candidates(
        self,
        job_id: str,
        *,
        max_candidates: int,
        max_pages: int,
        search_config: dict[str, Any],
    ) -> list[CandidateExtract]:
        self.runtime.goto_recommend_page(self.selectors)
        self._handle_login_scan_wait(search_config, flow="recommend")
        self._handle_manual_verification(search_config, flow="recommend")
        if not self.runtime.wait_for_any(self.selectors.recommend_list_ready, timeout_ms=15000):
            self._handle_login_scan_wait(search_config, flow="recommend")
            self._handle_manual_verification(search_config, flow="recommend")
            if not self.runtime.wait_for_any(("body",), timeout_ms=5000):
                raise RuntimeError("Recommend page did not load. Check login state or recommend selectors.")

        auto_greet_enabled = self._is_truthy_env("SCREENING_AUTO_GREET_ENABLED", default=True)
        auto_greet_threshold = self._float_env("SCREENING_AUTO_GREET_THRESHOLD", default=90.0)
        auto_greet_max = self._int_env("SCREENING_AUTO_GREET_MAX_PER_TASK", default=max_candidates)
        auto_greet_allow_non_recommend = self._is_truthy_env(
            "SCREENING_AUTO_GREET_ALLOW_NON_RECOMMEND",
            default=False,
        )
        candidates: list[CandidateExtract] = []
        seen_card_keys: set[str] = set()
        page_index = 1
        candidate_index = 0
        while page_index <= max(1, max_pages) and len(candidates) < max_candidates:
            self._handle_login_scan_wait(search_config, flow="recommend")
            self._handle_manual_verification(search_config, flow="recommend")
            page_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2)
            if not page_cards and page_index == 1:
                for _ in range(6):
                    self._handle_login_scan_wait(search_config, flow="recommend")
                    self._handle_manual_verification(search_config, flow="recommend")
                    self.runtime.wait_for_any(self.selectors.recommend_list_ready, timeout_ms=2000)
                    page_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2)
                    if page_cards:
                        break
            if not page_cards:
                self._handle_login_scan_wait(search_config, flow="recommend")
                self._handle_manual_verification(search_config, flow="recommend")
                break

            page_processed = 0
            while len(candidates) < max_candidates:
                current_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2) or page_cards
                recent_seen = self._recent_seen_external_ids(current_cards, search_config)
                target_card: dict[str, Any] | None = None
                target_key: str | None = None
                for card in current_cards:
                    key = str(
                        card.get("external_id")
                        or card.get("detail_url")
                        or f"p{page_index}-i{card.get('card_index')}"
                    )
                    if key in seen_card_keys:
                        continue
                    if card.get("external_id") in recent_seen:
                        continue
                    target_card = card
                    target_key = key
                    break

                if target_card is None:
                    break

                seen_card_keys.add(target_key or "")
                target_card["page_index"] = page_index
                candidate_index += 1
                current_candidate: CandidateExtract | None = None
                close_result = None
                try:
                    self._handle_login_scan_wait(search_config, flow="recommend")
                    self._handle_manual_verification(search_config, flow="recommend")
                    self._pause_for_human_browse(search_config, stage="open_candidate")
                    self.runtime.open_recommend_candidate(target_card, self.selectors)
                    detail = self.runtime.extract_recommend_detail_payload(self.selectors)
                    download_result = self.runtime.download_resume(
                        self.selectors,
                        external_id=target_card.get("external_id") or f"candidate-{candidate_index}",
                    )
                    screenshot_base64, screenshot_base64_error = self._safe_screenshot_base64()
                    screenshot_path, screenshot_error = self._safe_persist_screenshot(f"{job_id}_candidate_{candidate_index}")
                    merged_text = "\n".join(
                        part for part in (target_card.get("summary_text"), detail.get("page_text")) if part
                    )
                    if not download_result.get("downloaded"):
                        try:
                            fallback_path = self.runtime.persist_resume_text(
                                target_card.get("external_id") or f"candidate-{candidate_index}",
                                detail.get("page_text") or merged_text,
                            )
                            download_result["resume_path"] = fallback_path
                            download_result["fallback_exported"] = True
                        except Exception as exc:
                            download_result["fallback_export_error"] = str(exc)
                    heuristic_item = infer_candidate_item(job_id, merged_text)
                    extraction_error: str | None = None
                    extracted: dict[str, Any] = {}
                    extraction_usage: dict[str, Any] | None = None
                    try:
                        extracted = self.extractor.extract_candidate(job_id, detail.get("page_text") or merged_text, screenshot_base64)
                        extraction_usage = getattr(self.extractor, "last_usage", None)
                    except Exception as exc:
                        extraction_error = str(exc)
                        extraction_usage = getattr(self.extractor, "last_usage", None)
                    item = self.extractor.merge_with_fallback(job_id, extracted, heuristic_item)
                    normalized_fields = item.get("normalized_fields") or build_fallback_normalized_fields(job_id, item)
                    years_experience = target_card.get("years_experience") or extract_years_experience(merged_text)
                    if item.get("years_experience"):
                        years_experience = item.get("years_experience")
                    education_level = target_card.get("education_level") or extract_education_level(merged_text)
                    if item.get("education_level"):
                        education_level = item.get("education_level")
                    pre_score = score_candidate(
                        job_id,
                        normalized_fields | {
                            "years_experience": years_experience,
                            "education_level": education_level,
                        },
                    )
                    greet_info = self._try_auto_greet(
                        total_score=pre_score.total_score,
                        decision=pre_score.decision.value,
                        threshold=auto_greet_threshold,
                        enabled=auto_greet_enabled,
                        max_actions=auto_greet_max,
                        allow_non_recommend=auto_greet_allow_non_recommend,
                    )
                    current_candidate = CandidateExtract(
                        external_id=target_card.get("external_id")
                        or _extract_external_id(detail.get("detail_url"), candidate_index, merged_text),
                        name=item.get("name") or target_card.get("name"),
                        age=item.get("age") or extract_age(merged_text),
                        education_level=education_level,
                        major=item.get("major"),
                        years_experience=years_experience,
                        current_company=item.get("current_company") or target_card.get("current_company"),
                        current_title=item.get("current_title") or target_card.get("current_title"),
                        expected_salary=item.get("expected_salary") or extract_salary(merged_text),
                        location=item.get("location") or target_card.get("location"),
                        last_active_time=item.get("last_active_time") or target_card.get("last_active_time"),
                        raw_summary=item.get("resume_summary") or detail.get("page_text") or target_card.get("summary_text"),
                        normalized_fields=normalized_fields,
                        evidence_map={
                            "flow_mode": "recommend",
                            "list_summary": target_card.get("summary_text"),
                            "detail_url": detail.get("detail_url"),
                            "detail_excerpt": (detail.get("page_text") or "")[:500],
                            "selector_mode": "playwright_local",
                            "gpt_extraction_enabled": getattr(self.extractor, "enabled", False),
                            "gpt_extraction_used": bool(extracted),
                            "model_name": getattr(self.extractor, "model", None),
                            "model_usage": extraction_usage,
                            **({"gpt_extraction_error": extraction_error} if extraction_error else {}),
                            **({"screenshot_error": screenshot_error} if screenshot_error else {}),
                            **({"screenshot_base64_error": screenshot_base64_error} if screenshot_base64_error else {}),
                            "resume_downloaded": download_result.get("downloaded", False),
                            "resume_path": download_result.get("resume_path"),
                            "resume_download_reason": download_result.get("reason"),
                            "resume_filename": download_result.get("suggested_filename"),
                            "resume_fallback_exported": download_result.get("fallback_exported", False),
                            "resume_fallback_export_error": download_result.get("fallback_export_error"),
                            "auto_greet_enabled": auto_greet_enabled,
                            "auto_greet_threshold": auto_greet_threshold,
                            "auto_greet_allow_non_recommend": auto_greet_allow_non_recommend,
                            "auto_greet_score": pre_score.total_score,
                            **greet_info,
                            "page_index": target_card.get("page_index"),
                            **item.get("evidence_map", {}),
                        },
                        screenshot_path=screenshot_path or "",
                    )
                    candidates.append(current_candidate)
                    page_processed += 1
                except Exception:
                    # Single card failures should not abort the whole task.
                    pass
                finally:
                    try:
                        close_result = self.runtime.close_recommend_detail(self.selectors)
                    except Exception:
                        close_result = False
                    if current_candidate is not None:
                        current_candidate.evidence_map["recommend_detail_closed"] = bool(close_result)

            if len(candidates) >= max_candidates:
                break
            # Prevent infinite page turning when no usable cards are found.
            if page_processed == 0:
                break
            self._pause_for_human_browse(search_config, stage="page_turn")
            if not self.runtime.go_to_next_page(self.selectors):
                break
            page_index += 1

        return candidates

    def _recent_seen_external_ids(self, cards: list[dict[str, Any]], search_config: dict[str, Any]) -> set[str]:
        if not self._is_truthy(search_config.get("skip_existing_candidates"), default=False):
            return set()
        external_ids = [str(card.get("external_id") or "").strip() for card in cards if str(card.get("external_id") or "").strip()]
        if not external_ids:
            return set()
        max_age_hours = search_config.get("refresh_window_hours")
        try:
            age_hours = float(max_age_hours) if max_age_hours not in (None, "") else None
        except Exception:
            age_hours = None
        try:
            return set(self.existing_candidate_checker(external_ids, max_age_hours=age_hours) or set())
        except Exception:
            return set()

    def _pause_for_human_browse(self, search_config: dict[str, Any], *, stage: str) -> None:
        minimum = self._float_value(
            search_config.get("resume_browse_delay_min_seconds"),
            fallback=self._float_env("SCREENING_RESUME_BROWSE_DELAY_MIN_SECONDS", default=0.0),
        )
        maximum = self._float_value(
            search_config.get("resume_browse_delay_max_seconds"),
            fallback=self._float_env("SCREENING_RESUME_BROWSE_DELAY_MAX_SECONDS", default=0.0),
        )
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        delay = max(0.0, random.uniform(minimum, maximum))
        if delay <= 0:
            return
        time.sleep(delay)

    def _handle_manual_verification(self, search_config: dict[str, Any], *, flow: str) -> None:
        checker = getattr(self.runtime, "is_manual_verification_page", None)
        if not callable(checker):
            return
        try:
            needs_verification = bool(checker())
        except Exception:
            needs_verification = False
        if not needs_verification:
            return
        wait_timeout_seconds = self._float_value(
            search_config.get("manual_verification_timeout_seconds"),
            fallback=self._float_env("SCREENING_MANUAL_VERIFICATION_TIMEOUT_SECONDS", default=180.0),
        )
        waiter = getattr(self.runtime, "wait_for_manual_verification", None)
        if callable(waiter):
            cleared = bool(waiter(timeout_ms=max(1000, int(wait_timeout_seconds * 1000))))
            if cleared:
                return
        raise RuntimeError(f"BOSS {flow} page requires manual verification before continuing.")

    def _handle_login_scan_wait(self, search_config: dict[str, Any], *, flow: str) -> None:
        checker = getattr(self.runtime, "is_login_scan_page", None)
        if not callable(checker):
            return
        try:
            needs_scan = bool(checker())
        except Exception:
            needs_scan = False
        if not needs_scan:
            return
        wait_timeout_seconds = self._float_value(
            search_config.get("login_scan_wait_seconds"),
            fallback=self._float_env("SCREENING_LOGIN_SCAN_WAIT_SECONDS", default=20.0),
        )
        waiter = getattr(self.runtime, "wait_for_login_scan", None)
        if callable(waiter):
            cleared = bool(waiter(timeout_ms=max(1000, int(wait_timeout_seconds * 1000))))
            if cleared:
                return
        raise RuntimeError(f"BOSS {flow} page is waiting for QR scan login before continuing.")

    def _try_auto_greet(
        self,
        *,
        total_score: float,
        decision: str,
        threshold: float,
        enabled: bool,
        max_actions: int,
        allow_non_recommend: bool,
    ) -> dict[str, Any]:
        if not enabled:
            return {"auto_greet_attempted": False, "auto_greet_clicked": False, "auto_greet_reason": "disabled"}
        if not allow_non_recommend and str(decision).lower() != "recommend":
            return {"auto_greet_attempted": False, "auto_greet_clicked": False, "auto_greet_reason": "decision_not_recommend"}
        if total_score < threshold:
            return {"auto_greet_attempted": False, "auto_greet_clicked": False, "auto_greet_reason": "below_threshold"}
        if self._greet_count >= max(0, max_actions):
            return {"auto_greet_attempted": False, "auto_greet_clicked": False, "auto_greet_reason": "max_actions_reached"}
        action = self.runtime.click_recommend_greet(self.selectors)
        clicked = bool(action.get("clicked"))
        if clicked:
            self._greet_count += 1
        return {
            "auto_greet_attempted": True,
            "auto_greet_clicked": clicked,
            "auto_greet_reason": action.get("reason"),
        }

    @staticmethod
    def _is_truthy(value: Any, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _float_value(value: Any, *, fallback: float = 0.0) -> float:
        try:
            return float(value) if value not in (None, "") else fallback
        except Exception:
            return fallback

    def _safe_screenshot_base64(self) -> tuple[str | None, str | None]:
        try:
            return self.runtime.screenshot_base64(), None
        except Exception as exc:
            return None, str(exc)

    def _safe_persist_screenshot(self, label: str) -> tuple[str | None, str | None]:
        try:
            return self.runtime.persist_screenshot(label), None
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _is_truthy_env(name: str, *, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() not in {"0", "false", "off", "no"}

    @staticmethod
    def _int_env(name: str, *, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def _float_env(name: str, *, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default
