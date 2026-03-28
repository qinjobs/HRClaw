from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

from .candidate_heuristics import extract_education_level, extract_years_experience
from .phase2_repositories import create_resume_import_batch, finalize_resume_import_batch, insert_resume_import_result
from .phase2_scorecards import score_phase2_resume
from .search_service import KNOWN_INDUSTRIES, KNOWN_LOCATIONS, KNOWN_SKILLS, KNOWN_TITLES, ResumeSearchService


def _unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(text)
    return items


def _safe_filename(name: str) -> str:
    original = Path(str(name or "resume")).name
    safe = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", original).strip("._")
    return safe or "resume"


def _normalize_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_ocr_text(text: str, source_path: Path) -> str:
    raw = _normalize_text(text)
    if not raw:
        return ""
    ignored_exact = {
        str(source_path),
        source_path.name,
        "min",
        "general",
    }
    cleaned_lines: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if line in ignored_exact or lowered in {item.lower() for item in ignored_exact}:
            continue
        if lowered.endswith((".ttf", ".otf")):
            continue
        if lowered.startswith(("/users/", "/var/", "c:\\", "file://")):
            continue
        cleaned_lines.append(line)
    return _normalize_text("\n".join(cleaned_lines))


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "off", "no"}


def _docx_text_from_zip(file_path: Path) -> str:
    with zipfile.ZipFile(file_path) as archive:
        with archive.open("word/document.xml") as handle:
            xml_bytes = handle.read()
    root = ElementTree.fromstring(xml_bytes)
    parts = [node.text or "" for node in root.iter() if node.text]
    return _normalize_text("\n".join(parts))


class PaddleOCRBackend:
    def __init__(self) -> None:
        self._ocr = None
        self._module = None

    @property
    def provider(self) -> str:
        return str(os.getenv("SCREENING_RESUME_OCR_PROVIDER", "auto") or "auto").strip().lower()

    def enabled(self) -> bool:
        if self.provider in {"none", "off", "disabled"}:
            return False
        try:
            self._load_module()
        except Exception:
            return False
        return True

    def unavailable_reason(self) -> str:
        if self.provider in {"none", "off", "disabled"}:
            return "OCR 已关闭"
        try:
            self._load_module()
            return ""
        except Exception as exc:
            return f"PaddleOCR 不可用：{exc}"

    def extract_text(self, file_path: Path) -> str:
        ocr = self._get_ocr()
        results = list(ocr.predict(input=str(file_path)))
        texts = self._collect_texts(results)
        if not texts:
            texts = self._collect_texts_from_saved_json(results)
        merged = _clean_ocr_text("\n".join(_unique_texts(texts)), file_path)
        if not merged:
            raise ValueError("PaddleOCR 未识别出可用文本")
        return merged

    def _load_module(self):
        if self._module is not None:
            return self._module
        self._module = importlib.import_module("paddleocr")
        return self._module

    def _get_ocr(self):
        if self._ocr is not None:
            return self._ocr
        module = self._load_module()
        paddle_ocr_cls = getattr(module, "PaddleOCR", None)
        if paddle_ocr_cls is None:
            raise RuntimeError("paddleocr 模块中不存在 PaddleOCR")
        kwargs: dict[str, Any] = {
            "use_doc_orientation_classify": _env_flag("SCREENING_RESUME_OCR_USE_DOC_ORIENTATION", False),
            "use_doc_unwarping": _env_flag("SCREENING_RESUME_OCR_USE_DOC_UNWARPING", False),
            "use_textline_orientation": _env_flag("SCREENING_RESUME_OCR_USE_TEXTLINE_ORIENTATION", False),
        }
        lang = str(os.getenv("SCREENING_RESUME_OCR_LANG", "ch") or "ch").strip()
        if lang:
            kwargs["lang"] = lang
        det_model_name = str(
            os.getenv("SCREENING_RESUME_OCR_DET_MODEL_NAME", "PP-OCRv5_mobile_det") or "PP-OCRv5_mobile_det"
        ).strip()
        rec_default = "en_PP-OCRv5_mobile_rec" if lang.lower() == "en" else "PP-OCRv5_mobile_rec"
        rec_model_name = str(os.getenv("SCREENING_RESUME_OCR_REC_MODEL_NAME", rec_default) or rec_default).strip()
        if det_model_name:
            kwargs["text_detection_model_name"] = det_model_name
        if rec_model_name:
            kwargs["text_recognition_model_name"] = rec_model_name
        self._ocr = paddle_ocr_cls(**kwargs)
        return self._ocr

    def _collect_texts(self, value: Any, *, depth: int = 0, key_hint: str = "") -> list[str]:
        if depth > 10 or value is None:
            return []
        if isinstance(value, str):
            text = _normalize_text(value)
            if not text:
                return []
            if key_hint and key_hint not in {"text", "rec_text", "transcription", "label", "content", "texts"}:
                if len(text) < 2:
                    return []
            return [text]
        if isinstance(value, (int, float, bool)):
            return []
        if isinstance(value, dict):
            items: list[str] = []
            preferred_keys = ("rec_text", "text", "texts", "transcription", "label", "content")
            for key in preferred_keys:
                if key in value:
                    items.extend(self._collect_texts(value.get(key), depth=depth + 1, key_hint=key))
            for key, item in value.items():
                if key in preferred_keys:
                    continue
                items.extend(self._collect_texts(item, depth=depth + 1, key_hint=str(key)))
            return items
        if isinstance(value, (list, tuple, set)):
            items: list[str] = []
            for item in value:
                items.extend(self._collect_texts(item, depth=depth + 1, key_hint=key_hint))
            return items
        if hasattr(value, "tolist"):
            try:
                return self._collect_texts(value.tolist(), depth=depth + 1, key_hint=key_hint)
            except Exception:
                pass
        for attr in ("res", "data", "result", "json", "_data", "__dict__"):
            if not hasattr(value, attr):
                continue
            try:
                attr_value = getattr(value, attr)
                if callable(attr_value):
                    attr_value = attr_value()
            except Exception:
                continue
            items = self._collect_texts(attr_value, depth=depth + 1, key_hint=attr)
            if items:
                return items
        for method_name in ("to_dict", "as_dict", "to_json", "model_dump"):
            if not hasattr(value, method_name):
                continue
            try:
                method = getattr(value, method_name)
                dumped = method() if callable(method) else method
            except Exception:
                continue
            if isinstance(dumped, str):
                try:
                    dumped = json.loads(dumped)
                except Exception:
                    pass
            items = self._collect_texts(dumped, depth=depth + 1, key_hint=method_name)
            if items:
                return items
        return []

    def _collect_texts_from_saved_json(self, results: list[Any]) -> list[str]:
        texts: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            for index, result in enumerate(results):
                saver = getattr(result, "save_to_json", None)
                if not callable(saver):
                    continue
                before = {path for path in save_dir.rglob("*.json")}
                try:
                    maybe_path = saver(save_path=str(save_dir))
                except Exception:
                    continue
                after = {path for path in save_dir.rglob("*.json")}
                candidates = sorted(after - before)
                if isinstance(maybe_path, str) and maybe_path.endswith(".json"):
                    candidates.append(Path(maybe_path))
                if not candidates:
                    fallback = save_dir / f"{index}.json"
                    if fallback.exists():
                        candidates.append(fallback)
                for candidate in candidates:
                    try:
                        payload = json.loads(candidate.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    texts.extend(self._collect_texts(payload))
        return texts


class ResumeDocumentParser:
    def __init__(self, *, ocr_backend: PaddleOCRBackend | None = None) -> None:
        self.ocr_backend = ocr_backend or PaddleOCRBackend()

    def extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_text(file_path)
        if suffix in {".docx", ".doc"}:
            return self._extract_word_text(file_path)
        if suffix in {".png", ".jpg", ".jpeg"}:
            return self._extract_image_text(file_path)
        if suffix in {".txt", ".md"}:
            return _normalize_text(file_path.read_text(encoding="utf-8", errors="ignore"))
        raise ValueError(f"暂不支持的文件格式：{suffix or 'unknown'}")

    def _extract_pdf_text(self, file_path: Path) -> str:
        extract_errors: list[str] = []
        text = ""
        if PdfReader is not None:
            try:
                reader = PdfReader(str(file_path))
                text_parts: list[str] = []
                for page in reader.pages:
                    try:
                        text_parts.append(page.extract_text() or "")
                    except Exception:
                        continue
                text = _normalize_text("\n".join(text_parts))
            except Exception as exc:
                extract_errors.append(f"pypdf: {exc}")
        else:
            extract_errors.append("pypdf 未安装")
        if text and not _env_flag("SCREENING_RESUME_OCR_FORCE_ON_PDF", False):
            return text
        if self.ocr_backend.enabled():
            ocr_text = self._extract_image_text(file_path)
            if ocr_text:
                return ocr_text
        reason = "; ".join(error for error in extract_errors if error)
        if text:
            return text
        ocr_reason = self.ocr_backend.unavailable_reason()
        if reason and ocr_reason:
            raise ValueError(f"PDF 文本提取失败，且 OCR 不可用：{reason}; {ocr_reason}")
        if reason:
            raise ValueError(f"PDF 文本提取失败：{reason}")
        if ocr_reason:
            raise ValueError(f"PDF 文本为空，且 OCR 不可用：{ocr_reason}")
        raise ValueError("PDF 文本为空，请检查是否为扫描件")

    def _extract_word_text(self, file_path: Path) -> str:
        textutil = shutil_which("textutil")
        if textutil:
            try:
                completed = subprocess.run(
                    [textutil, "-convert", "txt", "-stdout", str(file_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                text = _normalize_text(completed.stdout)
                if text:
                    return text
            except Exception:
                pass
        if file_path.suffix.lower() == ".docx":
            text = _docx_text_from_zip(file_path)
            if text:
                return text
        raise ValueError("Word 文档无法提取文本")

    def _extract_image_text(self, file_path: Path) -> str:
        if not self.ocr_backend.enabled():
            raise ValueError(self.ocr_backend.unavailable_reason() or "OCR 不可用")
        return self.ocr_backend.extract_text(file_path)


def shutil_which(command: str) -> str | None:
    for path in os.getenv("PATH", "").split(os.pathsep):
        candidate = Path(path) / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _extract_name_from_text(text: str, filename: str) -> str:
    explicit = re.search(r"姓名[:：]?\s*([\u4e00-\u9fa5·]{2,8})", text)
    if explicit:
        return explicit.group(1)
    english = re.search(r"(?:name|candidate)[:：]?\s*([A-Za-z][A-Za-z .'-]{1,40})", text, flags=re.IGNORECASE)
    if english:
        return english.group(1).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:8]:
        candidate = line.replace("简历", "").replace("个人简历", "").strip()
        if re.fullmatch(r"[\u4e00-\u9fa5·]{2,8}", candidate):
            return candidate
    stem = Path(filename).stem
    cleaned = re.sub(r"[_\-()\[\]0-9]+", " ", stem).strip()
    return cleaned or stem


def _extract_location(text: str) -> str | None:
    explicit = re.search(r"(?:现居住地|所在地|工作地点|意向城市|城市)[:：]?\s*([^\s，,;；|/]{2,12})", text)
    if explicit:
        return explicit.group(1).strip()
    english = re.search(r"(?:location|city|address)[:：]?\s*([A-Za-z][A-Za-z .'-]{1,30})", text, flags=re.IGNORECASE)
    if english:
        return english.group(1).strip()
    return next((city for city in KNOWN_LOCATIONS if city in text), None)


def _extract_title(text: str) -> str | None:
    explicit = re.search(r"(?:求职意向|意向岗位|应聘职位|目标岗位)[:：]?\s*([^\n]{2,30})", text)
    if explicit:
        return explicit.group(1).strip()
    english = re.search(r"(?:role|title|target role|position)[:：]?\s*([^\n]{2,40})", text, flags=re.IGNORECASE)
    if english:
        return english.group(1).strip()
    lowered = text.lower()
    return next((title for title in KNOWN_TITLES if title.lower() in lowered), None)


def _extract_latest_company(text: str) -> str | None:
    explicit = re.search(r"(?:最近公司|当前公司|就职公司)[:：]?\s*([^\n]{2,40})", text)
    if explicit:
        return explicit.group(1).strip()
    return None


def _extract_terms(text: str, candidates: list[str]) -> list[str]:
    lowered = text.lower()
    return _unique_texts([item for item in candidates if item.lower() in lowered])


def build_import_profile(
    *,
    file_hash: str,
    filename: str,
    file_path: Path,
    batch_id: str,
    text: str,
) -> dict[str, Any]:
    return build_resume_profile_from_text(
        external_id=file_hash,
        source_candidate_id=f"{batch_id}:{file_hash}",
        filename=filename,
        text=text,
        source="resume_import",
        file_path=file_path,
        raw_resume_entry={
            "filename": filename,
            "file_path": str(file_path),
            "batch_id": batch_id,
            "source": "resume_import",
        },
    )


def build_resume_profile_from_text(
    *,
    external_id: str,
    source_candidate_id: str | None,
    filename: str,
    text: str,
    source: str,
    file_path: Path | None = None,
    raw_resume_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_text = _normalize_text(text)
    name = _extract_name_from_text(normalized_text, filename)
    skills = _extract_terms(normalized_text, KNOWN_SKILLS)
    industries = _extract_terms(normalized_text, KNOWN_INDUSTRIES)
    title = _extract_title(normalized_text)
    company = _extract_latest_company(normalized_text)
    entry = dict(raw_resume_entry or {})
    entry.setdefault("filename", filename)
    if file_path is not None:
        entry.setdefault("file_path", str(file_path))
    entry.setdefault("source", source)
    profile = {
        "source": source,
        "external_id": external_id,
        "source_candidate_id": source_candidate_id,
        "name": name,
        "city": _extract_location(normalized_text),
        "years_experience": extract_years_experience(normalized_text),
        "education_level": extract_education_level(normalized_text),
        "latest_title": title,
        "latest_company": company,
        "skills": skills,
        "industry_tags": industries,
        "raw_profile": {
            "summary": normalized_text[:1200],
            "experience": normalized_text,
            "projects": "",
            "skills": skills,
            "education": extract_education_level(normalized_text),
            "raw_resume_text": normalized_text,
        },
        "raw_resume_entry": entry,
    }
    return profile


class ResumeImportService:
    def __init__(
        self,
        *,
        parser: ResumeDocumentParser | None = None,
        search_service: ResumeSearchService | None = None,
    ) -> None:
        self.parser = parser or ResumeDocumentParser()
        self.search_service = search_service or ResumeSearchService()

    def import_base64_batch(
        self,
        *,
        scorecard_id: str,
        scorecard: dict[str, Any],
        files: list[dict[str, Any]],
        batch_name: str = "",
        created_by: str = "hr_ui",
    ) -> dict[str, Any]:
        if not files:
            raise ValueError("files 不能为空")
        batch = create_resume_import_batch(
            scorecard_id=scorecard_id,
            scorecard_name=str(scorecard.get("name") or scorecard_id),
            batch_name=batch_name or f"导入批次-{scorecard.get('name') or scorecard_id}",
            created_by=created_by,
            total_files=len(files),
        )
        batch_id = str(batch["id"])
        upload_dir = Path(__file__).resolve().parents[2] / "data" / "imports" / batch_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        profile_items: list[dict[str, Any]] = []
        pending_results: list[dict[str, Any]] = []
        recommend_count = 0
        review_count = 0
        reject_count = 0

        for file_item in files:
            filename = _safe_filename(str(file_item.get("name") or "resume"))
            content_base64 = str(file_item.get("content_base64") or "").strip()
            if not content_base64:
                raise ValueError(f"{filename} 缺少 content_base64")
            raw_bytes = base64.b64decode(content_base64, validate=True)
            file_hash = hashlib.sha1(raw_bytes).hexdigest()
            target_path = upload_dir / f"{file_hash[:10]}-{filename}"
            target_path.write_bytes(raw_bytes)
            try:
                text = self.parser.extract_text(target_path)
                profile = build_import_profile(
                    file_hash=file_hash,
                    filename=filename,
                    file_path=target_path,
                    batch_id=batch_id,
                    text=text,
                )
                score = score_phase2_resume(scorecard, profile)
                profile_items.append(profile)
                profile_id = f"{profile['source']}:{profile['external_id']}"
                detail = {
                    "profile": profile,
                    "blocked_terms": score.get("blocked_terms") or [],
                    "file_hash": file_hash,
                }
                pending_results.append(
                    {
                        "scorecard_id": scorecard_id,
                        "resume_profile_id": profile_id,
                        "filename": filename,
                        "file_path": str(target_path),
                        "parse_status": "completed",
                        "extracted_name": profile.get("name"),
                        "years_experience": profile.get("years_experience"),
                        "education_level": profile.get("education_level"),
                        "location": profile.get("city"),
                        "total_score": score["total_score"],
                        "decision": score["decision"],
                        "hard_filter_pass": score["hard_filter_pass"],
                        "hard_filter_fail_reasons": score["hard_filter_fail_reasons"],
                        "matched_terms": score["matched_terms"],
                        "missing_terms": score["missing_terms"],
                        "dimension_scores": score["dimension_scores"],
                        "summary": str((profile.get("raw_profile") or {}).get("summary") or "")[:280],
                        "detail": detail,
                    }
                )
                if score["decision"] == "recommend":
                    recommend_count += 1
                elif score["decision"] == "review":
                    review_count += 1
                else:
                    reject_count += 1
            except Exception as exc:
                reject_count += 1
                pending_results.append(
                    {
                        "scorecard_id": scorecard_id,
                        "resume_profile_id": None,
                        "filename": filename,
                        "file_path": str(target_path),
                        "parse_status": "failed",
                        "extracted_name": None,
                        "years_experience": None,
                        "education_level": None,
                        "location": None,
                        "total_score": 0.0,
                        "decision": "reject",
                        "hard_filter_pass": False,
                        "hard_filter_fail_reasons": [str(exc)],
                        "matched_terms": [],
                        "missing_terms": [],
                        "dimension_scores": {},
                        "summary": "解析失败",
                        "detail": {"error": str(exc), "file_hash": file_hash},
                    }
                )

        if profile_items:
            self.search_service.upsert_profiles(items=profile_items)

        stored_results = [insert_resume_import_result(batch_id, payload) for payload in pending_results]
        batch = finalize_resume_import_batch(
            batch_id,
            processed_files=len(stored_results),
            recommend_count=recommend_count,
            review_count=review_count,
            reject_count=reject_count,
            summary={
                "scorecard_name": scorecard.get("name"),
                "indexed_profiles": len(profile_items),
            },
        )
        return {
            "batch": batch,
            "results": stored_results,
        }
