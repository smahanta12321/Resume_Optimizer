"""Pre-approval validation of a resume version against the master profile, plus a change summary.

Errors block approval. Warnings need the user's acknowledgement. Info is context.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.schemas.analysis import Importance, JDAnalysis
from src.schemas.match import MatchReport, MatchStatus
from src.schemas.profile import MasterProfile
from src.schemas.resume import ResumeVersion, TextOrigin
from src.services.claim_checker import check_rewrite, check_summary
from src.services.matching_service import build_index, documented_experience_years

LINES_PER_PAGE = 52   # rough single-column estimate at readable font sizes; real check comes with export
CHARS_PER_LINE = 95


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    estimated_lines: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _lines(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_LINE)) if text else 0


def estimate_lines(version: ResumeVersion) -> int:
    c = version.content
    n = 4 + _lines(c.summary.text) + (2 if c.summary.text else 0)
    n += _lines(", ".join(s.name for s in c.skills)) + 2 if c.skills else 0
    for e in [*c.experience, *c.projects]:
        n += 2 + sum(_lines(b.text) for b in e.bullets)
    n += 2 * len(c.education) + len(c.certifications) + 6  # section headings
    return n


def validate_resume(
    version: ResumeVersion,
    profile: MasterProfile,
    *,
    analysis: Optional[JDAnalysis] = None,
    report: Optional[MatchReport] = None,
    today: Optional[date] = None,
) -> ValidationReport:
    out = ValidationReport()
    c = version.content
    idx = build_index(profile)
    evidence = profile.evidence_index()
    by_id = idx.by_id

    if profile.profile_version != version.profile_version:
        out.warnings.append(f"Built from profile v{version.profile_version}; your profile is now "
                            f"v{profile.profile_version}. Generate a new version to pick up changes.")

    # Header facts must match the profile exactly.
    exp = {e.id: e for e in profile.experience}
    prj = {p.id: p for p in profile.projects}
    for entry in [*c.experience, *c.projects]:
        src = exp.get(entry.evidence_id) if entry.kind == "experience" else prj.get(entry.evidence_id)
        if src is None:
            out.errors.append(f"“{entry.title}” refers to {entry.evidence_id}, which is no longer in your profile.")
            continue
        expected = ((src.title, src.employer, src.start_date, src.end_date) if entry.kind == "experience"
                    else (src.name, src.role, src.start_date, src.end_date))
        if (entry.title, entry.organization, entry.start_date, entry.end_date) != expected:
            out.errors.append(f"Title, organization or dates of “{entry.title}” differ from your profile.")

        for b in entry.bullets:
            missing = [e for e in b.evidence_ids if e not in evidence]
            if missing:
                out.errors.append(f"A bullet under “{entry.title}” cites missing evidence {', '.join(missing)}.")
                continue
            source_bullets = [evidence[e][1] for e in b.evidence_ids if evidence[e][0] == "bullet"]
            current_source = " ".join(sb.text for sb in source_bullets)
            if b.source_text != current_source:
                out.warnings.append(f"The profile text behind “{b.text[:50]}…” changed since this version was made.")
            if b.origin is TextOrigin.VERBATIM:
                if b.text != b.source_text:
                    out.errors.append(f"A bullet marked verbatim differs from its source: “{b.text[:60]}”.")
                continue
            res = check_rewrite(
                b.text, b.source_text,
                verified_values=[m.value for sb in source_bullets for m in sb.verified_metrics],
                tagged_terms=[t for e in b.evidence_ids if e in by_id for t in by_id[e].linked],
                extra=idx.extra,
            )
            out.errors += [f"“{b.text[:60]}”: {e}" for e in res.errors]
            out.warnings += [f"“{b.text[:60]}”: {w}" for w in res.warnings]

    for s in c.skills:
        if not [e for e in s.evidence_ids if e in evidence]:
            out.errors.append(f"Skill “{s.name}” has no evidence in your profile.")

    if c.summary.text and c.summary.origin is not TextOrigin.VERBATIM:
        missing = [e for e in c.summary.evidence_ids if e not in evidence]
        if missing:
            out.errors.append(f"The summary cites missing evidence {', '.join(missing)}.")
        cited = [by_id[e] for e in c.summary.evidence_ids if e in by_id]
        metrics = [m.value for e in c.summary.evidence_ids if e in evidence
                   for m in getattr(evidence[e][1], "verified_metrics", [])]
        res = check_summary(
            c.summary.text, cited_texts=[d.text for d in cited], cited_metric_values=metrics,
            evidenced_terms={t for d in idx.docs for t in d.terms} | {s.name for s in c.skills},
            total_experience_years=documented_experience_years(profile, today), extra=idx.extra,
        )
        out.errors += [f"Summary: {e}" for e in res.errors]
        out.warnings += [f"Summary: {w}" for w in res.warnings]
    elif c.summary.text and c.summary.text != profile.summary:
        out.warnings.append("The summary differs from your current profile summary.")

    for e in c.education:
        src = evidence.get(e.evidence_id)
        if src is None or (src[1].degree, src[1].institution, src[1].start_date, src[1].end_date) != \
                (e.degree, e.institution, e.start_date, e.end_date):
            out.errors.append(f"Education “{e.degree}” does not match your profile.")
    for crt in c.certifications:
        src = evidence.get(crt.evidence_id)
        if src is None or src[1].name != crt.name:
            out.errors.append(f"Certification “{crt.name}” does not match your profile.")

    if not c.experience and not c.projects:
        out.warnings.append("The resume has no experience or projects.")
    if not c.skills:
        out.warnings.append("The skills section is empty.")
    if not c.summary.text:
        out.info.append("No summary. Add one to your master profile or generate one with AI rewriting.")
    if not c.contact.email and not c.contact.phone:
        out.warnings.append("No email or phone in the contact details.")

    out.estimated_lines = estimate_lines(version)
    budget = LINES_PER_PAGE * int(version.target_pages)
    if out.estimated_lines > budget:
        out.warnings.append(f"Estimated length ≈ {out.estimated_lines} lines may exceed the "
                            f"{int(version.target_pages)}-page target. Exact layout is checked at export.")

    if analysis is not None and report is not None:
        by_req = report.by_requirement()
        missing_req = [r for r in analysis.requirements if r.importance is Importance.REQUIRED
                       and by_req.get(r.id) and by_req[r.id].effective_status is MatchStatus.NOT_DOCUMENTED]
        if missing_req:
            out.info.append("Required JD items not shown (no evidence): "
                            + "; ".join(r.normalized_term or r.text[:40] for r in missing_req) + ".")
    return out


@dataclass
class ChangeRow:
    section: str
    item: str
    change: str
    original: str
    final: str
    evidence: str


def change_summary(version: ResumeVersion, profile: MasterProfile) -> list[ChangeRow]:
    """One row per bullet/summary: what the master profile said vs what the resume says."""
    labels = {d.id: d.label for d in build_index(profile).docs}
    rows = []
    s = version.content.summary
    if s.text or profile.summary:
        change = {TextOrigin.VERBATIM: "unchanged", TextOrigin.REWRITTEN: "rewritten",
                  TextOrigin.USER_EDIT: "edited by you"}[s.origin]
        rows.append(ChangeRow("Summary", "", change, profile.summary, s.text,
                              "; ".join(labels.get(e, e) for e in s.evidence_ids) or "your profile summary"))
    for entry in [*version.content.experience, *version.content.projects]:
        for b in entry.bullets:
            change = {TextOrigin.VERBATIM: "unchanged", TextOrigin.REWRITTEN: "rewritten",
                      TextOrigin.USER_EDIT: "edited by you"}[b.origin]
            rows.append(ChangeRow(entry.kind.capitalize(), entry.title, change, b.source_text, b.text,
                                  "; ".join(labels.get(e, e) for e in b.evidence_ids)))
    return rows
