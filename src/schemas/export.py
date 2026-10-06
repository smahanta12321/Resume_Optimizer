"""Export record: the files produced for an approved resume version and their validation results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from src.schemas.profile import _Strict, utc_now


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ExportCheck(_Strict):
    file: str = Field(description="'docx', 'pdf' or 'both'")
    name: str
    status: CheckStatus
    detail: str = ""


class ExportRecord(_Strict):
    version_id: str
    job_id: str
    renderer: str = "classic-v1"
    page_size: str = "A4"
    pdf_font: str = ""
    docx_path: str
    pdf_path: str
    pdf_pages: Optional[int] = None
    target_pages: int = 1
    checks: list[ExportCheck] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def failed(self) -> list[ExportCheck]:
        return [c for c in self.checks if c.status is CheckStatus.FAIL]

    @property
    def warnings(self) -> list[ExportCheck]:
        return [c for c in self.checks if c.status is CheckStatus.WARN]
