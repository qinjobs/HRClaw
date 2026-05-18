from __future__ import annotations

from pathlib import Path
from typing import Any

from ..phase2_imports import ResumeDocumentParser, build_resume_profile_from_text
from .models import EmailResumeFile


class EmailResumeImporter:
    def __init__(self, *, parser: ResumeDocumentParser | None = None) -> None:
        self.parser = parser or ResumeDocumentParser()

    def import_file(
        self,
        *,
        file_ref: EmailResumeFile,
        file_sha1: str,
        source: str,
        source_candidate_id: str,
        raw_resume_entry: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str]:
        text = self.parser.extract_text(Path(file_ref.file_path))
        profile = build_resume_profile_from_text(
            external_id=file_sha1,
            source_candidate_id=source_candidate_id,
            filename=file_ref.file_name,
            text=text,
            source=source,
            file_path=Path(file_ref.file_path),
            raw_resume_entry=raw_resume_entry or {},
        )
        return profile, text

