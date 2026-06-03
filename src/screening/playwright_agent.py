from __future__ import annotations

import hashlib
import os
import random
import re
import time
from pathlib import Path
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
    looks_like_mojibake,
    normalize_education_level,
    repair_text_mojibake,
)
from .config import load_local_env
from .gpt_extractor import GPTFieldExtractor
from .jd_scorecard_repositories import get_jd_scorecard
from .models import CandidateExtract
from .repositories import list_seen_candidate_external_ids
from .scorecards import SCORECARDS
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
    _KNOWN_LOCATION_TOKENS = (
        "北京",
        "上海",
        "深圳",
        "广州",
        "杭州",
        "成都",
        "西安",
        "武汉",
        "苏州",
        "南京",
        "长沙",
        "郑州",
        "天津",
    )
    _KNOWN_LOCATION_ENGLISH = {
        "beijing": "Beijing",
        "shanghai": "Shanghai",
        "shenzhen": "Shenzhen",
        "guangzhou": "Guangzhou",
        "hangzhou": "Hangzhou",
        "chengdu": "Chengdu",
        "xian": "Xi'an",
        "xi'an": "Xi'an",
        "wuhan": "Wuhan",
        "suzhou": "Suzhou",
        "nanjing": "Nanjing",
        "changsha": "Changsha",
        "zhengzhou": "Zhengzhou",
        "tianjin": "Tianjin",
    }

    def __init__(
        self,
        *,
        runtime: PlaywrightBrowserRuntime | None = None,
        selectors: BossSelectors | None = None,
        extractor: GPTFieldExtractor | None = None,
        existing_candidate_checker=None,
    ) -> None:
        load_local_env()
        self.runtime = runtime or PlaywrightBrowserRuntime(
            load_storage_state=False,
            persist_storage_state_on_stop=False,
        )
        self.selectors = selectors or load_boss_selectors()
        self.extractor = extractor or GPTFieldExtractor()
        self.existing_candidate_checker = existing_candidate_checker or list_seen_candidate_external_ids
        self.session_id: str | None = None
        self._greet_count = 0
        self._trace_logger = None

    def start_session(self) -> str:
        self.session_id = self.runtime.start()
        self._greet_count = 0
        return self.session_id

    def stop_session(self) -> None:
        self.runtime.stop()
        self.session_id = None

    def set_trace_logger(self, logger) -> None:
        self._trace_logger = logger
        set_event_logger = getattr(self.extractor, "set_event_logger", None)
        if callable(set_event_logger):
            set_event_logger(logger)

    @staticmethod
    def _preferred_candidate_name(extracted_name: Any, fallback_name: Any) -> str | None:
        extracted = PlaywrightLocalAgent._normalized_text(extracted_name)
        if extracted and extracted.lower() not in {"null", "none"} and extracted not in {"未提供", "未知", "匿名", "N/A", "NA", "-"} and not looks_like_mojibake(extracted_name):
            return extracted
        fallback = PlaywrightLocalAgent._normalized_text(fallback_name)
        return fallback or extracted or None

    @staticmethod
    def _normalized_text(value: Any) -> str | None:
        if value is None:
            return None
        repaired = repair_text_mojibake(value)
        text = str(repaired or "").strip()
        if not text:
            return None
        if text.lower() in {"null", "none", "n/a", "na", "-"}:
            return None
        return text

    @classmethod
    def _readable_text(cls, value: Any) -> str | None:
        text = cls._normalized_text(value)
        if not text:
            return None
        if looks_like_mojibake(text):
            return None
        return text

    @staticmethod
    def _preferred_text_field(extracted_value: Any, fallback_value: Any, *, normalize_education: bool = False) -> str | None:
        raw_extracted = str(extracted_value or "").strip()
        if normalize_education:
            extracted = normalize_education_level(extracted_value)
            fallback = normalize_education_level(fallback_value)
        else:
            extracted = PlaywrightLocalAgent._readable_text(extracted_value)
            fallback = PlaywrightLocalAgent._readable_text(fallback_value)
        if fallback and "\ufffd" in raw_extracted:
            return fallback
        if fallback and raw_extracted and looks_like_mojibake(extracted_value):
            if extracted and "\ufffd" not in extracted:
                return extracted
            return fallback
        return extracted or fallback

    @classmethod
    def _clean_text_container(cls, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                key = cls._readable_text(raw_key)
                if not key:
                    continue
                item = cls._clean_text_container(raw_value)
                if item in (None, "", [], {}):
                    continue
                cleaned[key] = item
            return cleaned
        if isinstance(value, (list, tuple, set)):
            items: list[Any] = []
            seen: set[str] = set()
            for raw_item in value:
                item = cls._clean_text_container(raw_item)
                if item in (None, "", [], {}):
                    continue
                marker = str(item).lower()
                if marker in seen:
                    continue
                seen.add(marker)
                items.append(item)
            return items
        if isinstance(value, str):
            return cls._readable_text(value)
        return value

    @classmethod
    def _clean_structured_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        cleaned = cls._clean_text_container(item)
        return cleaned if isinstance(cleaned, dict) else {}

    @staticmethod
    def _preferred_resume_summary(*values: Any) -> str | None:
        best_text: str | None = None
        best_score = float("-inf")
        for value in values:
            raw = str(value or "").strip()
            if not raw:
                continue
            text = PlaywrightLocalAgent._normalized_text(value)
            if not text:
                continue
            score = float(len(text))
            if looks_like_mojibake(raw):
                score -= 500.0
            if "\ufffd" in raw:
                score -= 1000.0
            if re.search(r"[\u4e00-\u9fff]{4,}", text):
                score += 120.0
            if re.search(r"[A-Za-z]{4,}", text):
                score += 40.0
            if score > best_score:
                best_score = score
                best_text = text
        return best_text

    @classmethod
    def _infer_name_from_text(cls, *values: Any) -> str | None:
        for value in values:
            text = cls._normalized_text(value)
            if not text:
                continue
            for raw_line in str(text).splitlines()[:8]:
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue
                if re.fullmatch(r"[\u4e00-\u9fff·]{2,8}", line):
                    return line
        return None

    @classmethod
    def _infer_location_from_text(cls, *values: Any) -> str | None:
        combined_parts: list[str] = []
        for value in values:
            text = cls._normalized_text(value)
            if text:
                combined_parts.append(text)
        if not combined_parts:
            return None
        combined = "\n".join(combined_parts)
        token_hits = [
            (combined.index(token), token)
            for token in cls._KNOWN_LOCATION_TOKENS
            if token in combined
        ]
        if token_hits:
            return min(token_hits, key=lambda item: item[0])[1]
        lowered = combined.lower()
        english_hits: list[tuple[int, str]] = []
        for token, label in cls._KNOWN_LOCATION_ENGLISH.items():
            match = re.search(rf"\b{re.escape(token)}\b", lowered)
            if match:
                english_hits.append((match.start(), label))
        if english_hits:
            return min(english_hits, key=lambda item: item[0])[1]
        return None

    @classmethod
    def _infer_title_from_text(cls, *values: Any) -> str | None:
        title_pattern = re.compile(
            r"((?:AI|AIGC|B端|C端|策略|搜索|数据|平台|高级|资深|助理|初级|中级|Java|Python|前端|后端|测试|软件)?"
            r"(?:产品经理|测试工程师|开发工程师|工程师|设计师|运营|经理|专员|主管|总监))",
            flags=re.IGNORECASE,
        )
        candidates: list[tuple[float, int, str]] = []
        order = 0
        for value in values:
            text = cls._readable_text(value)
            if not text:
                continue
            for raw_line in text.splitlines():
                order += 1
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue
                match = title_pattern.search(line)
                if match:
                    title = match.group(1).strip()
                    score = float(len(title))
                    if re.match(r"^(?:AI|AIGC|B端|C端|策略|搜索|数据|平台)", title, flags=re.IGNORECASE):
                        score += 20.0
                    if re.search(r"\d{4}|至今|公司|科技|数字|教育|网络", line):
                        score += 8.0
                    candidates.append((score, -order, title))
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0], item[1]))[2]

    @classmethod
    def _infer_company_from_text(cls, title: Any, *values: Any) -> str | None:
        title_text = cls._readable_text(title)
        company_suffix = re.compile(r"(公司|集团|科技|网络|数字|教育|信息|智能|有限|中心|工作室)$")
        for value in values:
            text = cls._readable_text(value)
            if not text:
                continue
            for raw_line in text.splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue
                if title_text and title_text in line:
                    before = line.split(title_text, 1)[0]
                else:
                    match = re.search(r"(.{2,40}?)(?:AI|AIGC|B端|C端|策略|搜索|数据|平台)?产品经理", line)
                    before = match.group(1) if match else ""
                before = re.sub(r"^\d{4}(?:[./-]\d{1,2})?\s*(?:至今|[-~至到]\s*\d{4}(?:[./-]\d{1,2})?)?\s*", "", before)
                before = before.strip(" \t丨|·:-—")
                if not before or looks_like_mojibake(before):
                    continue
                if len(before) < 2 or len(before) > 30:
                    continue
                if re.search(r"[\u4e00-\u9fff]", before) and (company_suffix.search(before) or len(before) >= 4):
                    return before
        return None

    @staticmethod
    def _keyword_terms(search_config: dict[str, Any] | None) -> list[str]:
        raw = str((search_config or {}).get("keyword") or "").strip()
        if not raw:
            return []
        terms: list[str] = []
        seen: set[str] = set()
        for part in re.split(r"[;；]+", raw):
            token = re.sub(r"\s+", " ", str(part or "").strip())
            if not token:
                continue
            normalized = token.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(token)
        return terms

    @staticmethod
    def _keyword_match_text(*values: Any) -> str:
        parts: list[str] = []
        for value in values:
            text = PlaywrightLocalAgent._normalized_text(value)
            if text:
                parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _matches_keyword_terms(text: Any, keyword_terms: list[str]) -> bool:
        if not keyword_terms:
            return True
        normalized_text = PlaywrightLocalAgent._normalized_text(text)
        if not normalized_text:
            return False
        folded_text = normalized_text.casefold()
        dense_text = re.sub(r"\s+", "", folded_text)
        for keyword in keyword_terms:
            normalized_keyword = PlaywrightLocalAgent._normalized_text(keyword)
            if not normalized_keyword:
                continue
            folded_keyword = normalized_keyword.casefold()
            dense_keyword = re.sub(r"\s+", "", folded_keyword)
            if folded_keyword not in folded_text and dense_keyword not in dense_text:
                return False
        return True

    @staticmethod
    def _configured_external_ids(search_config: dict[str, Any] | None, *field_names: str) -> set[str]:
        values: set[str] = set()
        config = search_config or {}
        for field_name in field_names:
            raw = config.get(field_name)
            if isinstance(raw, (list, tuple, set)):
                raw_items = raw
            else:
                text = str(raw or "").replace("\uFF1B", ";").replace("\r", "\n")
                raw_items = re.split(r"[,;\n]+", text) if text.strip() else []
            for raw_item in raw_items:
                external_id = str(raw_item or "").strip()
                if external_id:
                    values.add(external_id)
        return values

    @staticmethod
    def _recommend_card_has_identity(card: dict[str, Any]) -> bool:
        return any(str(card.get(field) or "").strip() for field in ("external_id", "name", "summary_text"))

    @staticmethod
    def _recommend_card_visit_key(card: dict[str, Any]) -> str:
        external_id = str(card.get("external_id") or "").strip()
        if external_id and not external_id.startswith("playwright-"):
            return f"id:{external_id}"
        summary_text = re.sub(r"\s+", " ", str(card.get("summary_text") or "")).strip()
        if summary_text:
            return f"summary:{summary_text[:120]}"
        name = str(card.get("name") or "").strip()
        if name:
            return f"name:{name}"
        return f"index:{card.get('card_index')}"

    @staticmethod
    def _recommend_cards_match(expected_card: dict[str, Any], current_card: dict[str, Any]) -> bool:
        expected_external_id = str(expected_card.get("external_id") or "").strip()
        current_external_id = str(current_card.get("external_id") or "").strip()
        expected_name = str(expected_card.get("name") or "").strip()
        current_name = str(current_card.get("name") or "").strip()
        if (
            expected_external_id
            and current_external_id
            and not expected_external_id.startswith("playwright-")
        ):
            return current_external_id == expected_external_id
        if expected_external_id and current_external_id and not expected_external_id.startswith("playwright-"):
            return False
        if expected_name and current_name:
            return current_name == expected_name
        expected_summary = re.sub(r"\s+", " ", str(expected_card.get("summary_text") or "")).strip()
        current_summary = re.sub(r"\s+", " ", str(current_card.get("summary_text") or "")).strip()
        if expected_summary and current_summary and not expected_name and not expected_external_id and expected_summary[:120] == current_summary[:120]:
            return True
        return False

    def _refresh_recommend_target_card(
        self,
        target_card: dict[str, Any],
        page_cards: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for current_card in page_cards:
            if self._recommend_cards_match(target_card, current_card):
                return dict(current_card)
        return None

    def _pick_fresh_recommend_target_card(
        self,
        page_cards: list[dict[str, Any]],
        *,
        seen_card_keys: set[str],
        recent_seen_external_ids: set[str],
        excluded_external_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        excluded_ids = excluded_external_ids or set()
        for current_card in page_cards:
            visit_key = self._recommend_card_visit_key(current_card)
            if visit_key in seen_card_keys:
                continue
            external_id = str(current_card.get("external_id") or "").strip()
            if external_id and external_id in recent_seen_external_ids:
                continue
            if external_id and external_id in excluded_ids:
                continue
            return dict(current_card)
        return None

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
        effective_search_config = dict(search_config or {})
        self._trace(
            "candidate_collection.started",
            job_id=job_id,
            search_mode=normalized_mode or "search",
            sort_by=sort_by,
            max_candidates=max_candidates,
            max_pages=max_pages,
            search_config=effective_search_config,
        )
        if normalized_mode in {"recommend", "recommend_flow", "recommendation"}:
            effective_search_config.setdefault("skip_existing_candidates", True)
            candidates = self._collect_recommend_candidates(
                job_id,
                max_candidates=max_candidates,
                max_pages=max_pages,
                search_config=effective_search_config,
            )
        else:
            candidates = self._collect_search_candidates(
                job_id,
                max_candidates=max_candidates,
                search_config=effective_search_config,
                sort_by=sort_by,
                max_pages=max_pages,
            )
        self._trace(
            "candidate_collection.completed",
            job_id=job_id,
            search_mode=normalized_mode or "search",
            candidate_count=len(candidates),
        )
        return candidates

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
        self._trace("search.page_ready", current_url=self.runtime.current_url)
        self._handle_login_scan_wait(search_config, flow="search")
        self._handle_manual_verification(search_config, flow="search")
        if not self.runtime.wait_for_any(self.selectors.list_ready, timeout_ms=15000):
            self._handle_login_scan_wait(search_config, flow="search")
            self._handle_manual_verification(search_config, flow="search")
            raise RuntimeError(
                "Candidate list did not become ready. Check login state or update BOSS selectors."
            )
        self._trace("search.list_ready", current_url=self.runtime.current_url)

        applied_filters = self.runtime.apply_search_filters(self.selectors, search_config, sort_by)
        self._trace(
            "search.filters_applied",
            sort_by=sort_by,
            search_config=search_config,
            applied_filters=applied_filters,
        )
        queued_cards: list[dict[str, Any]] = []
        seen_external_ids: set[str] = set()
        excluded_external_ids = self._configured_external_ids(search_config, "exclude_external_ids", "exclude_external_id")
        page_index = 1
        while page_index <= max(1, max_pages) and len(queued_cards) < max_candidates:
            cards = self.runtime.collect_candidate_cards(self.selectors, max_candidates * 2)
            recent_seen = self._recent_seen_external_ids(cards, search_config)
            skipped_excluded = 0
            skipped_existing = 0
            for card in cards:
                external_id = card.get("external_id")
                if external_id in excluded_external_ids:
                    skipped_excluded += 1
                    continue
                if external_id in seen_external_ids or external_id in recent_seen:
                    skipped_existing += 1
                    continue
                seen_external_ids.add(external_id)
                card["page_index"] = page_index
                queued_cards.append(card)
                if len(queued_cards) >= max_candidates:
                    break
            self._trace(
                "search.page_cards",
                page_index=page_index,
                card_count=len(cards),
                queued_count=len(queued_cards),
                skipped_existing=skipped_existing,
                skipped_excluded=skipped_excluded,
            )
            if len(queued_cards) >= max_candidates:
                break
            self._pause_for_human_browse(search_config, stage="page_turn")
            has_next_page = bool(self.runtime.go_to_next_page(self.selectors))
            self._trace(
                "search.page_turn",
                page_index=page_index,
                has_next_page=has_next_page,
                current_url=self.runtime.current_url,
            )
            if not has_next_page:
                break
            page_index += 1

        candidates = []
        for index, card in enumerate(queued_cards[:max_candidates], start=1):
            self._pause_for_human_browse(search_config, stage="open_candidate")
            self._trace(
                "search.candidate_opening",
                page_index=card.get("page_index"),
                external_id=card.get("external_id"),
                name=card.get("name"),
            )
            self.runtime.open_candidate_card(card, self.selectors)
            detail = self.runtime.extract_detail_payload(self.selectors)
            self._trace(
                "search.candidate_detail",
                page_index=card.get("page_index"),
                external_id=card.get("external_id"),
                detail_url=detail.get("detail_url"),
                detail_text_chars=len(str(detail.get("page_text") or "")),
            )
            screenshot_base64, screenshot_base64_error = self._safe_screenshot_base64()
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
            item = self._clean_structured_item(item)
            resolved_item = dict(item)
            resolved_item["name"] = self._preferred_candidate_name(item.get("name"), card.get("name"))
            if not resolved_item.get("name") or looks_like_mojibake(resolved_item.get("name")):
                resolved_item["name"] = self._infer_name_from_text(detail.get("page_text"), card.get("summary_text"), merged_text)
            resolved_item["education_level"] = self._preferred_text_field(
                item.get("education_level"),
                card.get("education_level") or extract_education_level(merged_text),
                normalize_education=True,
            )
            resolved_item["current_company"] = self._preferred_text_field(item.get("current_company"), card.get("current_company"))
            resolved_item["current_title"] = self._preferred_text_field(item.get("current_title"), card.get("current_title"))
            if not resolved_item.get("current_title") or looks_like_mojibake(resolved_item.get("current_title")):
                resolved_item["current_title"] = self._infer_title_from_text(
                    card.get("summary_text"),
                    merged_text,
                    detail.get("page_text"),
                )
            if not resolved_item.get("current_company") or looks_like_mojibake(resolved_item.get("current_company")):
                resolved_item["current_company"] = self._infer_company_from_text(
                    resolved_item.get("current_title"),
                    card.get("summary_text"),
                    merged_text,
                    detail.get("page_text"),
                )
            resolved_item["location"] = self._preferred_text_field(item.get("location"), card.get("location"))
            if not resolved_item.get("location") or looks_like_mojibake(resolved_item.get("location")):
                resolved_item["location"] = self._infer_location_from_text(card.get("summary_text"), merged_text, detail.get("page_text"))
            resolved_item["last_active_time"] = self._preferred_text_field(item.get("last_active_time"), card.get("last_active_time"))
            resolved_item["major"] = self._normalized_text(item.get("major"))
            resolved_item["resume_summary"] = self._preferred_resume_summary(
                item.get("resume_summary"),
                detail.get("page_text"),
                card.get("summary_text"),
                merged_text,
            )
            resume_artifacts = self._safe_persist_resume_artifacts(
                card.get("external_id") or f"{job_id}_candidate_{index}",
                detail.get("page_text") or merged_text,
                title=resolved_item.get("current_title") or card.get("current_title") or card.get("name"),
                source_url=detail.get("detail_url") or card.get("detail_url"),
                label=f"{job_id}_candidate_{index}",
                content_html=detail.get("content_html"),
                page_html=detail.get("page_html"),
            )
            self._trace(
                "search.candidate_artifacts",
                page_index=card.get("page_index"),
                external_id=card.get("external_id"),
                resume_markdown_path=resume_artifacts.get("resume_markdown_path"),
                resume_full_screenshot_path=resume_artifacts.get("resume_full_screenshot_path"),
                screenshot_error=resume_artifacts.get("screenshot_error"),
                screenshot_base64_error=screenshot_base64_error,
            )
            normalized_fields = self._build_score_fields(
                item.get("normalized_fields") or build_fallback_normalized_fields(job_id, item),
                item=resolved_item,
                card=card,
                detail=detail,
                merged_text=merged_text,
                years_experience=item.get("years_experience") or card.get("years_experience") or extract_years_experience(merged_text),
                education_level=resolved_item.get("education_level") or card.get("education_level") or extract_education_level(merged_text),
            )
            current_candidate = CandidateExtract(
                external_id=card.get("external_id")
                or _extract_external_id(detail.get("detail_url"), index, merged_text),
                name=resolved_item.get("name"),
                age=item.get("age") or extract_age(merged_text),
                education_level=resolved_item.get("education_level") or card.get("education_level") or extract_education_level(merged_text),
                major=resolved_item.get("major"),
                years_experience=item.get("years_experience") or card.get("years_experience") or extract_years_experience(merged_text),
                current_company=resolved_item.get("current_company") or card.get("current_company"),
                current_title=resolved_item.get("current_title") or card.get("current_title"),
                expected_salary=item.get("expected_salary") or extract_salary(merged_text),
                location=resolved_item.get("location") or card.get("location"),
                last_active_time=resolved_item.get("last_active_time") or card.get("last_active_time"),
                raw_summary=resolved_item.get("resume_summary") or detail.get("page_text") or card.get("summary_text"),
                normalized_fields=normalized_fields,
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
                    **({"screenshot_error": resume_artifacts.get("screenshot_error")} if resume_artifacts.get("screenshot_error") else {}),
                    **({"screenshot_base64_error": screenshot_base64_error} if screenshot_base64_error else {}),
                    **resume_artifacts,
                    "page_index": card.get("page_index"),
                    "applied_filters": applied_filters,
                    **item.get("evidence_map", {}),
                },
                screenshot_path=str(resume_artifacts.get("resume_full_screenshot_path") or resume_artifacts.get("screenshot_path") or ""),
            )
            candidates.append(current_candidate)
            self._trace(
                "search.candidate_compiled",
                page_index=card.get("page_index"),
                external_id=current_candidate.external_id,
                name=current_candidate.name,
                gpt_extraction_used=bool(extracted),
                gpt_extraction_error=extraction_error,
                model_usage=extraction_usage,
            )

        self._trace("search.collect_completed", candidate_count=len(candidates))
        return candidates

    def _collect_recommend_candidates(
        self,
        job_id: str,
        *,
        max_candidates: int,
        max_pages: int,
        search_config: dict[str, Any],
    ) -> list[CandidateExtract]:
        self._trace(
            "recommend.collect_started",
            job_id=job_id,
            max_candidates=max_candidates,
            max_pages=max_pages,
            search_config=search_config,
        )
        self._ensure_recommend_login_ready()
        self._trace("recommend.attach_ready", current_url=self.runtime.current_url)
        self._handle_login_scan_wait(search_config, flow="recommend")
        self._handle_manual_verification(search_config, flow="recommend")
        self.runtime.goto_recommend_page(self.selectors)
        self._trace("recommend.page_ready", current_url=self.runtime.current_url)
        self._ensure_recommend_login_ready()
        self._handle_login_scan_wait(search_config, flow="recommend")
        self._handle_manual_verification(search_config, flow="recommend")
        wait_for_recommend_list_ready = getattr(self.runtime, "wait_for_recommend_list_ready", None)
        recommend_ready = None
        if callable(wait_for_recommend_list_ready):
            recommend_ready = wait_for_recommend_list_ready(self.selectors, timeout_ms=15000)
        else:
            recommend_ready = self.runtime.wait_for_any(self.selectors.recommend_list_ready, timeout_ms=15000)
        recommend_ready_info = self._normalize_recommend_ready_info(recommend_ready, current_url=self.runtime.current_url)
        if recommend_ready_info:
            self._trace("recommend.list_ready", **recommend_ready_info)
        if not recommend_ready:
            self._handle_login_scan_wait(search_config, flow="recommend")
            self._handle_manual_verification(search_config, flow="recommend")
            if not self.runtime.wait_for_any(("body",), timeout_ms=5000):
                raise RuntimeError("Recommend page did not load. Check login state or recommend selectors.")

        auto_greet_enabled = self._is_truthy_env("SCREENING_AUTO_GREET_ENABLED", default=True)
        auto_greet_threshold, auto_greet_threshold_source = self._resolve_auto_greet_threshold(
            job_id,
            search_config,
        )
        auto_greet_max = self._int_env("SCREENING_AUTO_GREET_MAX_PER_TASK", default=max_candidates)
        auto_greet_allow_non_recommend = self._is_truthy_env(
            "SCREENING_AUTO_GREET_ALLOW_NON_RECOMMEND",
            default=False,
        )
        keyword_terms = self._keyword_terms(search_config)
        excluded_external_ids = self._configured_external_ids(
            search_config,
            "exclude_external_ids",
            "exclude_external_id",
        )
        candidates: list[CandidateExtract] = []
        seen_card_keys: set[str] = set()
        page_index = 1
        candidate_index = 0
        while page_index <= max(1, max_pages) and len(candidates) < max_candidates:
            self._handle_login_scan_wait(search_config, flow="recommend")
            self._handle_manual_verification(search_config, flow="recommend")
            page_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2)
            self._trace(
                "recommend.cards_collected",
                page_index=page_index,
                card_count=len(page_cards),
                current_url=self.runtime.current_url,
                ready_selector=(recommend_ready_info or {}).get("ready_selector"),
                frame_name=(recommend_ready_info or {}).get("frame_name"),
                frame_url=(recommend_ready_info or {}).get("frame_url"),
            )
            if not page_cards and page_index == 1:
                # Keep first-page recovery gentle: wait once for manual login/redirect
                # completion, then retry collection a single time.
                self._handle_login_scan_wait(search_config, flow="recommend")
                self._handle_manual_verification(search_config, flow="recommend")
                if callable(wait_for_recommend_list_ready):
                    recommend_ready = wait_for_recommend_list_ready(self.selectors, timeout_ms=5000)
                else:
                    recommend_ready = self.runtime.wait_for_any(self.selectors.recommend_list_ready, timeout_ms=5000)
                recommend_ready_info = self._normalize_recommend_ready_info(recommend_ready, current_url=self.runtime.current_url)
                if recommend_ready_info:
                    self._trace("recommend.list_ready_retry", **recommend_ready_info)
                page_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2)
                self._trace(
                    "recommend.cards_retried",
                    page_index=page_index,
                    card_count=len(page_cards),
                    current_url=self.runtime.current_url,
                    ready_selector=(recommend_ready_info or {}).get("ready_selector"),
                    frame_name=(recommend_ready_info or {}).get("frame_name"),
                    frame_url=(recommend_ready_info or {}).get("frame_url"),
                )
            if not page_cards:
                self._handle_login_scan_wait(search_config, flow="recommend")
                self._handle_manual_verification(search_config, flow="recommend")
                self._trace(
                    "recommend.cards_empty",
                    page_index=page_index,
                    current_url=self.runtime.current_url,
                    ready_selector=(recommend_ready_info or {}).get("ready_selector"),
                    frame_name=(recommend_ready_info or {}).get("frame_name"),
                    frame_url=(recommend_ready_info or {}).get("frame_url"),
                )
                if page_index == 1:
                    detail_parts = [
                        "No recommend candidate cards detected on first page.",
                        f"current_url={self.runtime.current_url}",
                    ]
                    if recommend_ready_info:
                        if recommend_ready_info.get("ready_selector"):
                            detail_parts.append(f"ready_selector={recommend_ready_info['ready_selector']}")
                        if recommend_ready_info.get("frame_url"):
                            detail_parts.append(f"frame_url={recommend_ready_info['frame_url']}")
                        if recommend_ready_info.get("card_count") is not None:
                            detail_parts.append(f"card_count={recommend_ready_info.get('card_count')}")
                    raise RuntimeError(" ".join(detail_parts))
                break

            recent_seen = self._recent_seen_external_ids(page_cards, search_config)
            pending_cards: list[tuple[str, dict[str, Any]]] = []
            skipped_excluded = 0
            skipped_existing = 0
            for card in page_cards:
                key = self._recommend_card_visit_key(card)
                if key in seen_card_keys:
                    continue
                external_id = str(card.get("external_id") or "").strip()
                if external_id and external_id in recent_seen:
                    skipped_existing += 1
                    continue
                if external_id and external_id in excluded_external_ids:
                    skipped_excluded += 1
                    continue
                pending_cards.append((key, card))
            self._trace(
                "recommend.pending_cards",
                page_index=page_index,
                pending_count=len(pending_cards),
                skipped_existing=skipped_existing,
                skipped_excluded=skipped_excluded,
            )

            page_attempted = 0
            page_processed = 0
            page_needs_recovery = False
            for target_key, target_card in pending_cards:
                if len(candidates) >= max_candidates:
                    break

                current_page_cards = self.runtime.collect_recommend_cards(self.selectors, max_candidates * 2)
                if current_page_cards:
                    refreshed_target_card = self._refresh_recommend_target_card(target_card, current_page_cards)
                    if refreshed_target_card is not None:
                        target_card = {**target_card, **refreshed_target_card}
                    else:
                        replacement_target_card = self._pick_fresh_recommend_target_card(
                            current_page_cards,
                            seen_card_keys=seen_card_keys,
                            recent_seen_external_ids=recent_seen,
                            excluded_external_ids=excluded_external_ids,
                        )
                        if replacement_target_card is not None:
                            target_card = replacement_target_card
                            target_key = self._recommend_card_visit_key(target_card)

                seen_card_keys.add(target_key or "")
                target_card["page_index"] = page_index
                candidate_index += 1
                self._trace(
                    "recommend.candidate_opening",
                    page_index=page_index,
                    card_index=target_card.get("card_index"),
                    external_id=target_card.get("external_id"),
                    name=target_card.get("name"),
                )
                current_candidate: CandidateExtract | None = None
                close_result = None
                try:
                    self._handle_login_scan_wait(search_config, flow="recommend")
                    self._handle_manual_verification(search_config, flow="recommend")
                    self._pause_for_human_browse(search_config, stage="open_candidate")
                    page_attempted += 1
                    self.runtime.open_recommend_candidate(target_card, self.selectors)
                    detail = self.runtime.extract_recommend_detail_payload(self.selectors)
                    self._trace(
                        "recommend.candidate_detail",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        external_id=target_card.get("external_id"),
                        detail_url=detail.get("detail_url"),
                        detail_text_chars=len(str(detail.get("page_text") or "")),
                    )
                    merged_text = "\n".join(
                        part for part in (target_card.get("summary_text"), detail.get("page_text")) if part
                    )
                    keyword_match_text = self._keyword_match_text(
                        target_card.get("name"),
                        target_card.get("current_title"),
                        target_card.get("current_company"),
                        target_card.get("location"),
                        target_card.get("summary_text"),
                        detail.get("page_text"),
                    )
                    if keyword_terms and not self._matches_keyword_terms(keyword_match_text, keyword_terms):
                        self._trace(
                            "recommend.candidate_filtered",
                            page_index=page_index,
                            card_index=target_card.get("card_index"),
                            external_id=target_card.get("external_id"),
                            keywords=keyword_terms,
                            reason="keyword_mismatch",
                        )
                        continue
                    resume_full_screenshot_path, resume_full_screenshot_error = self._safe_persist_resume_full_screenshot(
                        target_card.get("external_id") or f"candidate-{candidate_index}",
                    )
                    download_result = self.runtime.download_resume(
                        self.selectors,
                        external_id=target_card.get("external_id") or f"candidate-{candidate_index}",
                    )
                    screenshot_base64, screenshot_base64_error = self._safe_screenshot_base64()
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
                    item = self._clean_structured_item(item)
                    resolved_item = dict(item)
                    resolved_item["name"] = self._preferred_candidate_name(item.get("name"), target_card.get("name"))
                    if not resolved_item.get("name") or looks_like_mojibake(resolved_item.get("name")):
                        resolved_item["name"] = self._infer_name_from_text(
                            detail.get("page_text"),
                            target_card.get("summary_text"),
                            merged_text,
                        )
                    resolved_item["education_level"] = self._preferred_text_field(
                        item.get("education_level"),
                        target_card.get("education_level") or extract_education_level(merged_text),
                        normalize_education=True,
                    )
                    resolved_item["current_company"] = self._preferred_text_field(item.get("current_company"), target_card.get("current_company"))
                    resolved_item["current_title"] = self._preferred_text_field(item.get("current_title"), target_card.get("current_title"))
                    if not resolved_item.get("current_title") or looks_like_mojibake(resolved_item.get("current_title")):
                        resolved_item["current_title"] = self._infer_title_from_text(
                            target_card.get("summary_text"),
                            merged_text,
                            detail.get("page_text"),
                        )
                    if not resolved_item.get("current_company") or looks_like_mojibake(resolved_item.get("current_company")):
                        resolved_item["current_company"] = self._infer_company_from_text(
                            resolved_item.get("current_title"),
                            target_card.get("summary_text"),
                            merged_text,
                            detail.get("page_text"),
                        )
                    resolved_item["location"] = self._preferred_text_field(item.get("location"), target_card.get("location"))
                    if not resolved_item.get("location") or looks_like_mojibake(resolved_item.get("location")):
                        resolved_item["location"] = self._infer_location_from_text(
                            target_card.get("summary_text"),
                            merged_text,
                            detail.get("page_text"),
                        )
                    resolved_item["last_active_time"] = self._preferred_text_field(item.get("last_active_time"), target_card.get("last_active_time"))
                    resolved_item["major"] = self._normalized_text(item.get("major"))
                    resolved_item["resume_summary"] = self._preferred_resume_summary(
                        item.get("resume_summary"),
                        detail.get("page_text"),
                        target_card.get("summary_text"),
                        merged_text,
                    )
                    resume_artifacts = self._safe_persist_resume_artifacts(
                        target_card.get("external_id") or f"candidate-{candidate_index}",
                        detail.get("page_text") or merged_text,
                        title=resolved_item.get("current_title") or target_card.get("current_title") or target_card.get("name"),
                        source_url=detail.get("detail_url") or target_card.get("detail_url"),
                        label=f"{job_id}_candidate_{candidate_index}",
                        content_html=detail.get("content_html"),
                        page_html=detail.get("page_html"),
                        resume_full_screenshot_path=resume_full_screenshot_path,
                    )
                    self._trace(
                        "recommend.candidate_artifacts",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        external_id=target_card.get("external_id"),
                        resume_markdown_path=resume_artifacts.get("resume_markdown_path"),
                        resume_full_screenshot_path=resume_artifacts.get("resume_full_screenshot_path"),
                        resume_downloaded=download_result.get("downloaded", False),
                        resume_path=download_result.get("resume_path"),
                        screenshot_base64_error=screenshot_base64_error,
                        resume_full_screenshot_error=resume_full_screenshot_error,
                        resume_fallback_export_error=download_result.get("fallback_export_error"),
                    )
                    years_experience = target_card.get("years_experience") or extract_years_experience(merged_text)
                    if item.get("years_experience"):
                        years_experience = item.get("years_experience")
                    education_level = resolved_item.get("education_level") or target_card.get("education_level") or extract_education_level(merged_text)
                    normalized_fields = self._build_score_fields(
                        item.get("normalized_fields") or build_fallback_normalized_fields(job_id, item),
                        item=resolved_item,
                        card=target_card,
                        detail=detail,
                        merged_text=merged_text,
                        years_experience=years_experience,
                        education_level=education_level,
                    )
                    pre_score = score_candidate(
                        job_id,
                        normalized_fields,
                    )
                    greet_info = self._try_auto_greet(
                        total_score=pre_score.total_score,
                        decision=pre_score.decision.value,
                        threshold=auto_greet_threshold,
                        enabled=auto_greet_enabled,
                        max_actions=auto_greet_max,
                        allow_non_recommend=auto_greet_allow_non_recommend,
                    )
                    self._trace(
                        "recommend.candidate_scored",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        external_id=target_card.get("external_id"),
                        score=pre_score.total_score,
                        decision=pre_score.decision.value,
                        auto_greet_clicked=bool(greet_info.get("auto_greet_clicked")),
                        auto_greet_reason=greet_info.get("auto_greet_reason"),
                    )
                    current_candidate = CandidateExtract(
                        external_id=target_card.get("external_id")
                        or _extract_external_id(detail.get("detail_url"), candidate_index, merged_text),
                        name=resolved_item.get("name"),
                        age=item.get("age") or extract_age(merged_text),
                        education_level=education_level,
                        major=resolved_item.get("major"),
                        years_experience=years_experience,
                        current_company=resolved_item.get("current_company") or target_card.get("current_company"),
                        current_title=resolved_item.get("current_title") or target_card.get("current_title"),
                        expected_salary=item.get("expected_salary") or extract_salary(merged_text),
                        location=resolved_item.get("location") or target_card.get("location"),
                        last_active_time=resolved_item.get("last_active_time") or target_card.get("last_active_time"),
                        raw_summary=resolved_item.get("resume_summary") or detail.get("page_text") or target_card.get("summary_text"),
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
                            **({"screenshot_error": resume_artifacts.get("screenshot_error")} if resume_artifacts.get("screenshot_error") else {}),
                            **({"screenshot_base64_error": screenshot_base64_error} if screenshot_base64_error else {}),
                            **resume_artifacts,
                            "resume_downloaded": download_result.get("downloaded", False),
                            "resume_path": download_result.get("resume_path"),
                            "resume_download_reason": download_result.get("reason"),
                            "resume_filename": download_result.get("suggested_filename"),
                            "resume_fallback_exported": download_result.get("fallback_exported", False),
                            "resume_fallback_export_error": download_result.get("fallback_export_error"),
                            "auto_greet_enabled": auto_greet_enabled,
                            "auto_greet_threshold": auto_greet_threshold,
                            "auto_greet_threshold_source": auto_greet_threshold_source,
                            "auto_greet_allow_non_recommend": auto_greet_allow_non_recommend,
                            "auto_greet_score": pre_score.total_score,
                            **greet_info,
                            "page_index": target_card.get("page_index"),
                            **item.get("evidence_map", {}),
                        },
                        screenshot_path=str(resume_artifacts.get("resume_full_screenshot_path") or resume_artifacts.get("screenshot_path") or ""),
                    )
                    candidates.append(current_candidate)
                    page_processed += 1
                    self._trace(
                        "recommend.candidate_compiled",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        external_id=current_candidate.external_id,
                        name=current_candidate.name,
                        gpt_extraction_used=bool(extracted),
                        gpt_extraction_error=extraction_error,
                        model_usage=extraction_usage,
                    )
                except Exception as exc:
                    self._trace(
                        "recommend.candidate_failed",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        external_id=target_card.get("external_id"),
                        name=target_card.get("name"),
                        error=str(exc),
                        current_url=self.runtime.current_url,
                    )
                    # Single card failures should not abort the whole task.
                    pass
                finally:
                    try:
                        close_result = self.runtime.close_recommend_detail(self.selectors)
                    except Exception:
                        close_result = False
                    self._trace(
                        "recommend.detail_closed",
                        page_index=page_index,
                        card_index=target_card.get("card_index"),
                        closed=bool(close_result),
                        current_url=self.runtime.current_url,
                    )
                    if current_candidate is not None:
                        current_candidate.evidence_map["recommend_detail_closed"] = bool(close_result)
                    if close_result:
                        wait_for_recommend_list_ready = getattr(self.runtime, "wait_for_recommend_list_ready", None)
                        if callable(wait_for_recommend_list_ready):
                            try:
                                wait_for_recommend_list_ready(self.selectors, timeout_ms=5000)
                            except Exception:
                                pass
                    else:
                        page_needs_recovery = True
                if page_needs_recovery:
                    break

            if len(candidates) >= max_candidates:
                break
            if page_needs_recovery:
                recovered = False
                recover_recommend_list = getattr(self.runtime, "recover_recommend_list", None)
                if callable(recover_recommend_list):
                    try:
                        recovered = bool(recover_recommend_list(self.selectors))
                    except Exception:
                        recovered = False
                self._trace(
                    "recommend.page_recover",
                    page_index=page_index,
                    recovered=recovered,
                    current_url=self.runtime.current_url,
                )
                if recovered:
                    continue
                if page_attempted == 0:
                    self._trace("recommend.page_stalled", page_index=page_index, current_url=self.runtime.current_url)
                break
            # Prevent infinite page turning when no usable cards are found.
            if page_attempted == 0:
                self._trace("recommend.page_stalled", page_index=page_index, current_url=self.runtime.current_url)
                break
            self._pause_for_human_browse(search_config, stage="page_turn")
            go_to_next_recommend_page = getattr(self.runtime, "go_to_next_recommend_page", None)
            if callable(go_to_next_recommend_page):
                has_next_page = bool(go_to_next_recommend_page(self.selectors))
            else:
                has_next_page = bool(self.runtime.go_to_next_page(self.selectors))
            self._trace(
                "recommend.page_turn",
                page_index=page_index,
                has_next_page=has_next_page,
                current_url=self.runtime.current_url,
            )
            if not has_next_page:
                break
            page_index += 1

        self._trace("recommend.collect_completed", candidate_count=len(candidates))
        return candidates

    def _recent_seen_external_ids(self, cards: list[dict[str, Any]], search_config: dict[str, Any]) -> set[str]:
        if not self._is_truthy(search_config.get("skip_existing_candidates"), default=False):
            return set()
        external_ids = []
        for card in cards:
            external_id = str(card.get("external_id") or "").strip()
            if not external_id:
                continue
            if re.fullmatch(r"playwright-\d+", external_id):
                continue
            external_ids.append(external_id)
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

    def _trace(self, event_type: str, **payload: Any) -> None:
        logger = self._trace_logger
        if not callable(logger):
            return
        try:
            logger(event_type, payload)
        except Exception:
            pass

    @staticmethod
    def _normalize_recommend_ready_info(ready_state: Any, *, current_url: str | None = None) -> dict[str, Any] | None:
        if isinstance(ready_state, dict):
            info = dict(ready_state)
        elif isinstance(ready_state, str):
            info = {"ready_selector": ready_state}
        elif ready_state:
            info = {"ready_selector": str(ready_state)}
        else:
            return None
        if current_url and not info.get("current_url"):
            info["current_url"] = current_url
        return info

    @staticmethod
    def _coerce_text_list(*values: Any) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for value in values:
            if isinstance(value, (list, tuple, set)):
                raw_items = value
            elif value in (None, ""):
                raw_items = []
            else:
                raw_items = [value]
            for raw_item in raw_items:
                text = PlaywrightLocalAgent._readable_text(raw_item)
                if not text:
                    continue
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                items.append(text)
        return items

    def _build_score_fields(
        self,
        normalized_fields: dict[str, Any],
        *,
        item: dict[str, Any],
        card: dict[str, Any],
        detail: dict[str, Any],
        merged_text: str,
        years_experience: Any,
        education_level: Any,
    ) -> dict[str, Any]:
        raw_summary = item.get("resume_summary") or detail.get("page_text") or merged_text
        clean_normalized_fields = self._clean_text_container(normalized_fields or {})
        base_fields = clean_normalized_fields if isinstance(clean_normalized_fields, dict) else {}
        return dict(base_fields) | {
            "name": item.get("name") or card.get("name"),
            "age": item.get("age") or card.get("age") or extract_age(merged_text),
            "education_level": education_level,
            "major": item.get("major"),
            "years_experience": years_experience,
            "current_company": item.get("current_company") or card.get("current_company"),
            "latest_company": item.get("current_company") or card.get("current_company"),
            "current_title": item.get("current_title") or card.get("current_title"),
            "latest_title": item.get("current_title") or card.get("current_title"),
            "expected_salary": item.get("expected_salary") or extract_salary(merged_text),
            "location": item.get("location") or card.get("location"),
            "city": item.get("location") or card.get("location"),
            "last_active_time": item.get("last_active_time") or card.get("last_active_time"),
            "skills": self._coerce_text_list(
                item.get("skills"),
                (normalized_fields or {}).get("skills"),
                item.get("project_keywords"),
            ),
            "industry_tags": self._coerce_text_list(
                item.get("industry_tags"),
                (normalized_fields or {}).get("industry_tags"),
            ),
            "project_keywords": self._coerce_text_list(
                item.get("project_keywords"),
                (normalized_fields or {}).get("project_keywords"),
            ),
            "raw_summary": raw_summary,
            "resume_summary": raw_summary,
            "summary": raw_summary,
            "page_text": detail.get("page_text") or merged_text,
        }

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
        if flow == "recommend":
            raise RuntimeError(
                "推荐牛人流程要求先在 9222 可附着的 Chrome 中手工登录 BOSS。"
                "当前仍停留在登录/扫码页，请先在 9222 Chrome 完成登录后再创建任务。"
            )
        wait_timeout_seconds = self._float_value(
            search_config.get("login_scan_wait_seconds"),
            fallback=self._float_env("SCREENING_LOGIN_SCAN_WAIT_SECONDS", default=15.0),
        )
        waiter = getattr(self.runtime, "wait_for_login_scan", None)
        if callable(waiter):
            cleared = bool(waiter(timeout_ms=max(1000, int(wait_timeout_seconds * 1000))))
            if cleared:
                return
        raise RuntimeError(f"BOSS {flow} page is waiting for QR scan login before continuing.")

    def _ensure_recommend_login_ready(self) -> None:
        checker = getattr(self.runtime, "is_login_scan_page", None)
        if not callable(checker):
            return
        try:
            needs_scan = bool(checker())
        except Exception:
            needs_scan = False
        if needs_scan:
            raise RuntimeError(
                "推荐牛人流程要求先在 9222 可附着的 Chrome 中手工登录 BOSS。"
                "当前仍停留在登录/扫码页，请先在 9222 Chrome 完成登录后再创建任务。"
            )

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

    def _resolve_auto_greet_threshold(
        self,
        job_id: str,
        search_config: dict[str, Any],
    ) -> tuple[float, str]:
        config_threshold = self._float_value(search_config.get("auto_greet_threshold"), fallback=-1.0)
        if config_threshold >= 0:
            return config_threshold, "search_config"

        env_threshold = os.getenv("SCREENING_AUTO_GREET_THRESHOLD")
        if env_threshold not in (None, ""):
            return self._float_value(env_threshold, fallback=90.0), "env"

        row = get_jd_scorecard(job_id)
        if row and isinstance(row.get("scorecard"), dict):
            threshold = self._threshold_from_scorecard(row["scorecard"])
            if threshold is not None:
                return threshold, "scorecard.recommend_min"

        builtin_scorecard = SCORECARDS.get(job_id)
        if isinstance(builtin_scorecard, dict):
            threshold = self._threshold_from_scorecard(builtin_scorecard)
            if threshold is not None:
                return threshold, "builtin.recommend_min"

        return 90.0, "default"

    @staticmethod
    def _threshold_from_scorecard(scorecard: dict[str, Any]) -> float | None:
        thresholds = scorecard.get("thresholds")
        if not isinstance(thresholds, dict):
            return None
        value = thresholds.get("recommend_min")
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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

    def _safe_persist_resume_full_screenshot(self, external_id: str) -> tuple[str | None, str | None]:
        try:
            return self.runtime.persist_resume_full_screenshot(external_id), None
        except Exception as exc:
            return None, str(exc)

    def _safe_persist_resume_markdown(
        self,
        external_id: str,
        content: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        content_html: str | None = None,
        page_html: str | None = None,
        screenshot_path: str | None = None,
    ) -> tuple[str | None, str | None]:
        try:
            return (
                self.runtime.persist_resume_markdown(
                    external_id,
                    content,
                    title=title,
                    source_url=source_url,
                    content_html=content_html,
                    page_html=page_html,
                    screenshot_path=screenshot_path,
                ),
                None,
            )
        except Exception as exc:
            return None, str(exc)

    def _safe_persist_resume_artifacts(
        self,
        external_id: str,
        content: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        label: str | None = None,
        content_html: str | None = None,
        page_html: str | None = None,
        resume_full_screenshot_path: str | None = None,
    ) -> dict[str, Any]:
        resume_full_screenshot_error = None
        if resume_full_screenshot_path is None:
            resume_full_screenshot_path, resume_full_screenshot_error = self._safe_persist_resume_full_screenshot(external_id)
        resume_markdown_path, resume_markdown_error = self._safe_persist_resume_markdown(
            external_id,
            content,
            title=title,
            source_url=source_url,
            content_html=content_html,
            page_html=page_html,
            screenshot_path=resume_full_screenshot_path,
        )
        return {
            "resume_full_screenshot_path": resume_full_screenshot_path,
            "resume_full_screenshot_error": resume_full_screenshot_error,
            "resume_full_screenshot_fallback_used": False,
            "resume_markdown_path": resume_markdown_path,
            "resume_markdown_filename": Path(resume_markdown_path).name if resume_markdown_path else None,
            "resume_markdown_error": resume_markdown_error,
            "screenshot_path": resume_full_screenshot_path,
            "screenshot_error": resume_full_screenshot_error,
        }

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
