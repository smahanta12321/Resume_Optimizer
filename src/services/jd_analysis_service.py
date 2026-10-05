"""JD analysis workflow: run the parser, apply user corrections, track staleness and confirmation."""

from __future__ import annotations

import logging
from typing import Optional

from src.schemas.analysis import JDAnalysis, Origin, Requirement, WorkArrangement
from src.schemas.job import Job
from src.schemas.profile import MasterProfile
from src.services.jd_import_service import description_hash
from src.services.jd_parser import ParseResult, parse_jd
from src.services.skill_taxonomy import SkillTerm, profile_terms
from src.ui.table_convert import rows_to_models

logger = logging.getLogger(__name__)

# Requirement fields the user edits in the review table. Others (excerpt, confidence, origin) are derived.
EDITABLE_FIELDS = ("category", "importance", "text", "normalized_term", "min_years", "max_years")


def vocabulary_from_profile(profile: Optional[MasterProfile]) -> list[SkillTerm]:
    """Profile skill names/aliases as extra recognition terms. Recognition is not matching."""
    if profile is None:
        return []
    return profile_terms((s.name, s.category, s.aliases) for s in profile.skills)


def analyze_job(job: Job, profile: Optional[MasterProfile] = None) -> ParseResult:
    """Run the deterministic parser on ``job`` (no LLM, no network)."""
    result = parse_jd(job, vocabulary_from_profile(profile))
    logger.info("event=jd_analyzed job_id=%s requirements=%d warnings=%d",
                job.id, len(result.analysis.requirements), len(result.analysis.warnings))
    return result


def is_stale(analysis: JDAnalysis, job: Job) -> bool:
    """True if the job's JD text changed after this analysis was made."""
    return analysis.jd_hash != description_hash(job.description)


def apply_requirement_edits(existing: list[Requirement], rows: list[dict]) -> list[Requirement]:
    """Turn edited table rows into requirements.

    Rows are matched to existing requirements by ID; derived columns in the rows
    are ignored. New or changed rows are marked ``origin=user`` with confidence 1.0.
    Raises ``ValueError`` (incl. pydantic ``ValidationError``) on invalid rows.
    """
    by_id = {r.id: r for r in existing}
    cleaned = [{k: v for k, v in row.items() if k in ("id", *EDITABLE_FIELDS)} for row in rows]
    for row in cleaned:
        for f in ("min_years", "max_years"):
            if isinstance(row.get(f), str) and not row[f].strip():
                row[f] = None  # blank table cell = no value
    updated = rows_to_models(cleaned, Requirement, existing)
    out = []
    for req in updated:
        before = by_id.get(req.id)
        changed = before is None or any(getattr(before, f) != getattr(req, f) for f in EDITABLE_FIELDS)
        if changed:
            req = req.model_copy(update={"origin": Origin.USER, "confidence": 1.0})
        out.append(Requirement.model_validate(req.model_dump()))
    return out


def update_analysis(
    analysis: JDAnalysis,
    *,
    requirements: Optional[list[Requirement]] = None,
    work_arrangement: Optional[WorkArrangement] = None,
    experience_min_years: Optional[float] = None,
    experience_max_years: Optional[float] = None,
) -> JDAnalysis:
    """Return an edited copy. Any edit clears confirmation; the user must re-confirm."""
    data = analysis.model_dump()
    if requirements is not None:
        data["requirements"] = [r.model_dump() for r in requirements]
    if work_arrangement is not None:
        data["work_arrangement"] = work_arrangement
    data["experience_min_years"] = experience_min_years
    data["experience_max_years"] = experience_max_years
    new = JDAnalysis.model_validate(data)
    if new.model_dump(exclude={"updated_at", "confirmed_at"}) != analysis.model_dump(exclude={"updated_at", "confirmed_at"}):
        new = new.model_copy(update={"confirmed_at": None})
    return new
