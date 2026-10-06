"""Resume workflow: generate a version (deterministic + optional checked AI rewrite) and apply user edits.

Every save produces a new immutable version linked to its parent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.schemas.analysis import JDAnalysis
from src.schemas.job import Job
from src.schemas.match import MatchReport
from src.schemas.profile import MasterProfile, RoleProfile, TargetLength
from src.schemas.resume import ResumeSummary, ResumeVersion, TextOrigin
from src.services.llm.provider import LLMError, LLMProvider
from src.services.resume_generator import build_draft, new_version
from src.services.resume_rewriter import rewrite

logger = logging.getLogger(__name__)


@dataclass
class GenerationOutcome:
    version: ResumeVersion
    notes: list[str] = field(default_factory=list)
    ai_failed: Optional[str] = None


def generate_version(job: Job, profile: MasterProfile, analysis: JDAnalysis, report: MatchReport, *,
                     role: Optional[RoleProfile] = None, target_pages: TargetLength = TargetLength.ONE_PAGE,
                     provider: Optional[LLMProvider] = None, today: Optional[date] = None) -> GenerationOutcome:
    """Build a draft from evidence. If a provider is given (user consented), apply checked rewrites.

    If the AI step fails, the deterministic draft is still returned, with the reason.
    """
    content, omitted = build_draft(profile, analysis, report, role=role, target_pages=target_pages)
    generator, notes, failed = "deterministic", [], None
    if provider is not None:
        try:
            result = rewrite(content, profile, analysis, report, provider, target_role=job.title, today=today)
            content, notes = result.content, result.notes
            generator = f"llm:{provider.name}/{provider.model}"
        except LLMError as exc:
            failed = str(exc)
            logger.warning("event=rewrite_failed provider=%s", provider.name)
    version = new_version(job.id, profile, report, content, omitted, generator=generator, role=role,
                          target_pages=target_pages)
    return GenerationOutcome(version, notes, failed)


def apply_user_edits(version: ResumeVersion, *, summary_text: Optional[str] = None,
                     bullets: Optional[dict[tuple[str, str], tuple[bool, str]]] = None) -> ResumeVersion:
    """Return a NEW version with the user's edits.

    ``bullets`` maps (entry evidence_id, bullet's first evidence_id) -> (include, text).
    Changed text is marked ``user_edit`` and checked at validation like any rewrite;
    excluded bullets are listed in ``omitted``. Header facts cannot be edited here.
    """
    content = version.content.model_copy(deep=True)
    omitted = list(version.omitted)
    changed = False
    if bullets:
        for entry in [*content.experience, *content.projects]:
            kept = []
            for b in entry.bullets:
                include, text = bullets.get((entry.evidence_id, b.evidence_ids[0]), (True, b.text))
                text = (text or "").strip()
                if not include:
                    omitted.append(f"Bullet “{b.text[:60]}” ({b.evidence_ids[0]}) removed by you.")
                    changed = True
                    continue
                if text and text != b.text:
                    origin = TextOrigin.VERBATIM if text == b.source_text else TextOrigin.USER_EDIT
                    b = b.model_copy(update={"text": text, "origin": origin, "notes": []})
                    changed = True
                kept.append(b)
            entry.bullets = kept
    if summary_text is not None and summary_text.strip() != content.summary.text:
        evidence_ids = [b.evidence_ids[0] for e in [*content.experience, *content.projects] for b in e.bullets]
        content.summary = ResumeSummary(text=summary_text.strip(), evidence_ids=evidence_ids,
                                        origin=TextOrigin.USER_EDIT, notes=[])
        changed = True
    if not changed:
        return version
    return ResumeVersion.model_validate(version.model_dump(exclude={"id", "created_at", "approved_at",
                                                                    "approval_note"})
                                        | {"parent_id": version.id, "generator": "user_edit",
                                           "content": content.model_dump(), "omitted": omitted})
