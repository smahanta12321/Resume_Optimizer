"""Structured JD analysis schemas.

An analysis is a reviewable draft derived from a job's JD text. It is never a
source of truth about the candidate. It only describes what the job asks for.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from src.schemas.profile import _Strict, utc_now


def new_requirement_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


class RequirementCategory(str, Enum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"
    QUALIFICATION = "qualification"
    DOMAIN = "domain"


class Importance(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNSPECIFIED = "unspecified"


class Origin(str, Enum):
    PARSER = "parser"
    USER = "user"


class WorkArrangement(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNSPECIFIED = "unspecified"


class Requirement(_Strict):
    id: str = Field(default_factory=new_requirement_id)
    text: str = Field(min_length=1, description="The requirement as stated or summarized")
    normalized_term: str = Field(default="", description="Canonical term, e.g. 'Kubernetes' for 'k8s'")
    category: RequirementCategory = RequirementCategory.QUALIFICATION
    importance: Importance = Importance.UNSPECIFIED
    source_excerpt: str = Field(default="", description="JD text this requirement was taken from")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: Origin = Origin.PARSER
    min_years: Optional[float] = Field(default=None, ge=0, le=60)
    max_years: Optional[float] = Field(default=None, ge=0, le=60)

    @model_validator(mode="after")
    def _years_order(self) -> "Requirement":
        if self.min_years is not None and self.max_years is not None and self.max_years < self.min_years:
            raise ValueError(f"max_years {self.max_years} is below min_years {self.min_years}")
        return self


class JDAnalysis(_Strict):
    job_id: str = Field(min_length=1)
    parser: str = Field(default="rules-v1", description="Which parser produced the first draft")
    jd_hash: str = Field(description="Hash of the JD text analyzed; a mismatch means the analysis is stale")
    work_arrangement: WorkArrangement = WorkArrangement.UNSPECIFIED
    experience_min_years: Optional[float] = Field(default=None, ge=0, le=60)
    experience_max_years: Optional[float] = Field(default=None, ge=0, le=60)
    requirements: list[Requirement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="Parser notes, e.g. embedded AI instructions")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    confirmed_at: Optional[datetime] = Field(default=None, description="When the user reviewed and confirmed")

    @model_validator(mode="after")
    def _check(self) -> "JDAnalysis":
        lo, hi = self.experience_min_years, self.experience_max_years
        if lo is not None and hi is not None and hi < lo:
            raise ValueError(f"experience max ({hi}) is below min ({lo})")
        ids = [r.id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate requirement IDs")
        return self

    def by_category(self, category: RequirementCategory) -> list[Requirement]:
        return [r for r in self.requirements if r.category is category]
