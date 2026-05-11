from __future__ import annotations

import os
import re
from pathlib import Path

from .models import EmailResumeFile


DATE_DIR_RE = re.compile(r"^\d{8}$")
SUPPORTED_RESUME_SUFFIXES = {".pdf", ".doc", ".docx"}


class EmailResumeScanner:
    def __init__(self, *, root_dir: str | Path | None = None) -> None:
        env_root = os.getenv("SCREENING_EMAIL_RESUME_ROOT", "/data/email")
        self.root_dir = Path(root_dir or env_root).expanduser()

    def scan_user(self, user_id: str, *, limit: int | None = None, ingest_directory: str | None = None) -> list[EmailResumeFile]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return []
        user_root = self._resolve_user_root(normalized_user_id, ingest_directory=ingest_directory)
        if not user_root.exists() or not user_root.is_dir():
            return []

        results: list[EmailResumeFile] = []
        for date_dir in self._iter_date_dirs(user_root):
            for path in sorted(date_dir.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_RESUME_SUFFIXES:
                    continue
                stat = path.stat()
                results.append(
                    EmailResumeFile(
                        user_id=normalized_user_id,
                        source_date=date_dir.name,
                        file_path=path,
                        file_name=path.name,
                        file_size=int(stat.st_size or 0),
                        modified_at=float(stat.st_mtime or 0.0),
                    )
                )
        results.sort(key=lambda item: (item.source_date, item.modified_at, item.file_name))
        if limit is not None and limit > 0:
            return results[: int(limit)]
        return results

    def _resolve_user_root(self, user_id: str, *, ingest_directory: str | None = None) -> Path:
        configured_directory = str(ingest_directory or "").strip()
        if not configured_directory:
            return self.root_dir / user_id
        normalized = configured_directory.replace("{user_id}", user_id)
        candidate = Path(normalized).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.root_dir / candidate).resolve()

    @staticmethod
    def _iter_date_dirs(user_root: Path) -> list[Path]:
        if DATE_DIR_RE.fullmatch(user_root.name):
            return [user_root]
        date_dirs: list[Path] = []
        for item in sorted(user_root.iterdir(), key=lambda path: path.name):
            if item.is_dir() and DATE_DIR_RE.fullmatch(item.name):
                date_dirs.append(item)
        return date_dirs
