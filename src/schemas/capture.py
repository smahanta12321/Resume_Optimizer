"""A job description captured by the optional browser extension, awaiting the user's review.

Everything here is untrusted page content. It becomes a job only after the user
reviews it on the Job Import page.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from src.schemas.job import MAX_JD_CHARS
from src.schemas.profile import _Strict, utc_now


def new_capture_id() -> str:
    return f"cap-{uuid.uuid4().hex[:8]}"


class CaptureIn(_Strict):
    """Request body accepted from the extension. Unknown fields are rejected."""

    url: str = Field(default="", max_length=2048)
    page_title: str = Field(default="", max_length=300)
    title: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=MAX_JD_CHARS)
    method: Literal["selection", "structured", "page", "edited"] = "edited"
    extension_version: str = Field(default="", max_length=20)

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("url must be an http(s) address")
        return v


class Capture(CaptureIn):
    id: str = Field(default_factory=new_capture_id)
    received_at: datetime = Field(default_factory=utc_now)
