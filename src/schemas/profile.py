"""Master profile schemas.

The master profile is the single source of truth for every resume claim.
Every evidence-bearing item (experience, project, bullet, education,
certification, achievement) carries a stable ID so generated content can be
traced back to it.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Iterator, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

_YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Prefixes make IDs self-describing in evidence maps (e.g. "exp-3f2a9c1b").
ID_PREFIXES = {
    "experience": "exp",
    "project": "prj",
    "bullet": "bul",
    "skill": "skl",
    "education": "edu",
    "certification": "crt",
    "achievement": "ach",
    "link": "lnk",
}


def new_id(kind: str) -> str:
    """Return a new random ID with the prefix registered for ``kind``."""
    return f"{ID_PREFIXES[kind]}-{uuid.uuid4().hex[:8]}"


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def _validate_year_month(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _YEAR_MONTH_RE.match(value):
        raise ValueError(f"date must be in YYYY-MM format, got {value!r}")
    return value


YearMonth = Annotated[Optional[str], AfterValidator(_validate_year_month)]
"""Optional ``YYYY-MM`` date; blank strings normalise to ``None``."""


class _Strict(BaseModel):
    """Base model: reject unknown fields so typos in imported JSON surface as errors."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SkillCategory(str, Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    TOOL = "tool"
    PLATFORM = "platform"
    CONCEPT = "concept"
    SOFT = "soft"
    OTHER = "other"


class VerifiedMetric(_Strict):
    """A quantitative outcome the user has verified. Never generated."""

    label: str = Field(min_length=1, description="What was measured, e.g. 'latency reduction'")
    value: str = Field(min_length=1, description="Verified value as the user states it, e.g. '35%'")
    source_note: str = ""


class Bullet(_Strict):
    """One factual statement about an experience or project."""

    id: str = Field(default_factory=lambda: new_id("bullet"))
    text: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list, description="Skill names this bullet demonstrates")
    source_note: str = ""
    verified_metrics: list[VerifiedMetric] = Field(default_factory=list)


class _Dated(_Strict):
    start_date: YearMonth = None
    end_date: YearMonth = Field(default=None, description="YYYY-MM; empty means current/ongoing")

    @model_validator(mode="after")
    def _end_after_start(self) -> "_Dated":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError(f"end_date {self.end_date} is before start_date {self.start_date}")
        return self

    @property
    def is_current(self) -> bool:
        return bool(self.start_date) and not self.end_date


class Experience(_Dated):
    id: str = Field(default_factory=lambda: new_id("experience"))
    employer: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = ""
    employment_type: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)
    source_note: str = ""


class Project(_Dated):
    id: str = Field(default_factory=lambda: new_id("project"))
    name: str = Field(min_length=1)
    role: str = ""
    description: str = ""
    url: str = ""
    related_experience_id: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)
    source_note: str = ""


class Skill(_Strict):
    """A skill the user has. ``aliases`` are exact alternative spellings
    (e.g. 'k8s' for 'Kubernetes'), NOT related concepts."""

    id: str = Field(default_factory=lambda: new_id("skill"))
    name: str = Field(min_length=1)
    category: SkillCategory = SkillCategory.OTHER
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(
        default_factory=list, description="IDs of experiences/projects/bullets that demonstrate this skill"
    )


class Education(_Dated):
    id: str = Field(default_factory=lambda: new_id("education"))
    institution: str = Field(min_length=1)
    degree: str = Field(min_length=1)
    field_of_study: str = ""
    location: str = ""
    grade: str = ""
    source_note: str = ""


class Certification(_Strict):
    id: str = Field(default_factory=lambda: new_id("certification"))
    name: str = Field(min_length=1)
    issuer: str = ""
    issue_date: YearMonth = None
    expiry_date: YearMonth = None
    credential_url: str = ""
    source_note: str = ""


class Achievement(_Strict):
    id: str = Field(default_factory=lambda: new_id("achievement"))
    title: str = Field(min_length=1)
    description: str = ""
    date: YearMonth = None
    source_note: str = ""
    verified_metrics: list[VerifiedMetric] = Field(default_factory=list)



class Link(_Strict):
    id: str = Field(default_factory=lambda: new_id("link"))
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Contact(_Strict):
    full_name: str = Field(min_length=1)
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[Link] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError(f"email looks invalid: {v!r}")
        return v


class MasterProfile(_Strict):
    """Versioned, validated master profile."""

    schema_version: str = SCHEMA_VERSION
    profile_version: int = Field(default=1, ge=1, description="Incremented on every saved change")
    is_sample: bool = Field(default=False, description="True for fictional sample data")
    contact: Contact
    headline: str = ""
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    confirmed_at: Optional[datetime] = Field(
        default=None, description="When the user last reviewed and confirmed this version"
    )
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _check_ids_and_references(self) -> "MasterProfile":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item_id, _kind, _obj in self.iter_evidence():
            if item_id in seen:
                duplicates.add(item_id)
            seen.add(item_id)
        for skill in self.skills:
            if skill.id in seen:
                duplicates.add(skill.id)
            seen.add(skill.id)
        if duplicates:
            raise ValueError(f"duplicate IDs in profile: {sorted(duplicates)}")

        evidence_ids = {item_id for item_id, _, _ in self.iter_evidence()}
        for skill in self.skills:
            missing = [e for e in skill.evidence_ids if e not in evidence_ids]
            if missing:
                raise ValueError(f"skill {skill.name!r} references unknown evidence IDs: {missing}")

        exp_ids = {e.id for e in self.experience}
        for project in self.projects:
            if project.related_experience_id and project.related_experience_id not in exp_ids:
                raise ValueError(
                    f"project {project.name!r} references unknown experience "
                    f"{project.related_experience_id!r}"
                )

        names = [s.name.casefold() for s in self.skills]
        dup_names = {n for n in names if names.count(n) > 1}
        if dup_names:
            raise ValueError(f"duplicate skill names: {sorted(dup_names)}")
        return self

    def iter_evidence(self) -> Iterator[tuple[str, str, BaseModel]]:
        """Yield ``(id, kind, item)`` for every evidence-bearing item, including bullets."""
        for exp in self.experience:
            yield exp.id, "experience", exp
            for b in exp.bullets:
                yield b.id, "bullet", b
        for prj in self.projects:
            yield prj.id, "project", prj
            for b in prj.bullets:
                yield b.id, "bullet", b
        for edu in self.education:
            yield edu.id, "education", edu
        for crt in self.certifications:
            yield crt.id, "certification", crt
        for ach in self.achievements:
            yield ach.id, "achievement", ach

    def evidence_index(self) -> dict[str, tuple[str, BaseModel]]:
        """Map evidence ID -> (kind, item)."""
        return {item_id: (kind, item) for item_id, kind, item in self.iter_evidence()}


class TargetLength(int, Enum):
    ONE_PAGE = 1
    TWO_PAGES = 2


class RoleProfile(_Strict):
    """A named selection/ordering of master-profile evidence (e.g. 'ML Engineer').

    Holds references only; it is never a competing source of truth.
    """

    id: str = Field(default_factory=lambda: f"role-{uuid.uuid4().hex[:8]}")
    name: str = Field(min_length=1)
    target_role: str = ""
    headline: str = Field(default="", description="Optional headline override; must be supported by the profile")
    evidence_ids: list[str] = Field(default_factory=list, description="Ordered experience/project/bullet IDs")
    skill_ids: list[str] = Field(default_factory=list, description="Ordered skill IDs to emphasise")
    target_pages: TargetLength = TargetLength.ONE_PAGE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def dangling_references(self, profile: MasterProfile) -> list[str]:
        """IDs referenced by this role profile that no longer exist in ``profile``."""
        known = set(profile.evidence_index()) | {s.id for s in profile.skills}
        return [i for i in [*self.evidence_ids, *self.skill_ids] if i not in known]


class RoleProfileLibrary(_Strict):
    schema_version: str = SCHEMA_VERSION
    role_profiles: list[RoleProfile] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique(self) -> "RoleProfileLibrary":
        ids = [r.id for r in self.role_profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate role profile IDs")
        names = [r.name.casefold() for r in self.role_profiles]
        if len(names) != len(set(names)):
            raise ValueError("role profile names must be unique")
        return self
