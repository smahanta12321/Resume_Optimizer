"""Deterministic resume drafting: select and order master-profile evidence for one job.

Nothing here writes new text. Bullets are copied verbatim, header fields
(titles, employers, dates, degrees) come straight from the profile, and the
skills section lists only profile skills that some evidence item shows.
Optional LLM rewriting happens afterwards (``resume_rewriter``) and is checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.schemas.analysis import JDAnalysis
from src.schemas.match import MatchReport, MatchStatus
from src.schemas.profile import Bullet, Experience, MasterProfile, Project, RoleProfile, TargetLength
from src.schemas.resume import (
    ResumeBullet,
    ResumeCertification,
    ResumeContent,
    ResumeEducation,
    ResumeEntry,
    ResumeSkill,
    ResumeSummary,
    ResumeVersion,
    TextOrigin,
)
from src.services.match_report_service import WEIGHT
from src.services.matching_service import ProfileIndex, build_index, canonical
from src.services.profile_service import unverified_numbers


@dataclass(frozen=True)
class Limits:
    first_role_bullets: int
    other_role_bullets: int
    total_bullets: int
    projects: int
    project_bullets: int
    skills: int


LIMITS = {
    TargetLength.ONE_PAGE: Limits(4, 3, 10, 2, 2, 14),
    TargetLength.TWO_PAGES: Limits(6, 4, 18, 4, 3, 24),
}


def _relevance(report: MatchReport, analysis: JDAnalysis, profile: MasterProfile) -> dict[str, float]:
    """Evidence ID -> weight of the matched requirements it supports (bullets also get a share of their parent's)."""
    reqs = {r.id: r for r in analysis.requirements}
    score: dict[str, float] = {}
    for m in report.matches:
        req = reqs.get(m.requirement_id)
        if req is None or m.effective_status is MatchStatus.NOT_DOCUMENTED:
            continue
        w = WEIGHT[req.importance] * (1.0 if m.effective_status is MatchStatus.SUPPORTED else 0.5)
        for eid in m.effective_evidence_ids:
            score[eid] = score.get(eid, 0.0) + w
    for item in [*profile.experience, *profile.projects]:
        parent = score.get(item.id, 0.0)
        for b in item.bullets:
            score[b.id] = score.get(b.id, 0.0) + 0.25 * parent
    return score


def _usable(b: Bullet) -> Optional[str]:
    """Reason a bullet can't be used, or None."""
    nums = unverified_numbers(b.text, [m.value for m in b.verified_metrics])
    if nums:
        return f"contains unverified number(s) {', '.join(nums)}"
    return None


def _pick_bullets(item: Experience | Project, cap: int, minimum: int, score: dict[str, float],
                  role_ids: set[str], omitted: list[str]) -> list[Bullet]:
    usable = []
    for b in item.bullets:
        reason = _usable(b)
        if reason:
            omitted.append(f"Bullet “{b.text[:60]}” ({b.id}) {reason}. Add a verified metric on the Master Profile "
                           "page to use it.")
        else:
            usable.append(b)
    order = {b.id: i for i, b in enumerate(item.bullets)}
    ranked = sorted(usable, key=lambda b: (-(score.get(b.id, 0.0) + (1.0 if b.id in role_ids else 0.0)), order[b.id]))
    relevant = [b for b in ranked if score.get(b.id, 0.0) > 0 or b.id in role_ids]
    chosen = relevant[:cap]
    for b in ranked:  # keep some context for each role even if nothing matched
        if len(chosen) >= min(minimum, cap):
            break
        if b not in chosen:
            chosen.append(b)
    for b in usable:
        if b not in chosen:
            omitted.append(f"Bullet “{b.text[:60]}” ({b.id}) left out as less relevant to this job.")
    return chosen


def _bullet(b: Bullet) -> ResumeBullet:
    return ResumeBullet(evidence_ids=[b.id], text=b.text, source_text=b.text, origin=TextOrigin.VERBATIM)


def _entry(item: Experience | Project, bullets: list[Bullet]) -> ResumeEntry:
    if isinstance(item, Experience):
        return ResumeEntry(evidence_id=item.id, kind="experience", title=item.title, organization=item.employer,
                           location=item.location, start_date=item.start_date, end_date=item.end_date,
                           bullets=[_bullet(b) for b in bullets])
    return ResumeEntry(evidence_id=item.id, kind="project", title=item.name, organization=item.role,
                       start_date=item.start_date, end_date=item.end_date, bullets=[_bullet(b) for b in bullets])


def _skills(profile: MasterProfile, idx: ProfileIndex, report: MatchReport, analysis: JDAnalysis,
            role: Optional[RoleProfile], cap: int, omitted: list[str]) -> list[ResumeSkill]:
    jd_weight: dict[str, int] = {}
    by_req = report.by_requirement()
    for req in analysis.requirements:
        m = by_req.get(req.id)
        if m and m.effective_status is MatchStatus.SUPPORTED and req.normalized_term:
            key = canonical(req.normalized_term, idx.extra).casefold()
            jd_weight[key] = max(jd_weight.get(key, 0), WEIGHT[req.importance])
    role_rank = {sid: i for i, sid in enumerate(role.skill_ids)} if role else {}

    candidates, no_evidence = [], []
    for skill in profile.skills:
        key = canonical(skill.name, idx.extra)
        docs = idx.with_term(key)
        if not docs:
            no_evidence.append(skill.name)
            continue
        candidates.append((skill, key.casefold(), [d.id for d in docs]))
    candidates.sort(key=lambda c: (-jd_weight.get(c[1], 0), role_rank.get(c[0].id, 10_000), -len(c[2])))
    if no_evidence:
        omitted.append("Skills without evidence were left out: " + ", ".join(no_evidence)
                       + ". Link them to evidence on the Master Profile page to include them.")
    if len(candidates) > cap:
        omitted.append("Skills left out to fit the length: " + ", ".join(c[0].name for c in candidates[cap:]) + ".")
    listed = {key for _, key, _ in candidates}
    unlisted = sorted({req.normalized_term for req in analysis.requirements
                       if by_req.get(req.id) and by_req[req.id].effective_status is MatchStatus.SUPPORTED
                       and req.category.value == "skill"
                       and canonical(req.normalized_term, idx.extra).casefold() not in listed})
    if unlisted:
        omitted.append("Evidenced JD skills not in your skills list (add them there to include them): "
                       + ", ".join(unlisted) + ".")
    return [ResumeSkill(name=s.name, evidence_ids=ids) for s, _, ids in candidates[:cap]]


def build_draft(
    profile: MasterProfile,
    analysis: JDAnalysis,
    report: MatchReport,
    *,
    role: Optional[RoleProfile] = None,
    target_pages: TargetLength = TargetLength.ONE_PAGE,
) -> tuple[ResumeContent, list[str]]:
    """Select, order and copy evidence into resume content. Returns ``(content, omitted_notes)``."""
    limits = LIMITS[target_pages]
    idx = build_index(profile)
    score = _relevance(report, analysis, profile)
    role_ids = set(role.evidence_ids) if role else set()
    omitted: list[str] = []

    # Current roles first, then most recently ended (reverse chronological).
    experiences = sorted(profile.experience, key=lambda e: (e.end_date is None, e.end_date or "", e.start_date or ""),
                         reverse=True)
    entries, total = [], 0
    for i, exp in enumerate(experiences):
        cap = limits.first_role_bullets if i == 0 else limits.other_role_bullets
        cap = max(1, min(cap, limits.total_bullets - total))
        bullets = _pick_bullets(exp, cap, 2 if i == 0 else 1, score, role_ids, omitted)
        total += len(bullets)
        entries.append(_entry(exp, bullets))

    def project_score(p: Project) -> float:
        return score.get(p.id, 0.0) + sum(score.get(b.id, 0.0) for b in p.bullets) + (1.0 if p.id in role_ids else 0.0)

    ranked = sorted((p for p in profile.projects if project_score(p) > 0), key=lambda p: -project_score(p))
    projects = []
    for p in ranked[: limits.projects]:
        projects.append(_entry(p, _pick_bullets(p, limits.project_bullets, 1, score, role_ids, omitted)))
    for p in profile.projects:
        if p not in ranked[: limits.projects]:
            omitted.append(f"Project “{p.name}” left out as {'less relevant' if p in ranked else 'not relevant'} "
                           "to this job.")

    summary = ResumeSummary(text=profile.summary, evidence_ids=[], origin=TextOrigin.VERBATIM,
                            notes=["Your master-profile summary, used as written."] if profile.summary else [])
    content = ResumeContent(
        contact=profile.contact,
        headline=(role.headline if role and role.headline else profile.headline),
        summary=summary,
        skills=_skills(profile, idx, report, analysis, role, limits.skills, omitted),
        experience=entries,
        projects=projects,
        education=[ResumeEducation(evidence_id=e.id, degree=e.degree, field_of_study=e.field_of_study,
                                   institution=e.institution, start_date=e.start_date, end_date=e.end_date)
                   for e in profile.education],
        certifications=[ResumeCertification(evidence_id=c.id, name=c.name, issuer=c.issuer, issue_date=c.issue_date)
                        for c in profile.certifications],
    )
    return content, omitted


def new_version(job_id: str, profile: MasterProfile, report: MatchReport, content: ResumeContent,
                omitted: list[str], *, generator: str, role: Optional[RoleProfile],
                target_pages: TargetLength, parent_id: Optional[str] = None) -> ResumeVersion:
    return ResumeVersion(job_id=job_id, parent_id=parent_id, profile_version=profile.profile_version,
                         match_profile_version=report.profile_version, role_profile_id=role.id if role else None,
                         target_pages=target_pages, generator=generator, content=content, omitted=omitted)
