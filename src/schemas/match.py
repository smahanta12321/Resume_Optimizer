"""Evidence-match schemas: how each JD requirement relates to master-profile evidence.

A match never adds facts. It only points at existing evidence IDs. A user
override may change a status, but ``supported``/``partial`` must still cite
at least one evidence item.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from src.schemas.profile import _Strict, utc_now


class MatchStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_DOCUMENTED = "not_documented"


class MatchType(str, Enum):
    EXACT = "exact"            # same term
    ALIAS = "alias"            # same thing under a recorded alternative name (k8s = Kubernetes)
    RELATED = "related"        # a related but different term (PySpark vs Apache Spark) -> never "supported"
    TEXT = "text_overlap"      # wording overlap between requirement and evidence text
    COMPUTED = "computed"      # derived from structured data (dates, degree level)
    NONE = "none"


class MatchOverride(_Strict):
    status: MatchStatus
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _evidence_rule(self) -> "MatchOverride":
        if self.status is not MatchStatus.NOT_DOCUMENTED and not self.evidence_ids:
            raise ValueError(f"a '{self.status.value}' override must cite at least one evidence item")
        if self.status is MatchStatus.NOT_DOCUMENTED and self.evidence_ids:
            raise ValueError("a 'not_documented' override cannot cite evidence")
        return self


class RequirementMatch(_Strict):
    requirement_id: str = Field(min_length=1)
    status: MatchStatus
    match_type: MatchType = MatchType.NONE
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Matcher strength; informational only")
    override: Optional[MatchOverride] = None

    @property
    def effective_status(self) -> MatchStatus:
        return self.override.status if self.override else self.status

    @property
    def effective_evidence_ids(self) -> list[str]:
        return self.override.evidence_ids if self.override else self.evidence_ids


class MatchReport(_Strict):
    job_id: str = Field(min_length=1)
    matcher: str = "rules-v1"
    profile_version: int = Field(ge=1)
    analysis_fingerprint: str = Field(description="Hash of the analysis content matched; mismatch => stale")
    matches: list[RequirementMatch] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _unique(self) -> "MatchReport":
        ids = [m.requirement_id for m in self.matches]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate requirement IDs in match report")
        return self

    def by_requirement(self) -> dict[str, RequirementMatch]:
        return {m.requirement_id: m for m in self.matches}
