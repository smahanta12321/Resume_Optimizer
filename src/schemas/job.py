"""Job record schemas.

A job stores the extracted JD text and where it came from — never full page
HTML. Structured requirements are added by JD analysis (Milestone 3).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator

from src.schemas.profile import _Strict, utc_now

MAX_JD_CHARS = 50_000  # far longer than any real JD; guards storage and later LLM cost


def new_job_id() -> str:
    return f"job-{uuid.uuid4().hex[:8]}"


class SourcePlatform(str, Enum):
    LINKEDIN = "linkedin"
    NAUKRI = "naukri"
    OTHER = "other"


class ImportMethod(str, Enum):
    PASTE = "paste"
    FILE = "file"
    URL = "url"
    EXTENSION = "extension"  # captured by the optional browser extension, then reviewed by the user


class JobStatus(str, Enum):
    """User-selected application status. The app never applies on the user's behalf."""

    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class Job(_Strict):
    id: str = Field(default_factory=new_job_id)
    source_platform: SourcePlatform = SourcePlatform.OTHER
    import_method: ImportMethod = ImportMethod.PASTE
    source_url: str = ""
    canonical_url: str = Field(default="", description="Normalized URL used for deduplication")
    source_label: str = Field(default="", description="User-provided note, e.g. 'LinkedIn saved jobs'")
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = Field(min_length=1, max_length=MAX_JD_CHARS, description="Extracted JD text (untrusted)")
    import_notes: list[str] = Field(
        default_factory=list, description="Warnings from import, e.g. 'extraction may be incomplete'"
    )
    status: JobStatus = JobStatus.SAVED
    notes: str = ""
    applied_on: Optional[date] = Field(default=None, description="When the user applied (entered by the user)")
    follow_up_on: Optional[date] = Field(default=None, description="Optional reminder date")
    resume_version_id: Optional[str] = Field(default=None, description="Resume version used for this application")
    imported_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("job description text is empty")
        return v

    @property
    def display_name(self) -> str:
        parts = [self.title or "Untitled role", self.company]
        return " @ ".join(p for p in parts if p)
