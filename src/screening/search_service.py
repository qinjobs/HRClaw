from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import db as db_module
from .config import load_local_env
from .db import connect, dumps, loads


CHUNK_LIMIT = 800
CHUNK_OVERLAP = 100
VECTOR_COLLECTION_NAME = "resume_chunks_v1"
DEFAULT_TOP_K = 20
INITIAL_RECALL_LIMIT = 80
RERANK_LIMIT = 20
HASH_EMBED_DIM = 256
DEFAULT_BGE_EMBED_DIM = 768
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"

EDUCATION_RANKS = {
    "博士": 5,
    "phd": 5,
    "硕士": 4,
    "master": 4,
    "研究生": 4,
    "本科": 3,
    "bachelor": 3,
    "大专": 2,
    "专科": 2,
    "统招大专": 2,
    "高中": 1,
}

KNOWN_LOCATIONS = [
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
]

KNOWN_TITLES = [
    "测试工程师",
    "测试开发",
    "qa",
    "java架构师",
    "架构师",
    "python开发",
    "开发工程师",
    "后端工程师",
    "前端工程师",
    "产品经理",
]

KNOWN_SKILLS = [
    "java",
    "python",
    "linux",
    "adb",
    "charles",
    "fiddler",
    "sql",
    "mysql",
    "postgresql",
    "redis",
    "postman",
    "jmeter",
    "appium",
    "selenium",
    "docker",
    "kubernetes",
    "spring",
    "springboot",
    "kafka",
    "rabbitmq",
    "测试",
    "自动化",
    "接口测试",
    "性能测试",
    "兼容性测试",
    "前后端测试",
    "鸿蒙",
    "openharmony",
    "在线教育",
    "教育",
    "web",
    "app",
    "小程序",
]

KNOWN_INDUSTRIES = [
    "在线教育",
    "教育",
    "电商",
    "金融",
    "医疗",
    "工业",
    "汽车",
    "房产",
    "社交",
    "游戏",
]

SKILL_SYNONYMS = {
    "qa": ["测试", "qa", "quality assurance"],
    "测试": ["qa", "功能测试", "测试"],
    "测试开发": ["自动化测试", "测试开发", "test development"],
    "adb": ["android debug bridge", "adb"],
    "charles": ["抓包", "charles"],
    "fiddler": ["抓包", "fiddler"],
    "mysql": ["sql", "mysql"],
    "linux": ["shell", "linux"],
    "springboot": ["spring boot", "springboot"],
    "在线教育": ["教育", "k12", "在线教育"],
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(text)
    return items


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return "\n".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_flatten_text(item) for item in value)
    return str(value)


def _education_rank(value: str | None) -> int:
    if not value:
        return 0
    lowered = value.lower()
    best = 0
    for label, rank in EDUCATION_RANKS.items():
        if label in lowered:
            best = max(best, rank)
    return best


def _contains_text(target: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not target:
        return False
    return expected.strip().lower() in target.strip().lower()


def _semantic_terms(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    ascii_terms = re.findall(r"[a-z0-9][a-z0-9\+\#\.\-_/]{0,30}", lowered)
    chinese_groups = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
    grams: list[str] = []
    for group in chinese_groups:
        chars = list(group)
        for size in (2, 3):
            if len(chars) < size:
                continue
            for idx in range(len(chars) - size + 1):
                grams.append("".join(chars[idx : idx + size]))
    single_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    return _unique_texts(ascii_terms + chinese_groups + grams + single_chars)


def _fts_normalize(text: str) -> str:
    return " ".join(_semantic_terms(text))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _hash_embedding(text: str, dim: int = HASH_EMBED_DIM) -> list[float]:
    vector = [0.0] * dim
    terms = _semantic_terms(text)
    if not terms:
        return vector
    for term in terms:
        digest = hashlib.md5(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        weight = 1.0 + min(len(term), 6) / 6.0
        vector[index] += sign * weight
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        return vector
    return [item / norm for item in vector]


def _trim_snippet(text: str, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _extract_json_blob(text: str) -> Any:
    if not text:
        return None
    decoder = json.JSONDecoder()
    start_positions = sorted(
        ((text.find(start_char), start_char) for start_char in ("{", "[")),
        key=lambda item: item[0] if item[0] >= 0 else len(text) + 1,
    )
    for initial_start, start_char in start_positions:
        start = initial_start
        while start >= 0:
            try:
                payload, _ = decoder.raw_decode(text[start:])
                return payload
            except Exception:
                start = text.find(start_char, start + 1)
    return None


def _llm_json_prefill(expected_type: str | None) -> str | None:
    if expected_type == "object":
        return "{"
    if expected_type == "array":
        return "["
    return None


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _unique_texts(value)
    return _unique_texts([value])


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value or "").strip().lower()
    if lowered in {"true", "1", "yes", "y", "pass", "passed"}:
        return True
    if lowered in {"false", "0", "no", "n", "reject", "rejected", "fail", "failed"}:
        return False
    return bool(value)


def _split_with_overlap(text: str, limit: int = CHUNK_LIMIT, overlap: int = CHUNK_OVERLAP) -> list[str]:
    source = re.sub(r"\s+", " ", text or "").strip()
    if not source:
        return []
    if len(source) <= limit:
        return [source]
    chunks: list[str] = []
    start = 0
    while start < len(source):
        end = min(len(source), start + limit)
        chunk = source[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(source):
            break
        start = max(end - overlap, start + 1)
    return chunks


@dataclass(slots=True)
class SearchIntent:
    must_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    industry: list[str] = field(default_factory=list)
    location: str | None = None
    years_min: float | None = None
    education_min: str | None = None
    weights: dict[str, float] = field(default_factory=dict)
    query_variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HashingEmbedder:
    provider = "hash_fallback"

    def __init__(self, dim: int = HASH_EMBED_DIM) -> None:
        self.model_name = "hash-fallback"
        self.dimension = dim

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        return [_hash_embedding(text, dim=self.dimension) for text in texts]


class HuggingFaceBGEEmbedder:
    provider = "huggingface_transformers"

    def __init__(self) -> None:
        self.model_name = os.getenv("SCREENING_SEARCH_EMBEDDING_MODEL", "BAAI/bge-base-zh-v1.5").strip() or "BAAI/bge-base-zh-v1.5"
        self.device_name = os.getenv("SCREENING_SEARCH_EMBEDDING_DEVICE", "cpu").strip().lower() or "cpu"
        self.max_length = max(32, int(os.getenv("SCREENING_SEARCH_EMBEDDING_MAX_LENGTH", "512")))
        self.batch_size = max(1, int(os.getenv("SCREENING_SEARCH_EMBEDDING_BATCH_SIZE", "24")))
        self.local_files_only = os.getenv("SCREENING_SEARCH_EMBEDDING_LOCAL_FILES_ONLY", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.query_instruction = os.getenv(
            "SCREENING_SEARCH_EMBEDDING_QUERY_INSTRUCTION",
            "为这个句子生成表示以用于检索相关简历：",
        ).strip()
        self._dimension = max(1, int(os.getenv("SCREENING_SEARCH_EMBEDDING_DIM", str(DEFAULT_BGE_EMBED_DIM))))
        self._bundle: tuple[Any, Any, Any, str] | None = None
        self._lock = threading.Lock()

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_bundle(self) -> tuple[Any, Any, Any, str]:
        if self._bundle is not None:
            return self._bundle
        with self._lock:
            if self._bundle is not None:
                return self._bundle
            import torch
            from transformers import AutoModel, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
            model = AutoModel.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                local_files_only=self.local_files_only,
            )
            device = "cpu"
            requested = self.device_name
            if requested == "mps" and getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                device = "mps"
            elif requested.startswith("cuda") and torch.cuda.is_available():
                device = requested
            model = model.to(device)
            model.eval()
            hidden_size = getattr(getattr(model, "config", None), "hidden_size", None)
            if isinstance(hidden_size, int) and hidden_size > 0:
                self._dimension = hidden_size
            self._bundle = (tokenizer, model, torch, device)
        return self._bundle

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        tokenizer, model, torch, device = self._ensure_bundle()
        prepared = [self._prepare_query(text) if is_query else str(text or "") for text in texts]
        vectors: list[list[float]] = []
        with torch.inference_mode():
            for start in range(0, len(prepared), self.batch_size):
                batch = prepared[start : start + self.batch_size]
                inputs = tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                inputs = {key: value.to(device) for key, value in inputs.items()}
                outputs = model(**inputs)
                embeddings = self._cls_pooling(outputs)
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                vectors.extend(embeddings.cpu().tolist())
        return vectors

    def _prepare_query(self, text: str) -> str:
        value = str(text or "").strip()
        if not value or not self.query_instruction:
            return value
        if value.startswith(self.query_instruction):
            return value
        return f"{self.query_instruction}{value}"

    @staticmethod
    def _cls_pooling(outputs: Any):
        if hasattr(outputs, "last_hidden_state") and outputs.last_hidden_state is not None:
            return outputs.last_hidden_state[:, 0]
        if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
            return outputs.pooler_output
        if isinstance(outputs, (list, tuple)) and outputs:
            return outputs[0][:, 0]
        raise RuntimeError("Embedding model did not return a usable hidden state.")


class BoundedSearchAgent:
    def __init__(self, service: "ResumeSearchService", max_turns: int = 6) -> None:
        self.service = service
        self.max_turns = max_turns
        self.turns = 0

    def _guard(self) -> None:
        if self.turns >= self.max_turns:
            raise RuntimeError("tool turn budget exceeded")
        self.turns += 1

    def get_candidate_profile(self, resume_profile_id: str) -> dict[str, Any]:
        self._guard()
        return self.service.get_search_profile(resume_profile_id)

    def get_candidate_chunk(self, resume_profile_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        self._guard()
        return self.service.list_profile_chunks(resume_profile_id, limit=limit)

    def expand_similar_candidates(self, resume_profile_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        self._guard()
        return self.service.expand_similar_candidates(resume_profile_id, limit=limit)

    def lookup_skill_synonyms(self, skill: str) -> list[str]:
        self._guard()
        lowered = (skill or "").strip().lower()
        return SKILL_SYNONYMS.get(lowered, [skill] if skill else [])


class ResumeSearchService:
    def __init__(self) -> None:
        load_local_env()
        self._fallback_embedder = HashingEmbedder()
        self._embedding_error: str | None = None
        self.embedder = self._build_embedder()
        self._background_runs: dict[str, threading.Thread] = {}
        self._llm_state: tuple[Any, Any] | bool | None = None
        self._llm_lock = threading.Lock()
        self._qdrant_state: tuple[Any, Any] | bool | None = None
        self._qdrant_lock = threading.Lock()

    def _local_llm_enabled(self) -> bool:
        raw_flag = os.getenv("SCREENING_SEARCH_ENABLE_LOCAL_LLM")
        if raw_flag is not None and raw_flag.strip() != "":
            return raw_flag.strip().lower() in {"1", "true", "yes", "on"}
        base_url = (
            os.getenv("SCREENING_SEARCH_OPENAI_BASE_URL")
            or os.getenv("SCREENING_SEARCH_LLM_BASE_URL")
            or ""
        ).strip()
        api_key = (
            os.getenv("SCREENING_SEARCH_OPENAI_API_KEY")
            or os.getenv("SCREENING_SEARCH_LLM_API_KEY")
            or ""
        ).strip()
        model = (
            os.getenv("SCREENING_SEARCH_OPENAI_MODEL")
            or os.getenv("SCREENING_SEARCH_NANBEIGE_MODEL")
            or ""
        ).strip()
        return bool(base_url and api_key and model)

    def _effective_rerank_limit(self) -> int:
        if self._openai_compatible_llm_config() is not None:
            return min(RERANK_LIMIT, 10)
        return RERANK_LIMIT

    def _build_embedder(self):
        provider = os.getenv("SCREENING_SEARCH_EMBEDDING_PROVIDER", "auto").strip().lower() or "auto"
        if provider in {"hash", "hash_fallback"}:
            return self._fallback_embedder
        can_use_hf = importlib.util.find_spec("transformers") is not None and importlib.util.find_spec("torch") is not None
        if provider in {"hf", "huggingface", "transformers", "auto"} and can_use_hf:
            return HuggingFaceBGEEmbedder()
        if provider in {"hf", "huggingface", "transformers"} and not can_use_hf:
            self._embedding_error = "transformers_or_torch_missing"
        return self._fallback_embedder

    def _encode_texts(self, texts: list[str], *, is_query: bool, degraded: list[str] | None = None) -> list[list[float]]:
        try:
            return self.embedder.encode(texts, is_query=is_query)
        except Exception as exc:
            self._embedding_error = str(exc)
            if self.embedder.provider != self._fallback_embedder.provider:
                self.embedder = self._fallback_embedder
                if degraded is not None:
                    degraded.append("embedding_model_fallback")
                return self.embedder.encode(texts, is_query=is_query)
            raise

    def sync_candidates(
        self,
        *,
        task_id: str | None = None,
        candidate_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        started_ms = _now_ms()
        ids = _unique_texts(candidate_ids or [])
        items = self._load_candidate_rows(task_id=task_id, candidate_ids=ids or None)
        if not items:
            return {
                "task_id": task_id,
                "synced_candidates": 0,
                "upserted_profiles": 0,
                "upserted_chunks": 0,
                "degraded": [],
                "duration_ms": _now_ms() - started_ms,
            }
        summary = self.upsert_profiles(items=items)
        return {
            **summary,
            "task_id": task_id,
            "synced_candidates": len(items),
        }

    def rebuild_vector_store(self) -> dict[str, Any]:
        started_ms = _now_ms()
        chunks = self._load_all_chunks()
        client_bundle = self._qdrant_bundle()
        if client_bundle is None:
            return {
                "ok": False,
                "collection": VECTOR_COLLECTION_NAME,
                "points": 0,
                "provider": self.embedder.provider,
                "model": getattr(self.embedder, "model_name", None),
                "error": "vector_store_unavailable",
                "duration_ms": _now_ms() - started_ms,
            }
        client, models = client_bundle
        if not self._recreate_qdrant_collection(client, models):
            return {
                "ok": False,
                "collection": VECTOR_COLLECTION_NAME,
                "points": 0,
                "provider": self.embedder.provider,
                "model": getattr(self.embedder, "model_name", None),
                "error": "vector_collection_recreate_failed",
                "duration_ms": _now_ms() - started_ms,
            }
        degraded = self._sync_vector_store(chunks, [])
        return {
            "ok": not degraded,
            "collection": VECTOR_COLLECTION_NAME,
            "points": len(chunks),
            "provider": self.embedder.provider,
            "model": getattr(self.embedder, "model_name", None),
            "dimension": self._embed_dim(),
            "degraded": _unique_texts(degraded),
            "duration_ms": _now_ms() - started_ms,
            **({"embedding_error": self._embedding_error} if self._embedding_error else {}),
        }

    def close(self) -> None:
        state = self._qdrant_state
        self._qdrant_state = None
        if isinstance(state, tuple):
            client = state[0]
            try:
                client.close()
            except Exception:
                pass

    def upsert_profiles(self, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        degraded: list[str] = []
        started_ms = _now_ms()
        source_items = items if items is not None else self._load_local_candidates()
        standardized = [self._standardize_profile_item(item) for item in source_items]
        standardized = [item for item in standardized if item]
        chunk_records: list[dict[str, Any]] = []
        deleted_chunk_ids: list[str] = []
        with connect() as conn:
            for item in standardized:
                profile_id = item["id"]
                existing_rows = conn.execute(
                    "select id from resume_chunks where resume_profile_id = ?",
                    (profile_id,),
                ).fetchall()
                existing_chunk_ids = [str(row["id"]) for row in existing_rows]
                deleted_chunk_ids.extend(existing_chunk_ids)
                if existing_chunk_ids:
                    placeholders = ",".join("?" for _ in existing_chunk_ids)
                    try:
                        conn.execute(
                            f"delete from resume_chunks_fts where chunk_id in ({placeholders})",
                            existing_chunk_ids,
                        )
                    except Exception:
                        pass
                conn.execute("delete from resume_chunks where resume_profile_id = ?", (profile_id,))
                conn.execute(
                    """
                    insert into resume_profiles (
                        id, source, external_id, source_candidate_id, name, city, years_experience,
                        education_level, latest_title, latest_company, skills, industry_tags,
                        raw_profile, raw_resume_entry, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                    on conflict(id) do update set
                        source = excluded.source,
                        external_id = excluded.external_id,
                        source_candidate_id = excluded.source_candidate_id,
                        name = excluded.name,
                        city = excluded.city,
                        years_experience = excluded.years_experience,
                        education_level = excluded.education_level,
                        latest_title = excluded.latest_title,
                        latest_company = excluded.latest_company,
                        skills = excluded.skills,
                        industry_tags = excluded.industry_tags,
                        raw_profile = excluded.raw_profile,
                        raw_resume_entry = excluded.raw_resume_entry,
                        updated_at = current_timestamp
                    """,
                    (
                        profile_id,
                        item["source"],
                        item["external_id"],
                        item.get("source_candidate_id"),
                        item.get("name"),
                        item.get("city"),
                        item.get("years_experience"),
                        item.get("education_level"),
                        item.get("latest_title"),
                        item.get("latest_company"),
                        dumps(item.get("skills", [])),
                        dumps(item.get("industry_tags", [])),
                        dumps(item.get("raw_profile", {})),
                        dumps(item.get("raw_resume_entry", {})),
                    ),
                )
                chunks = self._build_chunks(item)
                for chunk in chunks:
                    conn.execute(
                        """
                        insert into resume_chunks (
                            id, resume_profile_id, source_candidate_id, chunk_type, chunk_index,
                            content, title, city, experience_years, skills, updated_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                        """,
                        (
                            chunk["id"],
                            profile_id,
                            item.get("source_candidate_id"),
                            chunk["chunk_type"],
                            chunk["chunk_index"],
                            chunk["content"],
                            item.get("latest_title"),
                            item.get("city"),
                            item.get("years_experience"),
                            dumps(item.get("skills", [])),
                        ),
                    )
                    try:
                        conn.execute(
                            """
                            insert into resume_chunks_fts (chunk_id, content, title, city, skills)
                            values (?, ?, ?, ?, ?)
                            """,
                            (
                                chunk["id"],
                                _fts_normalize(chunk["content"]),
                                _fts_normalize(item.get("latest_title") or ""),
                                _fts_normalize(item.get("city") or ""),
                                _fts_normalize(" ".join(item.get("skills", []))),
                            ),
                        )
                    except Exception:
                        if "fts_unavailable" not in degraded:
                            degraded.append("fts_unavailable")
                    chunk_records.append(
                        {
                            "id": chunk["id"],
                            "resume_profile_id": profile_id,
                            "source_candidate_id": item.get("source_candidate_id"),
                            "chunk_type": chunk["chunk_type"],
                            "text": chunk["content"],
                            "title": item.get("latest_title"),
                            "city": item.get("city"),
                            "experience_years": item.get("years_experience"),
                            "skills": item.get("skills", []),
                        }
                    )
        degraded.extend(self._sync_vector_store(chunk_records, deleted_chunk_ids))
        return {
            "upserted_profiles": len(standardized),
            "upserted_chunks": len(chunk_records),
            "degraded": _unique_texts(degraded),
            "duration_ms": _now_ms() - started_ms,
        }

    def search(
        self,
        *,
        jd_text: str | None,
        query_text: str | None,
        filters: dict[str, Any] | None,
        top_k: int = DEFAULT_TOP_K,
        explain: bool = False,
    ) -> dict[str, Any]:
        started_ms = _now_ms()
        raw_query = (jd_text or query_text or "").strip()
        if not raw_query:
            raise ValueError("jd_text 或 query_text 不能为空")
        effective_top_k = max(1, min(int(top_k or DEFAULT_TOP_K), 50))
        degraded: list[str] = []
        intent = self._parse_intent(raw_query, filters or {}, degraded)
        run_id = str(uuid.uuid4())
        self._insert_search_run(
            run_id=run_id,
            jd_text=jd_text,
            query_text=query_text,
            filters=filters or {},
            top_k=effective_top_k,
            explain=explain,
            status="retrieving",
            query_intent=intent.to_dict(),
            degraded=degraded,
            model_summary={},
            retrieval_latency_ms=0,
            rerank_latency_ms=0,
            total_latency_ms=0,
        )
        base_results, retrieval_ms, retrieval_degraded = self._retrieve(intent, effective_top_k)
        degraded.extend(retrieval_degraded)
        self._replace_search_results(run_id, base_results)
        status = "retrieved"
        model_summary = {"provider": "pending", "model": None, "explain_requested": explain}
        self._update_search_run(
            run_id,
            status=status,
            degraded=_unique_texts(degraded),
            model_summary=model_summary,
            retrieval_latency_ms=retrieval_ms,
            total_latency_ms=_now_ms() - started_ms,
        )
        if explain and base_results:
            if os.getenv("SCREENING_SEARCH_SYNC_EXPLAIN", "0") == "1":
                self._complete_run_explanations(run_id, intent, started_ms)
                status = "completed"
            else:
                worker = threading.Thread(
                    target=self._complete_run_explanations,
                    args=(run_id, intent, started_ms),
                    daemon=True,
                )
                self._background_runs[run_id] = worker
                worker.start()
                status = "reranking"
        else:
            self._finalize_without_explain(run_id, started_ms)
            status = "completed"
        run_payload = self.get_search_run(run_id)
        return {
            "search_run_id": run_id,
            "status": status,
            "query_intent": intent.to_dict(),
            "results": run_payload.get("results", [])[:effective_top_k],
        }

    def get_search_run(self, run_id: str) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute("select * from search_runs where id = ?", (run_id,)).fetchone()
            if not row:
                raise KeyError(f"Search run not found: {run_id}")
            run = dict(row)
            results = conn.execute(
                """
                select
                    r.*,
                    p.source,
                    p.external_id,
                    p.name,
                    p.city,
                    p.years_experience,
                    p.education_level,
                    p.latest_title,
                    p.latest_company,
                    p.raw_resume_entry
                from search_results r
                join resume_profiles p on p.id = r.resume_profile_id
                where r.search_run_id = ?
                order by r.rank asc
                """,
                (run_id,),
            ).fetchall()
        payload = {
            **run,
            "filters": loads(run["filters"]) or {},
            "query_intent": loads(run["query_intent"]) or {},
            "degraded": loads(run["degraded"]) or [],
            "model_summary": loads(run["model_summary"]) or {},
            "results": [self._format_search_result_row(dict(item)) for item in results],
        }
        return payload

    def get_search_profile(self, candidate_id: str) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                """
                select *
                from resume_profiles
                where id = ? or source_candidate_id = ?
                order by updated_at desc
                limit 1
                """,
                (candidate_id, candidate_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Search profile not found: {candidate_id}")
            profile = dict(row)
        chunks = self.list_profile_chunks(profile["id"], limit=20)
        return {
            **profile,
            "skills": loads(profile["skills"]) or [],
            "industry_tags": loads(profile["industry_tags"]) or [],
            "raw_profile": loads(profile["raw_profile"]) or {},
            "raw_resume_entry": loads(profile["raw_resume_entry"]) or {},
            "chunks": chunks,
        }

    def list_profile_chunks(self, resume_profile_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                select *
                from resume_chunks
                where resume_profile_id = ?
                order by chunk_type asc, chunk_index asc
                limit ?
                """,
                (resume_profile_id, max(1, limit)),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["skills"] = loads(item["skills"]) or []
            items.append(item)
        return items

    def expand_similar_candidates(self, resume_profile_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        profile = self.get_search_profile(resume_profile_id)
        city = profile.get("city")
        title = profile.get("latest_title") or ""
        skills = loads(profile["skills"]) if isinstance(profile.get("skills"), str) else profile.get("skills", [])
        with connect() as conn:
            rows = conn.execute(
                """
                select id, name, city, latest_title, latest_company, years_experience
                from resume_profiles
                where id != ?
                  and (? is null or city = ? or latest_title like ?)
                order by updated_at desc
                limit ?
                """,
                (resume_profile_id, city, city, f"%{title[:6]}%", max(1, limit)),
            ).fetchall()
        similar = []
        for row in rows:
            item = dict(row)
            overlap = self._skill_overlap(skills or [], [])
            item["similarity_hint"] = overlap
            similar.append(item)
        return similar

    def _load_local_candidates(self) -> list[dict[str, Any]]:
        return self._load_candidate_rows()

    def _load_candidate_rows(
        self,
        *,
        task_id: str | None = None,
        candidate_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if task_id:
            clauses.append("c.task_id = ?")
            params.append(task_id)
        if candidate_ids:
            placeholders = ",".join("?" for _ in candidate_ids)
            clauses.append(f"c.id in ({placeholders})")
            params.extend(candidate_ids)
        where_clause = f"where {' and '.join(clauses)}" if clauses else ""
        with connect() as conn:
            rows = conn.execute(
                f"""
                select
                    c.*,
                    s.extracted_text,
                    s.screenshot_path,
                    s.evidence_map
                from candidates c
                left join candidate_snapshots s on s.id = (
                    select x.id
                    from candidate_snapshots x
                    where x.candidate_id = c.id
                    order by x.created_at desc
                    limit 1
                )
                {where_clause}
                order by c.created_at desc
                """,
                params,
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["normalized_fields"] = loads(item.get("normalized_fields")) or {}
            item["evidence_map"] = loads(item.get("evidence_map")) or {}
            items.append(item)
        return items

    def _standardize_profile_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if "task_id" in item and "normalized_fields" in item:
            return self._standardize_candidate_row(item)
        source = str(item.get("source") or "custom").strip()
        external_id = str(item.get("external_id") or item.get("id") or item.get("source_candidate_id") or uuid.uuid4()).strip()
        skills = _unique_texts(item.get("skills", []))
        industry_tags = _unique_texts(item.get("industry_tags", []))
        raw_profile = item.get("raw_profile")
        if not isinstance(raw_profile, dict):
            raw_profile = {
                "summary": item.get("summary") or item.get("raw_summary"),
                "experience": item.get("experience"),
                "projects": item.get("projects"),
                "skills": skills,
                "education": item.get("education"),
                "raw_resume_text": item.get("raw_resume_text") or item.get("snapshot_text"),
            }
        resume_entry = item.get("raw_resume_entry")
        if not isinstance(resume_entry, dict):
            resume_entry = {}
        standardized = {
            "id": f"{source}:{external_id}",
            "source": source,
            "external_id": external_id,
            "source_candidate_id": item.get("source_candidate_id") or item.get("candidate_id"),
            "name": item.get("name"),
            "city": item.get("city") or item.get("location"),
            "years_experience": self._safe_float(item.get("years_experience")),
            "education_level": item.get("education_level"),
            "latest_title": item.get("latest_title") or item.get("current_title"),
            "latest_company": item.get("latest_company") or item.get("current_company"),
            "skills": skills,
            "industry_tags": industry_tags,
            "raw_profile": raw_profile,
            "raw_resume_entry": resume_entry,
        }
        return standardized

    def _standardize_candidate_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = row.get("normalized_fields") or {}
        evidence_map = row.get("evidence_map") or {}
        tools = normalized.get("tools", [])
        explicit_skills = normalized.get("skills", [])
        derived_skills = []
        for key, value in normalized.items():
            if value is True and key.endswith("_test"):
                derived_skills.append(key.replace("_", " "))
        skills = _unique_texts(tools + explicit_skills + derived_skills + self._extract_known_terms(row.get("raw_summary", ""), KNOWN_SKILLS))
        industries = _unique_texts(normalized.get("industry_tags", []) + self._extract_known_terms(row.get("raw_summary", ""), KNOWN_INDUSTRIES))
        resume_path = _first_text(evidence_map.get("resume_path"))
        raw_resume_text = self._candidate_resume_text(row.get("extracted_text"), resume_path)
        raw_profile = {
            "candidate_id": row["id"],
            "summary": row.get("raw_summary"),
            "experience": raw_resume_text,
            "projects": normalized.get("project_experience"),
            "skills": skills,
            "education": " ".join(_unique_texts([row.get("education_level"), row.get("major")])),
            "raw_resume_text": raw_resume_text,
            "normalized_fields": normalized,
            "detail_url": evidence_map.get("detail_url"),
            "resume_path": resume_path,
        }
        return {
            "id": f"local_candidate:{row.get('external_id') or row['id']}",
            "source": "local_candidate",
            "external_id": row.get("external_id") or row["id"],
            "source_candidate_id": row["id"],
            "name": row.get("name"),
            "city": row.get("location"),
            "years_experience": self._safe_float(row.get("years_experience")),
            "education_level": row.get("education_level"),
            "latest_title": row.get("current_title"),
            "latest_company": row.get("current_company"),
            "skills": skills,
            "industry_tags": industries,
            "raw_profile": raw_profile,
            "raw_resume_entry": {
                "detail_api_path": f"/api/candidates/{row['id']}",
                "screenshot_api_path": f"/api/candidates/{row['id']}/screenshot",
                "candidate_id": row["id"],
                "task_id": row.get("task_id"),
                "external_id": row.get("external_id") or row["id"],
                "detail_url": evidence_map.get("detail_url"),
                "snapshot_path": row.get("screenshot_path"),
                "resume_path": resume_path,
                "resume_downloaded": bool(evidence_map.get("resume_downloaded")),
                "resume_filename": evidence_map.get("resume_filename"),
            },
        }

    def _candidate_resume_text(self, extracted_text: Any, resume_path: str | None) -> str:
        text = str(extracted_text or "").strip()
        if text:
            return text
        if resume_path and str(resume_path).lower().endswith(".txt"):
            try:
                return Path(resume_path).read_text(encoding="utf-8").strip()
            except Exception:
                return ""
        return ""

    def _build_chunks(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        raw_profile = item.get("raw_profile", {})
        sections = {
            "summary": raw_profile.get("summary") or self._compose_summary(item),
            "experience": raw_profile.get("experience") or raw_profile.get("raw_resume_text") or self._compose_summary(item),
            "projects": raw_profile.get("projects") or raw_profile.get("project_experience") or "",
            "skills": raw_profile.get("skills") or " ".join(item.get("skills", [])),
            "education": raw_profile.get("education") or " ".join(
                _unique_texts([item.get("education_level"), raw_profile.get("major")])
            ),
        }
        chunks: list[dict[str, Any]] = []
        for chunk_type in ("summary", "experience", "projects", "skills", "education"):
            text = _flatten_text(sections.get(chunk_type))
            if not text:
                continue
            for chunk_index, content in enumerate(_split_with_overlap(text), start=1):
                chunk_id = hashlib.md5(
                    f"{item['id']}|{chunk_type}|{chunk_index}".encode("utf-8")
                ).hexdigest()
                chunks.append(
                    {
                        "id": chunk_id,
                        "chunk_type": chunk_type,
                        "chunk_index": chunk_index,
                        "content": content,
                    }
                )
        return chunks

    def _compose_summary(self, item: dict[str, Any]) -> str:
        parts = [
            item.get("name"),
            item.get("latest_title"),
            item.get("latest_company"),
            item.get("city"),
            f"{item.get('years_experience')}年经验" if item.get("years_experience") else "",
            item.get("education_level"),
            " / ".join(item.get("skills", [])),
            " / ".join(item.get("industry_tags", [])),
        ]
        return " | ".join(part for part in parts if part)

    def _parse_intent(self, raw_query: str, filters: dict[str, Any], degraded: list[str]) -> SearchIntent:
        llm_intent = self._try_parse_intent_with_local_model(raw_query)
        if llm_intent:
            intent = llm_intent
        else:
            degraded.append("intent_rule_parser")
            intent = self._parse_intent_with_rules(raw_query)
        if filters.get("location"):
            intent.location = str(filters["location"]).strip()
        if filters.get("years_min") is not None:
            intent.years_min = self._safe_float(filters["years_min"])
        if filters.get("education_min"):
            intent.education_min = str(filters["education_min"]).strip()
        if filters.get("skills"):
            intent.skills = _unique_texts(intent.skills + list(filters.get("skills") or []))
            intent.must_have = _unique_texts(intent.must_have + list(filters.get("skills") or []))
        intent.query_variants = _unique_texts(
            [raw_query]
            + intent.query_variants
            + [" ".join(intent.titles + intent.skills + intent.industry)]
            + [" ".join(intent.must_have[:6])]
            + ([intent.location] if intent.location else [])
        )
        return intent

    def _parse_intent_with_rules(self, raw_query: str) -> SearchIntent:
        lowered = raw_query.lower()
        years_match = re.search(r"(\d+(?:\.\d+)?)\s*年(?:以上|及以上|经验)?", raw_query)
        years_min = float(years_match.group(1)) if years_match else None
        education_min = None
        for label in EDUCATION_RANKS:
            if label in lowered:
                education_min = label
                break
        location = next((city for city in KNOWN_LOCATIONS if city in raw_query), None)
        titles = self._extract_known_terms(raw_query, KNOWN_TITLES)
        skills = self._extract_known_terms(raw_query, KNOWN_SKILLS)
        industry = self._extract_known_terms(raw_query, KNOWN_INDUSTRIES)
        must_have = _unique_texts(skills + titles)
        nice_to_have = []
        for marker in ("优先", "加分", "最好"):
            if marker in raw_query:
                nice_to_have.extend(self._extract_window_terms(raw_query, marker))
        exclude = []
        for marker in ("不要", "排除", "不考虑", "exclude"):
            if marker in raw_query:
                exclude.extend(self._extract_window_terms(raw_query, marker))
        weights = {
            "must_have": 0.4,
            "skill_overlap": 0.2,
            "title_match": 0.15,
            "industry_match": 0.1,
            "location_match": 0.1,
            "stability": 0.05,
        }
        return SearchIntent(
            must_have=must_have,
            nice_to_have=_unique_texts(nice_to_have),
            exclude=_unique_texts(exclude),
            titles=titles,
            skills=skills,
            industry=industry,
            location=location,
            years_min=years_min,
            education_min=education_min,
            weights=weights,
            query_variants=_unique_texts([" ".join(skills + titles), " ".join(industry + skills)]),
        )

    def _extract_known_terms(self, text: str, candidates: list[str]) -> list[str]:
        lowered = (text or "").lower()
        return [item for item in candidates if item.lower() in lowered]

    def _extract_window_terms(self, text: str, marker: str) -> list[str]:
        start = text.find(marker)
        if start < 0:
            return []
        window = text[start : start + 60]
        return self._extract_known_terms(window, KNOWN_SKILLS + KNOWN_INDUSTRIES + KNOWN_TITLES)

    def _try_parse_intent_with_local_model(self, raw_query: str) -> SearchIntent | None:
        if not self._local_llm_enabled():
            return None
        try:
            payload = self._generate_local_llm_json(
                system_prompt=(
                    "你是招聘搜索意图解析器。"
                    "请把输入的JD或自然语言需求转成严格JSON，不要输出任何额外说明。"
                ),
                user_prompt=(
                    "输出字段固定为 "
                    "must_have, nice_to_have, exclude, titles, skills, industry, location, "
                    "years_min, education_min, weights, query_variants。\n"
                    f"输入内容：{raw_query}"
                ),
                max_new_tokens=700,
                expected_type="object",
            )
            if not isinstance(payload, dict):
                return None
            return SearchIntent(
                must_have=_unique_texts(payload.get("must_have", [])),
                nice_to_have=_unique_texts(payload.get("nice_to_have", [])),
                exclude=_unique_texts(payload.get("exclude", [])),
                titles=_unique_texts(payload.get("titles", [])),
                skills=_unique_texts(payload.get("skills", [])),
                industry=_unique_texts(payload.get("industry", [])),
                location=_first_text(payload.get("location")),
                years_min=self._safe_float(payload.get("years_min")) if payload.get("years_min") is not None else None,
                education_min=_first_text(payload.get("education_min")),
                weights=payload.get("weights") if isinstance(payload.get("weights"), dict) else {},
                query_variants=_unique_texts(payload.get("query_variants", [])),
            )
        except Exception:
            return None

    def _retrieve(self, intent: SearchIntent, top_k: int) -> tuple[list[dict[str, Any]], int, list[str]]:
        started_ms = _now_ms()
        degraded: list[str] = []
        profiles = self._load_all_profiles()
        chunks = self._load_all_chunks()
        allowed_profile_ids = {
            profile["id"]
            for profile in profiles
            if self._profile_passes_structured_filters(profile, intent)
        }
        if not allowed_profile_ids:
            return [], _now_ms() - started_ms, degraded
        bm25_hits = self._bm25_search(intent, allowed_profile_ids, degraded)
        vector_hits = self._vector_search(intent, chunks, allowed_profile_ids, degraded)
        aggregated = self._aggregate_retrieval(profiles, chunks, bm25_hits, vector_hits, intent)
        ranked = sorted(aggregated.values(), key=lambda item: item["retrieval_score"], reverse=True)
        rerank_limit = self._effective_rerank_limit()
        results = []
        for rank, item in enumerate(ranked[: max(top_k, rerank_limit)], start=1):
            results.append(
                {
                    "rank": rank,
                    "resume_profile_id": item["resume_profile_id"],
                    "source_candidate_id": item.get("source_candidate_id"),
                    "retrieval_score": round(item["retrieval_score"], 6),
                    "fit_score": None,
                    "final_score": round(item["retrieval_score"] * 100, 2),
                    "hard_filter_pass": bool(item["hard_filter_pass"]),
                    "matched_evidence": item["matched_evidence"][:3],
                    "gaps": [],
                    "risk_flags": [],
                    "interview_questions": [],
                    "final_recommendation": "review" if item["hard_filter_pass"] else "reject",
                    "explanation_status": "pending",
                }
            )
        return results, _now_ms() - started_ms, degraded

    def _load_all_profiles(self) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute("select * from resume_profiles").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["skills"] = loads(item["skills"]) or []
            item["industry_tags"] = loads(item["industry_tags"]) or []
            item["raw_profile"] = loads(item["raw_profile"]) or {}
            item["raw_resume_entry"] = loads(item["raw_resume_entry"]) or {}
            items.append(item)
        return items

    def _load_all_chunks(self) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute("select * from resume_chunks").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["skills"] = loads(item["skills"]) or []
            items.append(item)
        return items

    def _profile_passes_structured_filters(self, profile: dict[str, Any], intent: SearchIntent) -> bool:
        if intent.location and not _contains_text(profile.get("city"), intent.location):
            return False
        if intent.years_min is not None and self._safe_float(profile.get("years_experience")) < float(intent.years_min):
            return False
        if intent.education_min and _education_rank(profile.get("education_level")) < _education_rank(intent.education_min):
            return False
        return True

    def _bm25_search(
        self,
        intent: SearchIntent,
        allowed_profile_ids: set[str],
        degraded: list[str],
    ) -> list[dict[str, Any]]:
        if not allowed_profile_ids:
            return []
        variants = [variant for variant in intent.query_variants if variant][:5]
        if not variants:
            variants = [" ".join(intent.skills + intent.titles + intent.industry)]
        rows: list[dict[str, Any]] = []
        allowed_list = list(allowed_profile_ids)
        placeholders = ",".join("?" for _ in allowed_list)
        with connect() as conn:
            for variant in variants:
                match_query = _fts_normalize(variant)
                if not match_query:
                    continue
                try:
                    query_rows = conn.execute(
                        f"""
                        select
                            rc.id as chunk_id,
                            rc.resume_profile_id,
                            rc.source_candidate_id,
                            rc.content,
                            bm25(resume_chunks_fts) as bm25_score
                        from resume_chunks_fts
                        join resume_chunks rc on rc.id = resume_chunks_fts.chunk_id
                        where resume_chunks_fts match ?
                          and rc.resume_profile_id in ({placeholders})
                        order by bm25_score asc
                        limit ?
                        """,
                        [match_query, *allowed_list, INITIAL_RECALL_LIMIT],
                    ).fetchall()
                except Exception:
                    degraded.append("fts_query_fallback")
                    return self._lexical_search(intent, allowed_profile_ids)
                rows.extend(dict(row) for row in query_rows)
        merged: list[dict[str, Any]] = []
        for rank, row in enumerate(sorted(rows, key=lambda item: item["bm25_score"])[:INITIAL_RECALL_LIMIT], start=1):
            merged.append(
                {
                    "resume_profile_id": row["resume_profile_id"],
                    "source_candidate_id": row.get("source_candidate_id"),
                    "chunk_id": row["chunk_id"],
                    "snippet": _trim_snippet(row["content"]),
                    "score": 1.0 / (60.0 + rank),
                }
            )
        return merged

    def _lexical_search(self, intent: SearchIntent, allowed_profile_ids: set[str]) -> list[dict[str, Any]]:
        query_terms = set(_semantic_terms(" ".join(intent.query_variants)))
        results = []
        for chunk in self._load_all_chunks():
            if chunk["resume_profile_id"] not in allowed_profile_ids:
                continue
            chunk_terms = set(_semantic_terms(chunk.get("content", "")))
            overlap = len(query_terms & chunk_terms)
            if overlap <= 0:
                continue
            results.append(
                {
                    "resume_profile_id": chunk["resume_profile_id"],
                    "source_candidate_id": chunk.get("source_candidate_id"),
                    "chunk_id": chunk["id"],
                    "snippet": _trim_snippet(chunk.get("content", "")),
                    "score": overlap / max(len(query_terms), 1),
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:INITIAL_RECALL_LIMIT]

    def _vector_search(
        self,
        intent: SearchIntent,
        chunks: list[dict[str, Any]],
        allowed_profile_ids: set[str],
        degraded: list[str],
    ) -> list[dict[str, Any]]:
        query_text = " ".join(intent.query_variants or intent.skills or intent.must_have)
        query_vector = self._encode_texts([query_text], is_query=True, degraded=degraded)[0]
        qdrant_hits = self._vector_search_via_qdrant(query_vector, allowed_profile_ids)
        if qdrant_hits is not None:
            return qdrant_hits
        degraded.append("vector_store_fallback")
        results = []
        for chunk in chunks:
            if chunk["resume_profile_id"] not in allowed_profile_ids:
                continue
            chunk_vector = self._encode_texts([chunk.get("content", "")], is_query=False, degraded=degraded)[0]
            score = _cosine_similarity(query_vector, chunk_vector)
            if score <= 0:
                continue
            results.append(
                {
                    "resume_profile_id": chunk["resume_profile_id"],
                    "source_candidate_id": chunk.get("source_candidate_id"),
                    "chunk_id": chunk["id"],
                    "snippet": _trim_snippet(chunk.get("content", "")),
                    "score": score,
                }
            )
        return sorted(results, key=lambda item: item["score"], reverse=True)[:INITIAL_RECALL_LIMIT]

    def _aggregate_retrieval(
        self,
        profiles: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        bm25_hits: list[dict[str, Any]],
        vector_hits: list[dict[str, Any]],
        intent: SearchIntent,
    ) -> dict[str, dict[str, Any]]:
        profile_map = {profile["id"]: profile for profile in profiles}
        aggregated: dict[str, dict[str, Any]] = {}

        def ensure(profile_id: str) -> dict[str, Any]:
            if profile_id not in aggregated:
                profile = profile_map[profile_id]
                aggregated[profile_id] = {
                    "resume_profile_id": profile_id,
                    "source_candidate_id": profile.get("source_candidate_id"),
                    "matched_evidence": [],
                    "bm25_rrf": 0.0,
                    "vector_rrf": 0.0,
                    "facet_bonus": self._facet_bonus(profile, intent),
                    "hard_filter_pass": self._hard_filter_pass(profile, intent),
                }
            return aggregated[profile_id]

        for hit in bm25_hits:
            record = ensure(hit["resume_profile_id"])
            record["bm25_rrf"] = max(record["bm25_rrf"], float(hit["score"]))
            record["matched_evidence"].append(hit["snippet"])

        for hit in vector_hits:
            record = ensure(hit["resume_profile_id"])
            record["vector_rrf"] = max(record["vector_rrf"], float(hit["score"]))
            if hit["snippet"] not in record["matched_evidence"]:
                record["matched_evidence"].append(hit["snippet"])

        for profile_id, record in aggregated.items():
            retrieval_score = (
                0.5 * record["bm25_rrf"] + 0.35 * record["vector_rrf"] + 0.15 * record["facet_bonus"]
            )
            record["retrieval_score"] = retrieval_score
            if not record["matched_evidence"]:
                profile = profile_map[profile_id]
                fallback_evidence = self._compose_summary(profile)
                record["matched_evidence"] = [_trim_snippet(fallback_evidence)]
            record["matched_evidence"] = _unique_texts(record["matched_evidence"])[:3]
        return aggregated

    def _facet_bonus(self, profile: dict[str, Any], intent: SearchIntent) -> float:
        checks: list[float] = []
        if intent.location:
            checks.append(1.0 if _contains_text(profile.get("city"), intent.location) else 0.0)
        if intent.years_min is not None:
            checks.append(1.0 if self._safe_float(profile.get("years_experience")) >= float(intent.years_min) else 0.0)
        if intent.education_min:
            checks.append(1.0 if _education_rank(profile.get("education_level")) >= _education_rank(intent.education_min) else 0.0)
        if intent.skills:
            checks.append(self._skill_overlap(profile.get("skills", []), intent.skills))
        if intent.industry:
            checks.append(self._skill_overlap(profile.get("industry_tags", []), intent.industry))
        if not checks:
            return 0.5
        return sum(checks) / len(checks)

    def _hard_filter_pass(self, profile: dict[str, Any], intent: SearchIntent) -> bool:
        if intent.location and not _contains_text(profile.get("city"), intent.location):
            return False
        if intent.years_min is not None and self._safe_float(profile.get("years_experience")) < float(intent.years_min):
            return False
        if intent.education_min and _education_rank(profile.get("education_level")) < _education_rank(intent.education_min):
            return False
        combined_text = " ".join(
            _unique_texts(
                [
                    profile.get("latest_title"),
                    profile.get("latest_company"),
                    " ".join(profile.get("skills", [])),
                    " ".join(profile.get("industry_tags", [])),
                    _flatten_text(profile.get("raw_profile")),
                ]
            )
        ).lower()
        for skill in intent.exclude:
            if skill.lower() in combined_text:
                return False
        for skill in intent.must_have[:8]:
            synonyms = self._synonym_terms(skill)
            if not any(term.lower() in combined_text for term in synonyms):
                return False
        return True

    def _skill_overlap(self, left: list[str], right: list[str]) -> float:
        left_terms = {term.strip().lower() for term in left if term}
        right_terms = {term.strip().lower() for term in right if term}
        if not left_terms or not right_terms:
            return 0.0
        expanded_left = set(left_terms)
        for item in list(left_terms):
            expanded_left.update(term.lower() for term in self._synonym_terms(item))
        overlap = expanded_left & right_terms
        return len(overlap) / max(len(right_terms), 1)

    def _synonym_terms(self, skill: str) -> list[str]:
        lowered = (skill or "").strip().lower()
        return _unique_texts(SKILL_SYNONYMS.get(lowered, []) + [skill])

    def _replace_search_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        with connect() as conn:
            conn.execute("delete from search_results where search_run_id = ?", (run_id,))
            for item in results:
                conn.execute(
                    """
                    insert into search_results (
                        id, search_run_id, rank, resume_profile_id, source_candidate_id,
                        retrieval_score, fit_score, final_score, hard_filter_pass,
                        matched_evidence, gaps, risk_flags, interview_questions,
                        final_recommendation, explanation_status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        item["rank"],
                        item["resume_profile_id"],
                        item.get("source_candidate_id"),
                        item.get("retrieval_score", 0.0),
                        item.get("fit_score"),
                        item.get("final_score", 0.0),
                        1 if item.get("hard_filter_pass", True) else 0,
                        dumps(item.get("matched_evidence", [])),
                        dumps(item.get("gaps", [])),
                        dumps(item.get("risk_flags", [])),
                        dumps(item.get("interview_questions", [])),
                        item.get("final_recommendation"),
                        item.get("explanation_status", "pending"),
                    ),
                )

    def _insert_search_run(
        self,
        *,
        run_id: str,
        jd_text: str | None,
        query_text: str | None,
        filters: dict[str, Any],
        top_k: int,
        explain: bool,
        status: str,
        query_intent: dict[str, Any],
        degraded: list[str],
        model_summary: dict[str, Any],
        retrieval_latency_ms: int,
        rerank_latency_ms: int,
        total_latency_ms: int,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """
                insert into search_runs (
                    id, jd_text, query_text, filters, top_k, explain, status, query_intent,
                    degraded, model_summary, retrieval_latency_ms, rerank_latency_ms, total_latency_ms,
                    updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                """,
                (
                    run_id,
                    jd_text,
                    query_text,
                    dumps(filters),
                    top_k,
                    1 if explain else 0,
                    status,
                    dumps(query_intent),
                    dumps(_unique_texts(degraded)),
                    dumps(model_summary),
                    retrieval_latency_ms,
                    rerank_latency_ms,
                    total_latency_ms,
                ),
            )

    def _update_search_run(
        self,
        run_id: str,
        *,
        status: str,
        degraded: list[str],
        model_summary: dict[str, Any],
        retrieval_latency_ms: int,
        total_latency_ms: int,
        rerank_latency_ms: int | None = None,
    ) -> None:
        with connect() as conn:
            if rerank_latency_ms is None:
                current = conn.execute(
                    "select rerank_latency_ms from search_runs where id = ?",
                    (run_id,),
                ).fetchone()
                rerank_latency_ms = int(current["rerank_latency_ms"]) if current else 0
            conn.execute(
                """
                update search_runs
                set status = ?,
                    degraded = ?,
                    model_summary = ?,
                    retrieval_latency_ms = ?,
                    rerank_latency_ms = ?,
                    total_latency_ms = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                (
                    status,
                    dumps(_unique_texts(degraded)),
                    dumps(model_summary),
                    retrieval_latency_ms,
                    rerank_latency_ms,
                    total_latency_ms,
                    run_id,
                ),
            )

    def _complete_run_explanations(self, run_id: str, intent: SearchIntent, started_ms: int) -> None:
        rerank_started = _now_ms()
        run = self.get_search_run(run_id)
        degraded = list(run.get("degraded", []))
        base_results = run.get("results", [])[: self._effective_rerank_limit()]
        explained_results = self._try_rerank_with_local_model(intent, base_results)
        if explained_results is not None:
            model_summary = {
                "provider": self._llm_provider_label(),
                "model": self._llm_model_label(),
                "tool_budget": 6,
                "reranked": len(explained_results),
            }
        else:
            explained_results = []
            model_summary = {
                "provider": "heuristic",
                "model": "nanbeige4.1-3b-fallback",
                "tool_budget": 6,
                "reranked": len(base_results),
            }
            degraded.append("nanbeige_unavailable")
            for item in base_results:
                explained_results.append(self._heuristic_rerank(intent, item))
        explained_results.sort(key=lambda row: row["final_score"], reverse=True)
        for rank, item in enumerate(explained_results, start=1):
            item["rank"] = rank
        self._replace_search_results(run_id, explained_results)
        rerank_latency_ms = _now_ms() - rerank_started
        self._update_search_run(
            run_id,
            status="completed",
            degraded=degraded,
            model_summary=model_summary,
            retrieval_latency_ms=int(run.get("retrieval_latency_ms") or 0),
            rerank_latency_ms=rerank_latency_ms,
            total_latency_ms=_now_ms() - started_ms,
        )

    def _heuristic_rerank(self, intent: SearchIntent, item: dict[str, Any]) -> dict[str, Any]:
        agent = BoundedSearchAgent(self, max_turns=6)
        profile = agent.get_candidate_profile(item["resume_profile_id"])
        chunks = agent.get_candidate_chunk(item["resume_profile_id"], limit=5)
        chunk_text = " ".join(chunk["content"] for chunk in chunks)
        profile_text = " ".join(
            _unique_texts(
                [
                    profile.get("latest_title"),
                    profile.get("latest_company"),
                    profile.get("city"),
                    " ".join(profile.get("skills", [])),
                    " ".join(profile.get("industry_tags", [])),
                    _flatten_text(profile.get("raw_profile")),
                ]
            )
        ).lower()
        matched_evidence = list(item.get("matched_evidence", []))
        for must in intent.must_have[:6]:
            synonyms = self._synonym_terms(must)
            if any(term.lower() in profile_text for term in synonyms):
                matched_evidence.append(f"命中要求：{must}")
        matched_evidence = _unique_texts(matched_evidence)[:3]
        gaps: list[str] = []
        risk_flags: list[str] = []
        if intent.years_min is not None and self._safe_float(profile.get("years_experience")) < float(intent.years_min):
            gaps.append(f"工作年限不足 {intent.years_min} 年")
        if intent.education_min and _education_rank(profile.get("education_level")) < _education_rank(intent.education_min):
            gaps.append(f"学历低于 {intent.education_min}")
        for must in intent.must_have[:6]:
            synonyms = self._synonym_terms(must)
            if not any(term.lower() in profile_text for term in synonyms):
                gaps.append(f"缺少关键条件：{must}")
        if intent.exclude:
            for blocked in intent.exclude:
                if blocked.lower() in profile_text:
                    risk_flags.append(f"命中排除条件：{blocked}")
        if not matched_evidence:
            matched_evidence = [_trim_snippet(self._compose_summary(profile))]
        fit_score = self._estimate_fit_score(profile, intent, matched_evidence, gaps)
        final_score = round(0.6 * fit_score + 0.4 * float(item.get("retrieval_score", 0.0) * 100), 2)
        if risk_flags or not item.get("hard_filter_pass", True):
            final_recommendation = "reject"
        elif final_score >= 75:
            final_recommendation = "recommend"
        elif final_score >= 55:
            final_recommendation = "review"
        else:
            final_recommendation = "reject"
        if len(gaps) >= 2 and final_recommendation == "recommend":
            final_recommendation = "review"
        interview_questions = self._build_interview_questions(intent, gaps, profile)
        return {
            **item,
            "fit_score": round(fit_score, 2),
            "final_score": final_score,
            "matched_evidence": matched_evidence[:3],
            "gaps": _unique_texts(gaps)[:3],
            "risk_flags": _unique_texts(risk_flags)[:3],
            "interview_questions": interview_questions[:3],
            "final_recommendation": final_recommendation,
            "explanation_status": "completed",
        }

    def _estimate_fit_score(
        self,
        profile: dict[str, Any],
        intent: SearchIntent,
        matched_evidence: list[str],
        gaps: list[str],
    ) -> float:
        must_score = 100.0 if not intent.must_have else 100.0 * (1 - (len(gaps) / max(len(intent.must_have), 1)))
        location_score = 100.0 if not intent.location else (100.0 if _contains_text(profile.get("city"), intent.location) else 0.0)
        years_score = 100.0
        if intent.years_min is not None:
            candidate_years = self._safe_float(profile.get("years_experience"))
            years_score = min(100.0, 100.0 * (candidate_years / max(float(intent.years_min), 0.1)))
        education_score = 100.0
        if intent.education_min:
            education_score = 100.0 if _education_rank(profile.get("education_level")) >= _education_rank(intent.education_min) else 20.0
        evidence_score = min(100.0, len(matched_evidence) * 30.0)
        return max(0.0, min(100.0, 0.4 * must_score + 0.2 * location_score + 0.15 * years_score + 0.1 * education_score + 0.15 * evidence_score))

    def _build_interview_questions(self, intent: SearchIntent, gaps: list[str], profile: dict[str, Any]) -> list[str]:
        questions = []
        for gap in gaps[:2]:
            if "关键条件" in gap:
                target = gap.split("：", 1)[-1]
                questions.append(f"请具体说明你在 {target} 上的真实项目经验和负责深度。")
            elif "工作年限" in gap:
                questions.append("请按时间线拆解近三年的项目经历，说明你独立负责的测试或开发范围。")
            elif "学历" in gap:
                questions.append("请补充学历背景、毕业时间以及是否有可替代该门槛的核心项目经验。")
        if not questions and intent.skills:
            questions.append(f"请举一个与你最匹配的 {intent.skills[0]} 相关项目，说明你解决过的复杂问题。")
        if not questions:
            questions.append("请介绍一个最能证明你与该 JD 匹配的项目，并说明量化结果。")
        return questions

    def _try_rerank_with_local_model(
        self,
        intent: SearchIntent,
        base_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        if not self._local_llm_enabled():
            return None
        compact_candidates = []
        rerank_limit = self._effective_rerank_limit()
        for item in base_results[:rerank_limit]:
            profile = self.get_search_profile(item["resume_profile_id"])
            candidate_summary = {
                "resume_profile_id": item["resume_profile_id"],
                "candidate_id": item.get("source_candidate_id"),
                "name": profile.get("name"),
                "latest_title": profile.get("latest_title"),
                "latest_company": profile.get("latest_company"),
                "city": profile.get("city"),
                "years_experience": profile.get("years_experience"),
                "education_level": profile.get("education_level"),
                "skills": profile.get("skills", [])[:8],
                "industry_tags": profile.get("industry_tags", [])[:4],
                "matched_evidence": item.get("matched_evidence", [])[:2],
                "summary": _trim_snippet(_flatten_text(profile.get("raw_profile")), 160),
                "retrieval_score": item.get("retrieval_score", 0.0),
            }
            compact_candidates.append(
                {
                    "id": candidate_summary["resume_profile_id"],
                    "title": candidate_summary["latest_title"],
                    "years": candidate_summary["years_experience"],
                    "edu": candidate_summary["education_level"],
                    "city": candidate_summary["city"],
                    "skills": candidate_summary["skills"],
                    "industry": candidate_summary["industry_tags"],
                    "summary": candidate_summary["summary"],
                }
            )
        batch_size = 4 if self._openai_compatible_llm_config() is not None else max(len(compact_candidates), 1)
        payload_map: dict[str, dict[str, Any]] = {}
        for start in range(0, len(compact_candidates), batch_size):
            batch = compact_candidates[start : start + batch_size]
            payload = self._generate_local_llm_json(
                system_prompt=(
                    "你是招聘搜索重排器。"
                    "请根据 query_intent 和候选人摘要，输出严格JSON数组，不要输出任何额外说明。"
                ),
                user_prompt=(
                    "query_intent:\n"
                    f"{json.dumps(intent.to_dict(), ensure_ascii=False)}\n\n"
                    "candidates:\n"
                    f"{json.dumps(batch, ensure_ascii=False)}\n\n"
                    "数组中每个对象字段固定为 "
                    "resume_profile_id, fit_score, hard_filter_pass, matched_evidence, gaps, "
                    "risk_flags, interview_questions, final_recommendation。\n"
                    "要求：fit_score 输出 0-100 数字；"
                    "matched_evidence/gaps/risk_flags/interview_questions 最多各 2 条；"
                    "每条尽量短；final_recommendation 只能是 recommend/review/reject。"
                ),
                max_new_tokens=480 if self._openai_compatible_llm_config() is not None else 1200,
                expected_type="array",
            )
            if not isinstance(payload, list):
                continue
            for llm_item in payload:
                if not isinstance(llm_item, dict) or not llm_item.get("resume_profile_id"):
                    continue
                payload_map[str(llm_item.get("resume_profile_id"))] = llm_item
        if not payload_map:
            return None
        reranked = []
        for item in base_results[:rerank_limit]:
            llm_item = payload_map.get(item["resume_profile_id"])
            if not llm_item:
                reranked.append(self._heuristic_rerank(intent, item))
                continue
            fit_score = self._safe_float(llm_item.get("fit_score"))
            if 0.0 < fit_score <= 1.0:
                fit_score *= 100.0
            fit_score = max(0.0, min(100.0, fit_score))
            reranked.append(
                {
                    **item,
                    "fit_score": round(fit_score, 2),
                    "final_score": round(0.6 * fit_score + 0.4 * float(item.get("retrieval_score", 0.0) * 100), 2),
                    "hard_filter_pass": _safe_bool(llm_item.get("hard_filter_pass", item.get("hard_filter_pass", True))),
                    "matched_evidence": _text_list(llm_item.get("matched_evidence") or item.get("matched_evidence", []))[:3],
                    "gaps": _text_list(llm_item.get("gaps"))[:3],
                    "risk_flags": _text_list(llm_item.get("risk_flags"))[:3],
                    "interview_questions": _text_list(llm_item.get("interview_questions"))[:3],
                    "final_recommendation": llm_item.get("final_recommendation") or item.get("final_recommendation"),
                    "explanation_status": "completed",
                }
            )
        return reranked

    def _finalize_without_explain(self, run_id: str, started_ms: int) -> None:
        run = self.get_search_run(run_id)
        results = []
        for item in run.get("results", []):
            results.append(
                {
                    **item,
                    "explanation_status": "skipped",
                    "final_recommendation": "review" if item.get("hard_filter_pass") else "reject",
                }
            )
        self._replace_search_results(run_id, results)
        self._update_search_run(
            run_id,
            status="completed",
            degraded=run.get("degraded", []),
            model_summary={"provider": "none", "model": None, "explain_requested": False},
            retrieval_latency_ms=int(run.get("retrieval_latency_ms") or 0),
            total_latency_ms=_now_ms() - started_ms,
            rerank_latency_ms=0,
        )

    def _format_search_result_row(self, row: dict[str, Any]) -> dict[str, Any]:
        resume_entry = loads(row["raw_resume_entry"]) or {}
        matched_evidence = loads(row["matched_evidence"]) or []
        gaps = loads(row["gaps"]) or []
        risk_flags = loads(row["risk_flags"]) or []
        interview_questions = loads(row["interview_questions"]) or []
        return {
            "rank": row["rank"],
            "resume_profile_id": row["resume_profile_id"],
            "candidate_id": row.get("source_candidate_id") or row["resume_profile_id"],
            "source_candidate_id": row.get("source_candidate_id"),
            "name": row.get("name"),
            "city": row.get("city"),
            "years_experience": row.get("years_experience"),
            "education_level": row.get("education_level"),
            "latest_title": row.get("latest_title"),
            "latest_company": row.get("latest_company"),
            "retrieval_score": round(float(row.get("retrieval_score") or 0.0), 6),
            "fit_score": None if row.get("fit_score") is None else round(float(row["fit_score"]), 2),
            "total_score": round(float(row.get("final_score") or 0.0), 2),
            "hard_filter_pass": bool(row.get("hard_filter_pass")),
            "matched_evidence": matched_evidence[:3],
            "gaps": gaps[:3],
            "risk_flags": risk_flags[:3],
            "interview_questions": interview_questions[:3],
            "final_recommendation": row.get("final_recommendation"),
            "explanation_status": row.get("explanation_status"),
            "resume_entry": resume_entry,
        }

    def _sync_vector_store(self, chunk_records: list[dict[str, Any]], deleted_chunk_ids: list[str]) -> list[str]:
        client_bundle = self._qdrant_bundle()
        if client_bundle is None:
            return ["vector_store_fallback"]
        client, models = client_bundle
        collection_ready = self._ensure_qdrant_collection(client, models)
        if not collection_ready:
            return ["vector_store_fallback"]
        points = []
        vectors = self._encode_texts(
            [str(chunk.get("text") or chunk.get("content") or "") for chunk in chunk_records],
            is_query=False,
            degraded=[],
        )
        if len(vectors) != len(chunk_records):
            return ["vector_store_fallback"]
        for chunk, vector in zip(chunk_records, vectors):
            points.append(
                models.PointStruct(
                    id=chunk["id"],
                    vector=vector,
                    payload={
                        "resume_profile_id": chunk["resume_profile_id"],
                        "source_candidate_id": chunk.get("source_candidate_id"),
                        "chunk_type": chunk.get("chunk_type"),
                        "text": chunk.get("text") or chunk.get("content"),
                        "title": chunk.get("title"),
                        "city": chunk.get("city"),
                        "experience_years": chunk.get("experience_years"),
                        "skills": chunk.get("skills", []),
                    },
                )
            )
        try:
            if deleted_chunk_ids:
                client.delete(collection_name=VECTOR_COLLECTION_NAME, points_selector=models.PointIdsList(points=deleted_chunk_ids))
            if points:
                client.upsert(collection_name=VECTOR_COLLECTION_NAME, points=points)
        except Exception:
            return ["vector_store_fallback"]
        return []

    def _vector_search_via_qdrant(self, query_vector: list[float], allowed_profile_ids: set[str]) -> list[dict[str, Any]] | None:
        client_bundle = self._qdrant_bundle()
        if client_bundle is None:
            return None
        client, models = client_bundle
        if not self._ensure_qdrant_collection(client, models):
            return None
        try:
            if hasattr(client, "search"):
                hits = client.search(
                    collection_name=VECTOR_COLLECTION_NAME,
                    query_vector=query_vector,
                    limit=INITIAL_RECALL_LIMIT,
                )
            else:
                response = client.query_points(
                    collection_name=VECTOR_COLLECTION_NAME,
                    query=query_vector,
                    limit=INITIAL_RECALL_LIMIT,
                    with_payload=True,
                    with_vectors=False,
                )
                hits = getattr(response, "points", response)
        except Exception:
            return None
        results = []
        for hit in hits:
            payload = hit.payload or {}
            profile_id = payload.get("resume_profile_id")
            if profile_id not in allowed_profile_ids:
                continue
            results.append(
                {
                    "resume_profile_id": profile_id,
                    "source_candidate_id": payload.get("source_candidate_id"),
                    "chunk_id": str(hit.id),
                    "snippet": _trim_snippet(payload.get("text", "")),
                    "score": float(hit.score),
                }
            )
        return results

    def _qdrant_bundle(self):
        if isinstance(self._qdrant_state, tuple):
            return self._qdrant_state
        if self._qdrant_state is False:
            return None
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
        except Exception:
            self._qdrant_state = False
            return None
        with self._qdrant_lock:
            if isinstance(self._qdrant_state, tuple):
                return self._qdrant_state
            if self._qdrant_state is False:
                return None
            try:
                qdrant_path = os.getenv("SCREENING_SEARCH_QDRANT_PATH", "").strip()
                if qdrant_path:
                    data_dir = Path(qdrant_path).expanduser().resolve()
                    data_dir.mkdir(parents=True, exist_ok=True)
                    client = QdrantClient(path=str(data_dir))
                else:
                    qdrant_url = os.getenv("SCREENING_SEARCH_QDRANT_URL", DEFAULT_QDRANT_URL).strip() or DEFAULT_QDRANT_URL
                    qdrant_api_key = os.getenv("SCREENING_SEARCH_QDRANT_API_KEY", "").strip() or None
                    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            except Exception:
                self._qdrant_state = False
                return None
            self._qdrant_state = (client, models)
        return self._qdrant_state

    def _ensure_qdrant_collection(self, client, models) -> bool:
        try:
            existing = {item.name for item in client.get_collections().collections}
            if VECTOR_COLLECTION_NAME not in existing:
                client.create_collection(
                    collection_name=VECTOR_COLLECTION_NAME,
                    vectors_config=models.VectorParams(size=self._embed_dim(), distance=models.Distance.COSINE),
                )
                return True
            current = client.get_collection(VECTOR_COLLECTION_NAME)
            current_size = self._collection_vector_size(current)
            if current_size is not None and current_size != self._embed_dim():
                return False
        except Exception:
            return False
        return True

    def _recreate_qdrant_collection(self, client, models) -> bool:
        try:
            existing = {item.name for item in client.get_collections().collections}
            if VECTOR_COLLECTION_NAME in existing:
                client.delete_collection(VECTOR_COLLECTION_NAME)
            client.create_collection(
                collection_name=VECTOR_COLLECTION_NAME,
                vectors_config=models.VectorParams(size=self._embed_dim(), distance=models.Distance.COSINE),
            )
        except Exception:
            return False
        return True

    def _collection_vector_size(self, collection_info: Any) -> int | None:
        config = getattr(collection_info, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None)
        if isinstance(vectors, dict):
            for value in vectors.values():
                size = getattr(value, "size", None)
                if isinstance(size, int):
                    return size
            return None
        size = getattr(vectors, "size", None)
        return size if isinstance(size, int) else None

    def _embed_dim(self) -> int:
        dimension = getattr(self.embedder, "dimension", None)
        if isinstance(dimension, int) and dimension > 0:
            return dimension
        return HASH_EMBED_DIM

    def _llm_bundle(self):
        if not self._local_llm_enabled():
            return None
        if self._openai_compatible_llm_config() is not None:
            return None
        if isinstance(self._llm_state, tuple):
            return self._llm_state
        if self._llm_state is False:
            return None
        with self._llm_lock:
            if isinstance(self._llm_state, tuple):
                return self._llm_state
            if self._llm_state is False:
                return None
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                model_ref = os.getenv("SCREENING_SEARCH_NANBEIGE_MODEL", "Nanbeige/Nanbeige4.1-3B")
                quantization_config = None
                try:
                    from transformers import BitsAndBytesConfig

                    quantization_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=getattr(torch, "float16"),
                    )
                except Exception:
                    quantization_config = None
                tokenizer = AutoTokenizer.from_pretrained(
                    model_ref,
                    trust_remote_code=True,
                    use_fast=False,
                )
                model = AutoModelForCausalLM.from_pretrained(
                    model_ref,
                    trust_remote_code=True,
                    device_map="auto",
                    quantization_config=quantization_config,
                )
                self._llm_state = (tokenizer, model)
            except Exception:
                self._llm_state = False
                return None
        return self._llm_state if isinstance(self._llm_state, tuple) else None

    def _generate_local_llm_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
        expected_type: str | None = None,
    ) -> Any:
        remote_payload = self._generate_openai_compatible_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_new_tokens=max_new_tokens,
            expected_type=expected_type,
        )
        if remote_payload is not None:
            return remote_payload
        bundle = self._llm_bundle()
        if bundle is None:
            return None
        tokenizer, model = bundle
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prefill = _llm_json_prefill(expected_type)
        if prefill:
            messages.append({"role": "assistant", "content": prefill})
        if hasattr(tokenizer, "apply_chat_template"):
            prompt = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=False,
            )
        else:
            prompt = system_prompt + "\n\n" + user_prompt + "\n\n只输出JSON。"
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        attention_mask = inputs.get("attention_mask")
        device = getattr(model, "device", None)
        if device is not None:
            input_ids = input_ids.to(device)
            if attention_mask is not None:
                attention_mask = attention_mask.to(device)
        generation = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=getattr(tokenizer, "eos_token_id", None),
        )
        output = generation[0][input_ids.shape[-1] :]
        text = tokenizer.decode(output, skip_special_tokens=True)
        return _extract_json_blob(text)

    def _openai_compatible_llm_config(self) -> dict[str, str] | None:
        if not self._local_llm_enabled():
            return None
        base_url = (
            os.getenv("SCREENING_SEARCH_OPENAI_BASE_URL")
            or os.getenv("SCREENING_SEARCH_LLM_BASE_URL")
            or ""
        ).strip()
        api_key = (
            os.getenv("SCREENING_SEARCH_OPENAI_API_KEY")
            or os.getenv("SCREENING_SEARCH_LLM_API_KEY")
            or ""
        ).strip()
        model = (
            os.getenv("SCREENING_SEARCH_OPENAI_MODEL")
            or os.getenv("SCREENING_SEARCH_NANBEIGE_MODEL")
            or ""
        ).strip()
        if not base_url or not api_key or not model:
            return None
        return {
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "model": model,
        }

    def _llm_provider_label(self) -> str:
        if self._openai_compatible_llm_config() is not None:
            return "openai_compatible"
        return "transformers"

    def _llm_model_label(self) -> str:
        config = self._openai_compatible_llm_config()
        if config is not None:
            return config["model"]
        return os.getenv("SCREENING_SEARCH_NANBEIGE_MODEL", "Nanbeige/Nanbeige4.1-3B")

    def _generate_openai_compatible_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int,
        expected_type: str | None,
    ) -> Any:
        config = self._openai_compatible_llm_config()
        if config is None:
            return None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prefill = _llm_json_prefill(expected_type)
        if prefill:
            messages.append({"role": "assistant", "content": prefill})
        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_new_tokens,
            "stream": False,
            "response_format": {"type": "json_object"} if expected_type == "object" else None,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        request = urllib.request.Request(
            f"{config['base_url']}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError):
            return None
        try:
            response_payload = json.loads(body)
        except Exception:
            return None
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(str(block.get("text") or "") for block in content if isinstance(block, dict))
        else:
            text = str(content or "")
        parsed = _extract_json_blob(text)
        if parsed is not None:
            return parsed
        reasoning_text = str(message.get("reasoning_content") or "")
        return _extract_json_blob(reasoning_text)

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value) if value is not None and value != "" else 0.0
        except Exception:
            return 0.0
