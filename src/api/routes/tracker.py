"""Application tracker and dashboard (mirrors the Application Tracker and Dashboard pages).

Statuses and dates are recorded by the user. Nothing here applies to jobs or contacts anyone.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Response

from src.api import deps
from src.api.errors import ApiError
from src.api.models import (
    ApplicationIn,
    ApplicationOut,
    Dashboard,
    DashboardJob,
    DashboardProfile,
    DuplicatePairView,
    MergeIn,
    TrackerRowView,
    TrackerView,
)
from src.api.routes.resumes import list_all_versions
from src.persistence.profile_store import ProfileStoreError
from src.schemas.job import Job, JobStatus, SourcePlatform
from src.services.profile_service import profile_warnings
from src.services.tracker_service import (
    TrackerError,
    TrackerRow,
    build_rows,
    duplicate_pairs,
    filter_rows,
    follow_ups_due,
    merge_jobs,
    merge_loss,
    to_csv,
    update_application,
)

router = APIRouter(tags=["tracker"])


def _filtered(status: Optional[list[JobStatus]], platform: Optional[list[SourcePlatform]], search: str,
              due_only: bool) -> tuple[list[TrackerRow], list[TrackerRow]]:
    rows = build_rows(deps.job_store())
    return rows, filter_rows(rows, statuses=status or None, platforms=platform or None, search=search,
                             due_only=due_only)


def _row(r: TrackerRow) -> TrackerRowView:
    return TrackerRowView(job=r.job, display_name=r.job.display_name, analysis_state=r.analysis_state,
                          required_coverage=r.required_coverage, versions=r.versions, approved=r.approved,
                          resume_label=r.resume_label, exported=r.exported, follow_up_due=r.follow_up_due)


@router.get("/tracker", response_model=TrackerView)
def tracker(status: Optional[list[JobStatus]] = Query(None), platform: Optional[list[SourcePlatform]] = Query(None),
            search: str = "", due_only: bool = False) -> TrackerView:
    rows, shown = _filtered(status, platform, search, due_only)
    return TrackerView(rows=[_row(r) for r in shown], total=len(rows),
                       counts={s.value: sum(r.job.status is s for r in rows) for s in JobStatus},
                       follow_ups_due=sum(r.follow_up_due for r in rows))


@router.get("/tracker/export.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "CSV of the filtered jobs"}})
def tracker_csv(status: Optional[list[JobStatus]] = Query(None),
                platform: Optional[list[SourcePlatform]] = Query(None), search: str = "", due_only: bool = False,
                include_jd_text: bool = False) -> Response:
    _, shown = _filtered(status, platform, search, due_only)
    return Response(to_csv(shown, include_jd_text=include_jd_text), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="applications_{date.today():%Y%m%d}.csv"'})


@router.patch("/tracker/{job_id}", response_model=ApplicationOut)
def update(job_id: str, body: ApplicationIn) -> ApplicationOut:
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    try:
        saved, info = update_application(store, job, status=body.status, applied_on=body.applied_on,
                                         follow_up_on=body.follow_up_on, notes=body.notes,
                                         resume_version_id=body.resume_version_id)
    except TrackerError as exc:
        raise ApiError(422, "invalid_application", str(exc)) from exc
    return ApplicationOut(job=saved, info=info)


@router.get("/tracker/duplicates", response_model=list[DuplicatePairView])
def duplicates() -> list[DuplicatePairView]:
    store = deps.job_store()
    return [DuplicatePairView(first=p.first, second=p.second, reason=p.reason,
                              loss_if_first_dropped=merge_loss(store, p.first.id),
                              loss_if_second_dropped=merge_loss(store, p.second.id))
            for p in duplicate_pairs(store.list())]


@router.post("/tracker/merge", response_model=Job)
def merge(body: MergeIn) -> Job:
    """Keep one record, fill its blanks from the other, append the other's notes, delete the other."""
    store = deps.job_store()
    try:
        return merge_jobs(store, body.keep_id, body.drop_id, deps.settings().output_dir)
    except TrackerError as exc:
        raise ApiError(422, "merge_failed", str(exc)) from exc


# ---- dashboard --------------------------------------------------------------------


def _dash_job(job: Job) -> DashboardJob:
    return DashboardJob(id=job.id, display_name=job.display_name, status=job.status, updated_at=job.updated_at,
                        follow_up_on=job.follow_up_on)


@router.get("/dashboard", response_model=Dashboard, tags=["dashboard"])
def dashboard() -> Dashboard:
    """Counts and recent items from stored records only. There is no activity log or ATS score."""
    profile_store, store = deps.profile_store(), deps.job_store()
    try:
        profile = profile_store.load()
        state = "ok" if profile else "missing"
    except ProfileStoreError:
        profile, state = None, "unreadable"
    summary = DashboardProfile(state=state)
    roles: list[str] = []
    if profile:
        summary = DashboardProfile(state="ok", version=profile.profile_version, is_sample=profile.is_sample,
                                   confirmed_at=profile.confirmed_at, experience=len(profile.experience),
                                   projects=len(profile.projects), skills=len(profile.skills),
                                   warnings=len(profile_warnings(profile)))
        try:
            roles = [r.name for r in profile_store.load_roles().role_profiles]
        except ProfileStoreError:
            roles = []
    jobs = store.list()
    counts = store.resume_counts()
    return Dashboard(
        profile=summary, role_profiles=roles, jobs_total=len(jobs), jobs_analyzed=len(store.analysis_ids()),
        jobs_matched=len(store.match_report_ids()),
        jobs_with_approved_resume=sum(1 for _, approved in counts.values() if approved),
        jobs_exported=len(store.export_counts()), versions_total=sum(v for v, _ in counts.values()),
        applications_tracked=sum(j.status is not JobStatus.SAVED for j in jobs),
        recent_jobs=[_dash_job(j) for j in sorted(jobs, key=lambda j: j.updated_at, reverse=True)[:5]],
        recent_versions=list_all_versions()[:5],
        follow_ups_due=[_dash_job(j) for j in follow_ups_due(jobs)],
        captures_waiting=len(store.list_captures()),
    )
