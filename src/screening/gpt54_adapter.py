from __future__ import annotations

import json
import os
import uuid
from typing import Any, Protocol

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from .browser_runtime import PlaywrightBrowserRuntime
from .candidate_heuristics import build_fallback_normalized_fields
from .config import load_local_env
from .models import CandidateExtract
from .prompts import FIELD_EXTRACTION_PROMPT, SYSTEM_PROMPT
from .scorecards import MOCK_CANDIDATES, SCORECARDS
from .scoring_targets import get_scoring_target


class BrowserAgent(Protocol):
    def start_session(self) -> str: ...

    def collect_candidates(
        self,
        job_id: str,
        max_candidates: int,
        *,
        search_mode: str | None = None,
        search_config: dict[str, Any] | None = None,
        sort_by: str | None = None,
        max_pages: int = 1,
    ) -> list[CandidateExtract]: ...

    def stop_session(self) -> None: ...


class MockBrowserAgent:
    def start_session(self) -> str:
        return f"mock-session-{uuid.uuid4()}"

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
        items = []
        for raw in MOCK_CANDIDATES.get(job_id, [])[:max_candidates]:
            items.append(CandidateExtract(**raw, screenshot_path=f"/tmp/{raw['external_id']}.png"))
        return items

    def stop_session(self) -> None:
        return


class OpenAIComputerAgent:
    def __init__(
        self,
        model: str | None = None,
        extraction_model: str | None = None,
        *,
        client: Any | None = None,
        runtime: PlaywrightBrowserRuntime | None = None,
    ) -> None:
        load_local_env()
        self.model = model or os.getenv("SCREENING_COMPUTER_MODEL", "computer-use-preview")
        self.extraction_model = extraction_model or os.getenv("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
        self.client = client
        self.runtime = runtime or PlaywrightBrowserRuntime()
        self.session_id: str | None = None
        self._last_response_id: str | None = None

        if self.client is None and OpenAI is not None and os.getenv("OPENAI_API_KEY"):
            self.client = OpenAI()

    def start_session(self) -> str:
        self.session_id = self.runtime.start()
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
        self._ensure_ready()
        instruction = self._build_navigation_instruction(job_id, max_candidates)
        response = self.client.responses.create(
            model=self.model,
            tools=[self._tool_spec()],
            instructions=SYSTEM_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": instruction},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{self.runtime.screenshot_base64()}",
                        },
                    ],
                }
            ],
            reasoning={"summary": "concise"},
            truncation="auto",
        )
        self._last_response_id = getattr(response, "id", None)
        final_response = self._computer_loop(response)
        return self._parse_candidates(job_id, self._response_text(final_response))

    def extract_fields_from_current_page(self, page_text: str = "") -> dict[str, Any]:
        self._ensure_ready()
        response = self.client.responses.create(
            model=self.extraction_model,
            instructions=FIELD_EXTRACTION_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": page_text or "Extract visible fields from the current candidate page."},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{self.runtime.screenshot_base64()}",
                        },
                    ],
                }
            ],
            text={"format": {"type": "json_object"}},
            truncation="auto",
        )
        text = self._response_text(response)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Extraction model did not return valid JSON: {text}") from exc

    def _ensure_ready(self) -> None:
        if self.client is None:
            raise RuntimeError("OpenAI client is not configured. Install the openai package and set OPENAI_API_KEY.")
        if self.session_id is None:
            raise RuntimeError("Browser session is not started. Call start_session() first.")

    def _tool_spec(self) -> dict[str, Any]:
        return {
            "type": "computer_use_preview",
            "display_width": self.runtime.width,
            "display_height": self.runtime.height,
            "environment": "browser",
        }

    def _build_navigation_instruction(self, job_id: str, max_candidates: int) -> str:
        target = get_scoring_target(job_id)
        role_name = str((target or {}).get("name") or SCORECARDS[job_id]["name"])
        return (
            f"You are screening resumes for the role '{role_name}'. "
            f"Inspect up to {max_candidates} candidates in the current BOSS browser session. "
            "Assume the user is already logged in. "
            "Navigate the BOSS workflow, configure the search page for this role, and inspect candidate detail pages. "
            "Do not click any button that sends messages, downloads files, submits forms, or exchanges contact information. "
            "If a captcha, safety check, login expiry, or anti-bot page appears, return only JSON: "
            '{"blocked": true, "reason": "...", "candidates": []}. '
            "Otherwise return only JSON with keys blocked, reason, candidates. "
            "Each candidate object must contain: "
            "external_id, name, age, education_level, major, years_experience, current_company, current_title, "
            "expected_salary, location, last_active_time, skills, industry_tags, certificates, project_keywords, "
            "resume_summary, evidence_map."
        )

    def _computer_loop(self, response: Any) -> Any:
        while True:
            computer_calls = [item for item in self._response_items(response) if self._item_type(item) == "computer_call"]
            if not computer_calls:
                return response

            call = computer_calls[0]
            plain_call = self._plain(call)
            pending_safety_checks = plain_call.get("pending_safety_checks", [])
            if pending_safety_checks:
                raise RuntimeError(f"Pending safety checks returned by OpenAI: {pending_safety_checks}")

            self.runtime.execute(plain_call["action"])
            response = self.client.responses.create(
                model=self.model,
                previous_response_id=getattr(response, "id", self._last_response_id),
                tools=[self._tool_spec()],
                input=[
                    {
                        "type": "computer_call_output",
                        "call_id": plain_call["call_id"],
                        "output": {
                            "type": "computer_screenshot",
                            "image_url": f"data:image/png;base64,{self.runtime.screenshot_base64()}",
                        },
                        "current_url": self.runtime.current_url,
                    }
                ],
                truncation="auto",
            )
            self._last_response_id = getattr(response, "id", self._last_response_id)

    def _parse_candidates(self, job_id: str, payload_text: str) -> list[CandidateExtract]:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI computer-use response was not valid JSON: {payload_text}") from exc

        if isinstance(payload, list):
            payload = {"blocked": False, "reason": None, "candidates": payload}

        if payload.get("blocked"):
            raise RuntimeError(f"OpenAI computer-use flow blocked: {payload.get('reason', 'unknown reason')}")

        candidates: list[CandidateExtract] = []
        for index, item in enumerate(payload.get("candidates", []), start=1):
            screenshot_path = self.runtime.persist_screenshot(f"{job_id}_candidate_{index}")
            candidates.append(
                CandidateExtract(
                    external_id=item.get("external_id", f"openai-{index}"),
                    name=item.get("name"),
                    age=item.get("age"),
                    education_level=item.get("education_level"),
                    major=item.get("major"),
                    years_experience=item.get("years_experience"),
                    current_company=item.get("current_company"),
                    current_title=item.get("current_title"),
                    expected_salary=item.get("expected_salary"),
                    location=item.get("location"),
                    last_active_time=item.get("last_active_time"),
                    raw_summary=item.get("resume_summary"),
                    normalized_fields=item.get("normalized_fields") or build_fallback_normalized_fields(job_id, item),
                    evidence_map=item.get("evidence_map", {}),
                    screenshot_path=screenshot_path,
                )
            )
        return candidates

    def runtime_config(self) -> dict[str, str]:
        return {
            "computer_model": self.model,
            "extraction_model": self.extraction_model,
        }

    @staticmethod
    def _plain(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return {
            key: getattr(item, key)
            for key in dir(item)
            if not key.startswith("_") and not callable(getattr(item, key))
        }

    def _response_items(self, response: Any) -> list[Any]:
        if isinstance(response, dict):
            return response.get("output", [])
        return getattr(response, "output", [])

    def _item_type(self, item: Any) -> str | None:
        if isinstance(item, dict):
            return item.get("type")
        return getattr(item, "type", None)

    def _response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text
        if isinstance(response, dict) and response.get("output_text"):
            return response["output_text"]

        chunks: list[str] = []
        for item in self._response_items(response):
            if self._item_type(item) != "message":
                continue
            plain_item = self._plain(item)
            for content in plain_item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text", ""))
        return "\n".join(chunk for chunk in chunks if chunk).strip()


def build_extraction_request_payload(screenshot_b64: str, page_text: str = "") -> dict[str, Any]:
    return {
        "instructions": FIELD_EXTRACTION_PROMPT,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": page_text or "Extract fields from the screenshot only."},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{screenshot_b64}"},
                ],
            }
        ],
    }
