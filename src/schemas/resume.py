"""Tailored resume schemas.

A resume version is an immutable snapshot built from master-profile evidence.
Every bullet, skill and summary carries the evidence IDs it rests on; factual
fields (titles, employers, dates, degrees) are copied from the profile and
never generated. Approval is recorded on the version, never by editing it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from src.schemas.profile import Contact, TargetLength, _Strict, utc_now


def new_resume_id() -> str:
    return f"res-{uuid.uuid4().hex[:8]}"


class TextOrigin(str, Enum):
    VERBATIM = "verbatim"      # copied unchanged from the master profile
    REWRITTEN = "rewritten"    # rewritten by the configured LLM and passed the claim checks
    USER_EDIT = "user_edit"    # edited by the user in the builder


class ResumeBullet(_Strict):
    evidence_ids: list[str] = Field(min_length=1, description="Profile evidence this bullet states")
    text: str = Field(min_length=1)
    source_text: str = Field(description="The master-profile text this bullet comes from")
    origin: TextOrigin = TextOrigin.VERBATIM
    notes: list[str] = Field(default_factory=list, description="Checker notes, e.g. a rejected rewrite")


class ResumeSummary(_Strict):
    text: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    origin: TextOrigin = TextOrigin.VERBATIM
    notes: list[str] = Field(default_factory=list)


class ResumeSkill(_Strict):
    name: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ResumeEntry(_Strict):
    """An experience or project. Header fields are copied from the profile, never generated."""

    evidence_id: str = Field(min_length=1)
    kind: str = Field(pattern="^(experience|project)$")
    title: str  # job title / project name
    organization: str = ""  # employer / project role
    location: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: list[ResumeBullet] = Field(default_factory=list)


class ResumeEducation(_Strict):
    evidence_id: str
    degree: str
    field_of_study: str = ""
    institution: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ResumeCertification(_Strict):
    evidence_id: str
    name: str
    issuer: str = ""
    issue_date: Optional[str] = None


class ResumeContent(_Strict):
    contact: Contact
    headline: str = ""
    summary: ResumeSummary = Field(default_factory=ResumeSummary)
    skills: list[ResumeSkill] = Field(default_factory=list)
    experience: list[ResumeEntry] = Field(default_factory=list)
    projects: list[ResumeEntry] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[ResumeCertification] = Field(default_factory=list)

    def evidence_map(self) -> dict[str, list[str]]:
        """Resume line -> evidence IDs, for display and traceability."""
        out: dict[str, list[str]] = {}
        if self.summary.text:
            out[f"Summary: {self.summary.text[:60]}"] = self.summary.evidence_ids
        for s in self.skills:
            out[f"Skill: {s.name}"] = s.evidence_ids
        for e in [*self.experience, *self.projects]:
            for b in e.bullets:
                out[f"{e.title}: {b.text[:60]}"] = b.evidence_ids
        return out


class ResumeVersion(_Strict):
    id: str = Field(default_factory=new_resume_id)
    job_id: str = Field(min_length=1)
    parent_id: Optional[str] = Field(default=None, description="Version this one was edited from")
    profile_version: int = Field(ge=1)
    match_profile_version: int = Field(ge=1, description="Profile version the match report used")
    role_profile_id: Optional[str] = None
    target_pages: TargetLength = TargetLength.ONE_PAGE
    generator: str = Field(description="'deterministic', 'llm:<provider>/<model>', or 'user_edit'")
    content: ResumeContent
    omitted: list[str] = Field(default_factory=list, description="What was left out and why")
    created_at: datetime = Field(default_factory=utc_now)
    approved_at: Optional[datetime] = None
    approval_note: str = ""
