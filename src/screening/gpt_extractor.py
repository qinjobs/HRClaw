from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from .candidate_heuristics import build_fallback_normalized_fields, has_qa_testing_evidence
from .config import load_local_env
from .prompts import FIELD_EXTRACTION_PROMPT, build_local_extraction_prompt


EXTRACTION_KEYS = {
    "name",
    "age",
    "education_level",
    "major",
    "years_experience",
    "current_company",
    "current_title",
    "expected_salary",
    "location",
    "last_active_time",
    "skills",
    "industry_tags",
    "certificates",
    "project_keywords",
    "resume_summary",
    "evidence_map",
    "normalized_fields",
}
LIST_FIELDS = {"skills", "industry_tags", "certificates", "project_keywords"}
SCALAR_FIELDS = {
    "name",
    "age",
    "education_level",
    "major",
    "years_experience",
    "current_company",
    "current_title",
    "expected_salary",
    "location",
    "last_active_time",
    "resume_summary",
}


def summarize_model_error(detail: Any) -> str:
    if isinstance(detail, BaseException):
        text = str(detail)
    elif isinstance(detail, dict):
        try:
            text = json.dumps(detail, ensure_ascii=False)
        except Exception:
            text = str(detail)
    else:
        text = str(detail or "")
    normalized = text.strip()
    lower = normalized.lower()
    if normalized.startswith("模型提取已回退："):
        return normalized
    if (
        "invalid_authentication_error" in lower
        or "error code: 401" in lower
        or ("api key" in lower and ("invalid" in lower or "expired" in lower))
    ):
        return "模型提取已回退：Kimi API Key 无效或已过期"
    if "insufficient_quota" in lower or ("quota" in lower and "insufficient" in lower):
        return "模型提取已回退：Kimi 额度不足"
    if "rate_limit" in lower or "error code: 429" in lower:
        return "模型提取已回退：Kimi 请求过多，请稍后重试"
    if "timed out" in lower or "timeout" in lower:
        return "模型提取已回退：Kimi 响应超时"
    if (
        "no json payload" in lower
        or "valid json" in lower
        or "json object" in lower
        or "unsupported keys" in lower
    ):
        return "模型提取已回退：模型返回格式异常"
    return "模型提取已回退：模型服务暂时不可用"


class GPTFieldExtractor:
    def __init__(
        self,
        model: str | None = None,
        *,
        client: Any | None = None,
        cli_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        load_local_env()
        self.provider = os.getenv("SCREENING_EXTRACTION_PROVIDER", "kimi_cli").strip().lower() or "kimi_cli"
        self.model = model or os.getenv("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
        self.base_url = os.getenv("SCREENING_LLM_BASE_URL", "").strip()
        self.api_key = os.getenv("SCREENING_LLM_API_KEY", "").strip()
        self._enabled = os.getenv("SCREENING_ENABLE_MODEL_EXTRACTION", os.getenv("SCREENING_ENABLE_GPT_EXTRACTION", "auto")).lower()
        self.max_retries = max(0, int(os.getenv("SCREENING_EXTRACTION_RETRIES", "1")))
        self.retry_delay_ms = max(0, int(os.getenv("SCREENING_EXTRACTION_RETRY_DELAY_MS", "400")))
        default_kimi_args = "--print --output-format text --final-message-only" if self.provider == "kimi_cli" else ""
        self.cli_timeout_seconds = max(5, int(os.getenv("SCREENING_KIMI_CLI_TIMEOUT_SECONDS", "180")))
        self.kimi_cli_command = os.getenv("SCREENING_KIMI_CLI_COMMAND", "kimi").strip()
        self.kimi_cli_args = os.getenv("SCREENING_KIMI_CLI_ARGS", default_kimi_args).strip()
        self.kimi_cli_prompt_arg_template = os.getenv(
            "SCREENING_KIMI_CLI_PROMPT_ARG_TEMPLATE",
            "{prompt}" if self.provider == "kimi_cli" else "",
        ).strip()
        default_send_exit = "false" if self.provider == "kimi_cli" else "true"
        self.kimi_cli_send_exit = os.getenv("SCREENING_KIMI_CLI_SEND_EXIT", default_send_exit).strip().lower() not in {
            "0",
            "false",
            "off",
            "no",
        }
        self.kimi_cli_config = os.getenv("SCREENING_KIMI_CLI_CONFIG", "").strip()
        self.kimi_cli_api_key = os.getenv("SCREENING_KIMI_CLI_API_KEY", "").strip()
        self.kimi_cli_base_url = os.getenv("SCREENING_KIMI_CLI_BASE_URL", "https://api.kimi.com/coding/v1").strip()
        self.last_usage: dict[str, Any] | None = None
        self.client = client
        self._cli_runner = cli_runner or subprocess.run
        if self.provider == "kimi_cli":
            self.model = model or os.getenv("SCREENING_EXTRACTION_MODEL", "kimi-for-coding")
            self.client = None
        elif self.client is None and OpenAI is not None and self.api_key:
            client_kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self.client = OpenAI(**client_kwargs)

    @property
    def enabled(self) -> bool:
        if self._enabled in {"0", "false", "off", "no"}:
            return False
        if self.provider == "kimi_cli":
            if self._cli_runner is not subprocess.run:
                return True
            command_tokens = self._kimi_cli_command_tokens()
            if not command_tokens:
                return False
            command = command_tokens[0]
            if command == "kimi":
                return shutil.which("kimi") is not None
            if Path(command).exists():
                return True
            return shutil.which(command) is not None
        return self.client is not None

    def extract_candidate(self, job_id: str, page_text: str, screenshot_base64: str | None = None) -> dict[str, Any]:
        self.last_usage = None
        if not self.enabled:
            return {}
        try:
            if self.provider == "kimi_cli":
                return self._extract_with_kimi_cli(job_id, page_text)
            return self._extract_with_chat_completions(job_id, page_text)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(summarize_model_error(exc)) from exc

    def _extract_with_chat_completions(self, job_id: str, page_text: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": FIELD_EXTRACTION_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": build_local_extraction_prompt(job_id, page_text),
                        },
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                self.last_usage = self._chat_usage(response)
                return self._validate_payload_text(self._chat_response_text(response))
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay_ms / 1000)
        raise RuntimeError(self._normalize_provider_error(last_error)) from last_error

    def _extract_with_kimi_cli(self, job_id: str, page_text: str) -> dict[str, Any]:
        command = self._kimi_cli_command_tokens()
        if not command:
            raise RuntimeError("SCREENING_KIMI_CLI_COMMAND is empty.")
        if self.model and "--model" not in command and "-m" not in command:
            command.extend(["--model", self.model])
        effective_config = self._effective_kimi_cli_config()
        if effective_config:
            command.extend(["--config", effective_config])

        system_prompt = FIELD_EXTRACTION_PROMPT
        user_prompt = build_local_extraction_prompt(job_id, page_text)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        stdin_input = None
        if self.kimi_cli_prompt_arg_template:
            if "--prompt" not in command and "-p" not in command and "--command" not in command and "-c" not in command:
                command.append("--prompt")
            command.append(self.kimi_cli_prompt_arg_template.format(prompt=full_prompt, job_id=job_id))
        else:
            stdin_input = full_prompt
            if self.kimi_cli_send_exit:
                stdin_input += "\n/exit\n"
            else:
                stdin_input += "\n"

        completed = self._cli_runner(
            command,
            input=stdin_input,
            text=True,
            capture_output=True,
            timeout=self.cli_timeout_seconds,
            env={**os.environ, "NO_COLOR": "1"},
        )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0 and not stdout:
            detail = stderr or "no stderr output"
            raise RuntimeError(self._normalize_provider_error(detail))

        payload = self._parse_kimi_cli_payload(stdout)
        if payload is None:
            detail = stderr or stdout[:500] or "empty output"
            raise RuntimeError(self._normalize_provider_error(detail))

        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            raise RuntimeError(self._normalize_provider_error(payload["error"]))

        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            self.last_usage = self._normalize_usage(usage)
        else:
            self.last_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model": self.model,
                "provider": "kimi_cli",
            }

        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        elif isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            payload = payload["data"]

        return self._validate_payload_obj(payload)

    def merge_with_fallback(self, job_id: str, extracted: dict[str, Any], fallback_item: dict[str, Any]) -> dict[str, Any]:
        merged = dict(extracted or {})
        merged.setdefault("skills", fallback_item.get("skills", []))
        merged.setdefault("industry_tags", fallback_item.get("industry_tags", []))
        merged.setdefault("project_keywords", fallback_item.get("project_keywords", []))
        merged.setdefault("resume_summary", fallback_item.get("resume_summary"))
        merged["normalized_fields"] = merged.get("normalized_fields") or build_fallback_normalized_fields(job_id, merged)
        if job_id == "qa_test_engineer_v1":
            normalized_fields = dict(merged.get("normalized_fields") or {})
            normalized_fields["testing_evidence"] = has_qa_testing_evidence(merged.get("resume_summary"))
            merged["normalized_fields"] = normalized_fields
        merged["evidence_map"] = merged.get("evidence_map") or {}
        return merged

    @staticmethod
    def _validate_payload_text(payload_text: str) -> dict[str, Any]:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GPT extraction did not return valid JSON: {payload_text}") from exc
        return GPTFieldExtractor._validate_payload_obj(payload)

    @staticmethod
    def _validate_payload_obj(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeError(f"GPT extraction must return a JSON object: {payload!r}")

        unknown = sorted(set(payload) - EXTRACTION_KEYS)
        if unknown:
            raise RuntimeError(f"GPT extraction returned unsupported keys: {', '.join(unknown)}")

        for scalar_key in SCALAR_FIELDS:
            payload.setdefault(scalar_key, None)

        for list_key in LIST_FIELDS:
            value = payload.get(list_key)
            if value is None:
                payload[list_key] = []
            elif not isinstance(value, list):
                raise RuntimeError(f"GPT extraction field '{list_key}' must be a list.")

        evidence_map = payload.get("evidence_map")
        if evidence_map is None:
            payload["evidence_map"] = {}
        elif not isinstance(evidence_map, dict):
            raise RuntimeError("GPT extraction field 'evidence_map' must be an object.")

        normalized_fields = payload.get("normalized_fields")
        if normalized_fields is not None and not isinstance(normalized_fields, dict):
            raise RuntimeError("GPT extraction field 'normalized_fields' must be an object.")
        if normalized_fields is None:
            payload["normalized_fields"] = {}

        return payload

    def _kimi_cli_command_tokens(self) -> list[str]:
        command = shlex.split(self.kimi_cli_command) if self.kimi_cli_command else []
        command.extend(shlex.split(self.kimi_cli_args) if self.kimi_cli_args else [])
        return command

    @staticmethod
    def _normalize_provider_error(detail: Any) -> str:
        return summarize_model_error(detail)

    def _effective_kimi_cli_config(self) -> str:
        # Prefer explicit config, but normalize legacy short forms to avoid
        # runtime failures like "LLM not set" on newer Kimi CLI versions.
        if self.kimi_cli_config:
            normalized = self._normalize_kimi_cli_config(self.kimi_cli_config)
            if normalized:
                return normalized
        if not self.kimi_cli_api_key:
            return ""
        return self._build_kimi_cli_config(self.kimi_cli_api_key, self.kimi_cli_base_url, self.model)

    def _normalize_kimi_cli_config(self, raw_config: str) -> str:
        text = (raw_config or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Keep raw config for non-JSON formats (e.g. TOML) provided by user.
            return text

        if not isinstance(parsed, dict):
            return text

        # Already complete.
        if (
            isinstance(parsed.get("providers"), dict)
            and isinstance(parsed.get("models"), dict)
            and parsed.get("default_model")
        ):
            return json.dumps(parsed, ensure_ascii=False)

        # Legacy short config:
        # {"provider":{"name":"kimi-code","api_key":"sk-...","base_url":"..."}}
        provider_obj = parsed.get("provider")
        if isinstance(provider_obj, dict):
            api_key = str(provider_obj.get("api_key") or "").strip()
            if api_key:
                base_url = str(provider_obj.get("base_url") or self.kimi_cli_base_url or "").strip()
                return self._build_kimi_cli_config(api_key, base_url, self.model)

        # Partial providers config: try to extract any api_key and auto-complete.
        providers = parsed.get("providers")
        if isinstance(providers, dict):
            for _, provider in providers.items():
                if isinstance(provider, dict):
                    api_key = str(provider.get("api_key") or "").strip()
                    if api_key:
                        base_url = str(provider.get("base_url") or self.kimi_cli_base_url or "").strip()
                        return self._build_kimi_cli_config(api_key, base_url, self.model)

        # Fallback to api key in env if available.
        if self.kimi_cli_api_key:
            return self._build_kimi_cli_config(self.kimi_cli_api_key, self.kimi_cli_base_url, self.model)

        return text

    @staticmethod
    def _build_kimi_cli_config(api_key: str, base_url: str | None, model_name: str | None) -> str:
        provider_name = "kimi-for-coding"
        effective_model = model_name or "kimi-for-coding"
        payload = {
            "default_model": effective_model,
            "providers": {
                provider_name: {
                    "type": "kimi",
                    "base_url": (base_url or "https://api.kimi.com/coding/v1"),
                    "api_key": api_key,
                }
            },
            "models": {
                effective_model: {
                    "provider": provider_name,
                    "model": effective_model,
                    "max_context_size": 262144,
                }
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _parse_kimi_cli_payload(output: str) -> dict[str, Any] | None:
        text = (output or "").strip()
        if not text:
            return None
        parsed = GPTFieldExtractor._decode_json_from_text(text)
        if isinstance(parsed, dict):
            return parsed
        return None

    @staticmethod
    def _decode_json_from_text(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        if "```" in text:
            for block in text.split("```"):
                candidate = block.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

        decoder = json.JSONDecoder()
        best_candidate = None
        best_score = -1
        for index, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            score = len(set(obj.keys()) & EXTRACTION_KEYS)
            if score > best_score:
                best_score = score
                best_candidate = obj
                if score >= 4:
                    break
        return best_candidate

    @staticmethod
    def _normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
        def pick_int(name: str) -> int:
            value = usage.get(name)
            try:
                return int(value) if value is not None else 0
            except Exception:
                return 0

        prompt_tokens = pick_int("prompt_tokens")
        completion_tokens = pick_int("completion_tokens")
        total_tokens = pick_int("total_tokens")
        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "model": usage.get("model"),
            "provider": usage.get("provider", "kimi_cli"),
        }

    @staticmethod
    def _chat_response_text(response: Any) -> str:
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices", [])
        if not choices:
            return ""
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message", {})
        content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    chunks.append(str(item.get("text") or ""))
            return "".join(chunks).strip()
        return str(content or "").strip()

    @staticmethod
    def _chat_usage(response: Any) -> dict[str, Any] | None:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return None

        def pick_int(name: str) -> int:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            try:
                return int(value) if value is not None else 0
            except Exception:
                return 0

        prompt_tokens = pick_int("prompt_tokens")
        completion_tokens = pick_int("completion_tokens")
        total_tokens = pick_int("total_tokens")
        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "model": getattr(response, "model", None) if not isinstance(response, dict) else response.get("model"),
        }
