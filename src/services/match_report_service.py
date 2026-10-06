"""Match report: transparent coverage summary, gaps, overrides, staleness, and recommendations.

Coverage measures how many JD requirements your recorded evidence addresses.
It is not a hiring probability or an ATS score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.schemas.analysis import Importance, JDAnalysis, Requirement
from src.schemas.match import MatchOverride, MatchReport, MatchStatus
from src.schemas.profile import MasterProfile, RoleProfile
from src.services.matching_service import analysis_fingerprint

CREDIT = {MatchStatus.SUPPORTED: 1.0, MatchStatus.PARTIAL: 0.5, MatchStatus.NOT_DOCUMENTED: 0.0}
WEIGHT = {Importance.REQUIRED: 3, Importance.PREFERRED: 2, Importance.UNSPECIFIED: 1}

FORMULA = (
    "Each requirement earns **1** if supported, **0.5** if partial, **0** if not documented "
    "(using your overrides where set). **Required coverage** and **preferred coverage** are the average credit "
    "within that group. **Overall coverage** weights required ×3, preferred ×2, unspecified ×1. "
    "These numbers describe how much of the JD your recorded evidence addresses. They are not a hiring "
    "probability or an ATS score, and text-overlap matches are hints that need your check."
)


class OverrideError(ValueError):
    """Invalid override request. Message is user-facing."""


@dataclass
class GroupStats:
    total: int = 0
    supported: int = 0
    partial: int = 0
    not_documented: int = 0

    @property
    def coverage(self) -> Optional[float]:
        if not self.total:
            return None
        return (self.supported + 0.5 * self.partial) / self.total


@dataclass
class Summary:
    groups: dict[Importance, GroupStats] = field(default_factory=dict)
    overall: Optional[float] = None
    overrides: int = 0


def _joined(report: MatchReport, analysis: JDAnalysis) -> list[tuple[Requirement, object]]:
    by_req = report.by_requirement()
    return [(r, by_req[r.id]) for r in analysis.requirements if r.id in by_req]


def summarize(report: MatchReport, analysis: JDAnalysis) -> Summary:
    summary = Summary(groups={i: GroupStats() for i in Importance})
    num = den = 0.0
    for req, m in _joined(report, analysis):
        g = summary.groups[req.importance]
        g.total += 1
        status = m.effective_status
        setattr(g, status.value, getattr(g, status.value) + 1)
        num += WEIGHT[req.importance] * CREDIT[status]
        den += WEIGHT[req.importance]
        summary.overrides += m.override is not None
    summary.overall = num / den if den else None
    return summary


def gaps(report: MatchReport, analysis: JDAnalysis) -> list[Requirement]:
    """Required/preferred requirements with no documented evidence, required first."""
    out = [req for req, m in _joined(report, analysis)
           if m.effective_status is MatchStatus.NOT_DOCUMENTED and req.importance is not Importance.UNSPECIFIED]
    return sorted(out, key=lambda r: r.importance is not Importance.REQUIRED)


def stale_reasons(report: MatchReport, analysis: Optional[JDAnalysis], profile: Optional[MasterProfile]) -> list[str]:
    reasons = []
    if profile is not None and profile.profile_version != report.profile_version:
        reasons.append(f"Your master profile changed (v{report.profile_version} → v{profile.profile_version}).")
    if analysis is not None and analysis_fingerprint(analysis) != report.analysis_fingerprint:
        reasons.append("The JD analysis changed.")
    return reasons


def set_override(report: MatchReport, requirement_id: str, status: MatchStatus, evidence_ids: list[str],
                 note: str, profile: MasterProfile) -> MatchReport:
    """Record the user's judgement for one requirement. Evidence must exist in the profile."""
    matches = report.by_requirement()
    if requirement_id not in matches:
        raise OverrideError("That requirement is not in this report.")
    unknown = [e for e in evidence_ids if e not in profile.evidence_index()]
    if unknown:
        raise OverrideError(f"Unknown evidence IDs: {', '.join(unknown)}.")
    try:
        override = MatchOverride(status=status, evidence_ids=list(dict.fromkeys(evidence_ids)), note=note.strip())
    except ValueError as exc:
        msg = "; ".join(e["msg"] for e in exc.errors()) if hasattr(exc, "errors") else str(exc)
        raise OverrideError(msg.removeprefix("Value error, ")) from exc
    new = [m.model_copy(update={"override": override}) if m.requirement_id == requirement_id else m
           for m in report.matches]
    return report.model_copy(update={"matches": new})


def clear_override(report: MatchReport, requirement_id: str) -> MatchReport:
    new = [m.model_copy(update={"override": None}) if m.requirement_id == requirement_id else m
           for m in report.matches]
    return report.model_copy(update={"matches": new})


# ---- recommendations ------------------------------------------------------------


@dataclass
class Recommendation:
    id: str
    name: str
    score: float  # share of evidenced requirement weight this item covers (0..1)
    covered: list[str]  # requirement labels


def _req_label(req: Requirement) -> str:
    return req.normalized_term if req.normalized_term and req.normalized_term != "overall" else req.text[:50]


def _evidenced(report: MatchReport, analysis: JDAnalysis) -> list[tuple[Requirement, set[str]]]:
    return [(req, set(m.effective_evidence_ids)) for req, m in _joined(report, analysis)
            if m.effective_status is not MatchStatus.NOT_DOCUMENTED and m.effective_evidence_ids]


def _children(profile: MasterProfile) -> dict[str, set[str]]:
    kids: dict[str, set[str]] = {}
    for item in [*profile.experience, *profile.projects]:
        kids[item.id] = {b.id for b in item.bullets}
    return kids


def _rank(candidates: list[tuple[str, str, set[str]]], evidenced: list[tuple[Requirement, set[str]]]
          ) -> list[Recommendation]:
    total = sum(WEIGHT[r.importance] for r, _ in evidenced)
    out = []
    for cid, name, ids in candidates:
        covered = [r for r, ev in evidenced if ev & ids]
        if not covered:
            continue
        score = sum(WEIGHT[r.importance] for r in covered) / total if total else 0.0
        out.append(Recommendation(cid, name, score, [_req_label(r) for r in covered]))
    return sorted(out, key=lambda rec: -rec.score)


def recommend_role_profiles(report: MatchReport, analysis: JDAnalysis, profile: MasterProfile,
                            roles: list[RoleProfile]) -> list[Recommendation]:
    """Role profiles ranked by how much evidenced requirement weight their selected evidence covers."""
    kids = _children(profile)
    candidates = []
    for role in roles:
        ids = set(role.evidence_ids)
        for eid in role.evidence_ids:
            ids |= kids.get(eid, set())
        candidates.append((role.id, role.name, ids))
    return _rank(candidates, _evidenced(report, analysis))


def recommend_projects(report: MatchReport, analysis: JDAnalysis, profile: MasterProfile) -> list[Recommendation]:
    """Projects ranked by the evidenced requirements they (or their bullets) support."""
    kids = _children(profile)
    candidates = [(p.id, p.name, {p.id} | kids[p.id]) for p in profile.projects]
    return _rank(candidates, _evidenced(report, analysis))
