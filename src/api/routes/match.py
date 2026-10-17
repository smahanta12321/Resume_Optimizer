"""Match report: evidence-backed coverage for a confirmed JD analysis (mirrors the Match Report page)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from src.api import deps
from src.api.errors import ApiError
from src.api.models import (
    GroupStatsView,
    MatchRow,
    MatchRunOut,
    MatchSummaryView,
    MatchView,
    OverrideIn,
    RecommendationView,
)
from src.api.routes.profile import evidence_items
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStoreError
from src.schemas.analysis import JDAnalysis
from src.schemas.job import Job
from src.schemas.match import MatchReport
from src.schemas.profile import MasterProfile
from src.services.jd_analysis_service import is_stale
from src.services.match_report_service import (
    FORMULA,
    OverrideError,
    clear_override,
    gaps,
    recommend_projects,
    recommend_role_profiles,
    set_override,
    stale_reasons,
    summarize,
)
from src.services.matching_service import build_match_report

router = APIRouter(tags=["match"])


def match_blockers(job: Job, analysis: Optional[JDAnalysis], profile: Optional[MasterProfile]) -> list[str]:
    """The same preconditions the Match Report page checks before matching."""
    if profile is None:
        return ["Create or import a master profile first."]
    if analysis is None:
        return ["Analyze this job description first."]
    if is_stale(analysis, job):
        return ["The JD text changed after it was analyzed. Re-analyze and confirm it first."]
    if not analysis.confirmed_at:
        return ["Confirm this job's analysis before matching. Matching unreviewed requirements would be misleading."]
    if not analysis.requirements:
        return ["The analysis has no requirements to match. Add them on the analysis review."]
    return []


def recommendations(recs) -> list[RecommendationView]:
    return [RecommendationView(id=r.id, name=r.name, score=r.score, covered=r.covered) for r in recs]


def _summary(report: MatchReport, analysis: JDAnalysis) -> MatchSummaryView:
    s = summarize(report, analysis)
    groups = {imp.value: GroupStatsView(total=g.total, supported=g.supported, partial=g.partial,
                                        not_documented=g.not_documented, coverage=g.coverage)
              for imp, g in s.groups.items()}
    return MatchSummaryView(groups=groups, overall=s.overall, overrides=s.overrides, formula=FORMULA)


def _load(store: JobStore, job_id: str):
    job = deps.require_job(store, job_id)
    profile_store = deps.profile_store()
    profile = profile_store.load()
    try:
        roles = profile_store.load_roles().role_profiles
    except ProfileStoreError:
        roles = []
    return job, profile, roles, store.get_analysis(job_id), store.get_match_report(job_id)


def build_view(store: JobStore, job_id: str) -> MatchView:
    job, profile, roles, analysis, report = _load(store, job_id)
    blockers = match_blockers(job, analysis, profile)
    view = MatchView(job=job, blockers=blockers, report=report if not blockers else None,
                     profile_version=profile.profile_version if profile else None,
                     profile_confirmed=bool(profile and profile.confirmed_at), has_role_profiles=bool(roles))
    if blockers or report is None:
        return view
    by_req = report.by_requirement()
    rows = []
    for req in analysis.requirements:
        m = by_req.get(req.id)
        if m is None:
            continue
        rows.append(MatchRow(requirement=req, status=m.effective_status, evidence_ids=m.effective_evidence_ids,
                             match_type=m.match_type.value, explanation=m.explanation,
                             has_override=m.override is not None,
                             override_note=m.override.note if m.override else ""))
    view.stale_reasons = stale_reasons(report, analysis, profile)
    view.rows = rows
    view.summary = _summary(report, analysis)
    view.gaps = gaps(report, analysis)
    view.role_recommendations = recommendations(recommend_role_profiles(report, analysis, profile, roles))
    view.project_recommendations = recommendations(recommend_projects(report, analysis, profile)[:5])
    view.evidence = evidence_items(profile)
    return view


@router.get("/jobs/{job_id}/match", response_model=MatchView)
def get_match(job_id: str) -> MatchView:
    return build_view(deps.job_store(), job_id)


@router.post("/jobs/{job_id}/match", response_model=MatchRunOut)
def run_match(job_id: str) -> MatchRunOut:
    """Run (or re-run) matching. The user's judgements are kept where their evidence still exists."""
    store = deps.job_store()
    job, profile, _, analysis, previous = _load(store, job_id)
    blockers = match_blockers(job, analysis, profile)
    if blockers:
        raise ApiError(409, "match_blocked", blockers[0])
    report, notes = build_match_report(analysis, profile, previous=previous)
    store.save_match_report(report)
    return MatchRunOut(view=build_view(store, job_id), notes=notes)


def _report_for_override(store: JobStore, job_id: str):
    job, profile, _, analysis, report = _load(store, job_id)
    blockers = match_blockers(job, analysis, profile)
    if blockers:
        raise ApiError(409, "match_blocked", blockers[0])
    if report is None:
        raise ApiError(409, "match_missing", "Run matching first.")
    return profile, report


@router.put("/jobs/{job_id}/match/overrides/{requirement_id}", response_model=MatchView)
def save_override(job_id: str, requirement_id: str, body: OverrideIn) -> MatchView:
    """Record the user's judgement. Supported and partial must cite evidence from the profile."""
    store = deps.job_store()
    profile, report = _report_for_override(store, job_id)
    try:
        store.save_match_report(set_override(report, requirement_id, body.status, body.evidence_ids, body.note,
                                             profile))
    except OverrideError as exc:
        raise ApiError(422, "invalid_override", str(exc)) from exc
    return build_view(store, job_id)


@router.delete("/jobs/{job_id}/match/overrides/{requirement_id}", response_model=MatchView)
def remove_override(job_id: str, requirement_id: str) -> MatchView:
    store = deps.job_store()
    _, report = _report_for_override(store, job_id)
    try:
        store.save_match_report(clear_override(report, requirement_id))
    except OverrideError as exc:
        raise ApiError(422, "invalid_override", str(exc)) from exc
    return build_view(store, job_id)
