from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from .candidate_heuristics import (
    build_fallback_normalized_fields,
    has_qa_testing_evidence,
    normalize_education_level,
    repair_text_mojibake,
)
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
    if (
        "llm not set" in lower
        or "provider not found" in lower
        or "default model" in lower and "not set" in lower
        or "config file" in lower and "not found" in lower
        or "api key" in lower and "not set" in lower
    ):
        return "模型提取已回退：Kimi CLI 未配置模型或 API Key"
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
        self.log_model_payloads = os.getenv("SCREENING_LOG_MODEL_PAYLOADS", "false").strip().lower() not in {
            "0",
            "false",
            "off",
            "no",
        }
        self.log_model_payload_max_chars = max(0, int(os.getenv("SCREENING_LOG_MODEL_PAYLOAD_MAX_CHARS", "40000")))
        self.file_log_path = self._resolve_file_log_path(os.getenv("SCREENING_GPT_EXTRACTOR_LOG_PATH", "").strip())
        self.last_usage: dict[str, Any] | None = None
        self._event_logger = None
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
            return bool(command and (Path(command).exists() or shutil.which(command) is not None))
        return self.client is not None

    def set_event_logger(self, logger) -> None:
        self._event_logger = logger

    def extract_candidate(self, job_id: str, page_text: str, screenshot_base64: str | None = None) -> dict[str, Any]:
        self.last_usage = None
        self._emit_event(
            "model.extract.start",
            job_id=job_id,
            provider=self.provider,
            model=self.model,
            enabled=self.enabled,
            **self._text_log_payload("page_text", page_text),
        )
        if not self.enabled:
            self._emit_event(
                "model.extract.skipped",
                job_id=job_id,
                provider=self.provider,
                model=self.model,
                reason="extractor_disabled",
            )
            return {}
        try:
            if self.provider == "kimi_cli":
                result = self._extract_with_kimi_cli(job_id, page_text)
            else:
                result = self._extract_with_chat_completions(job_id, page_text)
            self._emit_event(
                "model.extract.completed",
                job_id=job_id,
                provider=self.provider,
                model=self.model,
                extracted_keys=sorted(result.keys()),
                usage=self.last_usage or {},
            )
            return result
        except RuntimeError as exc:
            self._emit_event(
                "model.extract.failed",
                job_id=job_id,
                provider=self.provider,
                model=self.model,
                error=str(exc),
            )
            raise
        except Exception as exc:
            normalized_error = summarize_model_error(exc)
            self._emit_event(
                "model.extract.failed",
                job_id=job_id,
                provider=self.provider,
                model=self.model,
                error=normalized_error,
            )
            raise RuntimeError(normalized_error) from exc

    def _extract_with_chat_completions(self, job_id: str, page_text: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                request_payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": FIELD_EXTRACTION_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": build_local_extraction_prompt(job_id, page_text),
                        },
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }
                self._emit_event(
                    "model.extract.request",
                    job_id=job_id,
                    provider=self.provider,
                    model=self.model,
                    transport="chat_completions",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    **self._json_log_payload("request_body", request_payload),
                )
                response = self.client.chat.completions.create(**request_payload)
                response_text = self._chat_response_text(response)
                self.last_usage = self._chat_usage(response)
                self._emit_event(
                    "model.extract.response",
                    job_id=job_id,
                    provider=self.provider,
                    model=self.model,
                    transport="chat_completions",
                    attempt=attempt + 1,
                    usage=self.last_usage or {},
                    **self._text_log_payload("response_text", response_text),
                )
                return self._validate_payload_text(response_text)
            except Exception as exc:
                last_error = exc
                self._emit_event(
                    "model.extract.attempt_failed",
                    job_id=job_id,
                    provider=self.provider,
                    model=self.model,
                    transport="chat_completions",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retrying=attempt < self.max_retries,
                    error=self._normalize_provider_error(exc),
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay_ms / 1000)
        raise RuntimeError(self._normalize_provider_error(last_error)) from last_error

    def _extract_with_kimi_cli(self, job_id: str, page_text: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                command = self._kimi_cli_command_tokens()
                if not command:
                    raise RuntimeError("SCREENING_KIMI_CLI_COMMAND is empty.")
                effective_config = self._effective_kimi_cli_config()
                effective_model = self._effective_kimi_cli_model(effective_config)
                if effective_model and "--model" not in command and "-m" not in command:
                    command.extend(["--model", effective_model])
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

                self._emit_event(
                    "model.extract.request",
                    job_id=job_id,
                    provider=self.provider,
                    model=effective_model or self.model,
                    transport="kimi_cli",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    request_channel="stdin" if stdin_input is not None else "argv",
                    command=self._redact_cli_command(command),
                    **self._text_log_payload("request_prompt", full_prompt),
                )
                completed = self._cli_runner(
                    command,
                    input=stdin_input,
                    text=True,
                    capture_output=True,
                    timeout=self.cli_timeout_seconds,
                    encoding="utf-8",
                    errors="replace",
                    env={**os.environ, "NO_COLOR": "1"},
                )

                stdout = (completed.stdout or "").strip()
                stderr = (completed.stderr or "").strip()
                self._emit_event(
                    "model.extract.response",
                    job_id=job_id,
                    provider=self.provider,
                    model=effective_model or self.model,
                    transport="kimi_cli",
                    attempt=attempt + 1,
                    returncode=completed.returncode,
                    **self._text_log_payload("stdout_text", stdout),
                    **self._text_log_payload("stderr_text", stderr),
                )
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
            except Exception as exc:
                last_error = exc
                self._emit_event(
                    "model.extract.attempt_failed",
                    job_id=job_id,
                    provider=self.provider,
                    model=self.model,
                    transport="kimi_cli",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retrying=attempt < self.max_retries,
                    error=self._normalize_provider_error(exc),
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay_ms / 1000)
        raise RuntimeError(self._normalize_provider_error(last_error)) from last_error

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

        for scalar_key in (
            "name",
            "education_level",
            "major",
            "current_company",
            "current_title",
            "expected_salary",
            "location",
            "last_active_time",
        ):
            payload[scalar_key] = GPTFieldExtractor._sanitize_scalar_field(scalar_key, payload.get(scalar_key))

        return payload

    @staticmethod
    def _sanitize_scalar_field(field_name: str, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        if field_name == "education_level":
            normalized = normalize_education_level(text)
            if normalized:
                return normalized
        repaired = repair_text_mojibake(text)
        repaired_text = str(repaired or "").strip()
        return repaired_text or text

    def _kimi_cli_command_tokens(self) -> list[str]:
        command = shlex.split(self.kimi_cli_command) if self.kimi_cli_command else []
        if command:
            resolved = self._resolve_kimi_cli_executable(command[0])
            if resolved:
                command[0] = resolved
        command.extend(shlex.split(self.kimi_cli_args) if self.kimi_cli_args else [])
        return command

    @staticmethod
    def _resolve_kimi_cli_executable(command: str) -> str:
        raw = str(command or "").strip()
        if not raw:
            return ""
        if Path(raw).exists():
            return raw

        resolved = shutil.which(raw)
        if resolved:
            return resolved

        if raw != "kimi":
            return raw

        candidates = [
            Path.home() / ".local" / "bin" / "kimi",
            Path.home() / ".cargo" / "bin" / "kimi",
            Path.home() / ".npm-global" / "bin" / "kimi",
            Path("/opt/homebrew/bin/kimi"),
            Path("/usr/local/bin/kimi"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return raw

    @staticmethod
    def _normalize_provider_error(detail: Any) -> str:
        return summarize_model_error(detail)

    def _emit_event(self, event_type: str, **payload: Any) -> None:
        self._append_file_event(event_type, payload)
        logger = self._event_logger
        if not callable(logger):
            return
        try:
            logger(event_type, payload)
        except Exception:
            pass

    @staticmethod
    def _resolve_file_log_path(raw_path: str) -> Path:
        if raw_path:
            return Path(raw_path).expanduser()
        return Path(__file__).resolve().parents[2] / "data" / "logs" / "gpt_extractor.log"

    def _append_file_event(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self.file_log_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "payload": payload,
            }
            with self.file_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str))
                handle.write("\n")
        except Exception:
            pass

    def _json_log_payload(self, field_name: str, value: Any) -> dict[str, Any]:
        return self._text_log_payload(field_name, self._safe_json_dumps(value))

    def _text_log_payload(self, field_name: str, value: Any) -> dict[str, Any]:
        text = str(value or "")
        payload = {
            f"{field_name}_chars": len(text),
            f"{field_name}_sha1": hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest(),
        }
        if self.log_model_payloads:
            truncated = False
            if self.log_model_payload_max_chars and len(text) > self.log_model_payload_max_chars:
                text = text[: self.log_model_payload_max_chars]
                truncated = True
            payload[field_name] = text
            if truncated:
                payload[f"{field_name}_truncated"] = True
        return payload

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _redact_cli_command(command: list[str]) -> list[str]:
        if not command:
            return []
        redacted: list[str] = []
        redact_next = False
        for token in command:
            text = str(token or "")
            if redact_next:
                redacted.append("<redacted>")
                redact_next = False
                continue
            if text in {"--config", "--prompt", "-p", "--command", "-c"}:
                redacted.append(text)
                redact_next = True
                continue
            if text.startswith("--config="):
                redacted.append("--config=<redacted>")
                continue
            redacted.append(text)
        return redacted

    def _effective_kimi_cli_config(self) -> str:
        # Prefer explicit config, but normalize legacy short forms to avoid
        # runtime failures like "LLM not set" on newer Kimi CLI versions.
        if self.kimi_cli_config:
            normalized = self._normalize_kimi_cli_config(self.kimi_cli_config)
            if normalized:
                return normalized
        if self.kimi_cli_api_key:
            return self._build_kimi_cli_config(self.kimi_cli_api_key, self.kimi_cli_base_url, self.model)
        default_config = self._load_default_kimi_cli_config()
        if default_config:
            return default_config
        return ""

    def _load_default_kimi_cli_config(self) -> str:
        default_path = Path.home() / ".kimi" / "config.toml"
        if not default_path.exists():
            return ""
        try:
            raw = default_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = default_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return self._normalize_kimi_cli_config(raw)

    def _effective_kimi_cli_model(self, config_text: str | None = None) -> str | None:
        requested = str(self.model or "").strip()
        parsed = self._parse_kimi_cli_config_text(config_text or "")
        if not isinstance(parsed, dict):
            return requested or None

        default_model = str(parsed.get("default_model") or "").strip()
        models = parsed.get("models")
        if isinstance(models, dict):
            if requested and requested in models:
                return requested
            if requested:
                for key, item in models.items():
                    key_text = str(key or "").strip()
                    if not key_text:
                        continue
                    model_name = ""
                    if isinstance(item, dict):
                        model_name = str(item.get("model") or "").strip()
                    if requested == key_text or requested == model_name or requested == key_text.rsplit("/", 1)[-1]:
                        return key_text
            if default_model:
                return default_model
        if default_model:
            return default_model
        return requested or None

    def _normalize_kimi_cli_config(self, raw_config: str) -> str:
        text = (raw_config or "").strip()
        if not text:
            return ""
        parsed = self._parse_kimi_cli_config_text(text)
        if not isinstance(parsed, dict):
            # Keep raw config for non-JSON/TOML formats provided by user.
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
    def _parse_kimi_cli_config_text(text: str) -> dict[str, Any] | None:
        raw = (text or "").strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            if tomllib is None:
                return None
            try:
                parsed = tomllib.loads(raw)
            except Exception:
                return None
        return parsed if isinstance(parsed, dict) else None

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
