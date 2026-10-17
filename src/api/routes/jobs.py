"""Job import (paste / file / URL / extension inbox), saved jobs, and JD analysis.

Mirrors the Job Import and JD Analysis pages: an import becomes a reviewable draft first, and a job
is only saved by ``POST /jobs`` after the user has reviewed it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.api import deps
from src.api.errors import ApiError, not_found
from src.api.models import (
    AnalysisReviewIn,
    AnalysisView,
    AnalyzeIn,
    AnalyzeOut,
    CaptureList,
    DuplicateView,
    JobCreateIn,
    JobCreateOut,
    JobDraft,
    JobPatchIn,
    JobSummary,
    TextDraftIn,
    UrlDraftIn,
)
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStoreError
from src.schemas.job import ImportMethod, Job, SourcePlatform
from src.schemas.profile import utc_now
from src.services.jd_analysis_service import analyze_job, apply_requirement_edits, is_stale, update_analysis
from src.services.jd_import_service import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
    JDImportError,
    build_job,
    check_jd_text,
    extract_text_from_file,
    find_duplicates,
    infer_platform,
    merge_import_into,
)
from src.services.tracker_service import delete_job
from src.services.url_import import UrlImportError, fetch_job_from_url

router = APIRouter(tags=["jobs"])


def _import_error(exc: Exception) -> ApiError:
    return ApiError(422, "import_failed", str(exc))


def _draft(text: str, method: ImportMethod, *, source_notes: list[str] | None = None, **fields) -> JobDraft:
    try:
        clean, notes = check_jd_text(text)
    except JDImportError as exc:
        raise _import_error(exc) from exc
    url = fields.get("source_url") or ""
    return JobDraft(text=clean, method=method, text_notes=notes, source_notes=source_notes or [],
                    suggested_platform=infer_platform(url) if url else SourcePlatform.OTHER, **fields)


# ---- drafts -----------------------------------------------------------------------


@router.post("/jobs/drafts/text", response_model=JobDraft)
def draft_from_text(body: TextDraftIn) -> JobDraft:
    return _draft(body.text, ImportMethod.PASTE)


@router.post("/jobs/drafts/file", response_model=JobDraft)
async def draft_from_file(request: Request, filename: str) -> JobDraft:
    """Extract JD text from an uploaded file sent as the raw request body (``?filename=`` names it)."""
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise ApiError(422, "unsupported_file", f"Use a text-based {', '.join(SUPPORTED_EXTENSIONS)} file.")
    data = await request.body()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_large", f"The file is larger than {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    try:
        text = extract_text_from_file(filename, data)
    except JDImportError as exc:
        raise _import_error(exc) from exc
    return _draft(text, ImportMethod.FILE, source_label=filename)


@router.post("/jobs/drafts/url", response_model=JobDraft)
def draft_from_url(body: UrlDraftIn) -> JobDraft:
    """Best-effort fetch of one public page. Never bypasses sign-in or bot checks; failures suggest pasting."""
    settings = deps.settings()
    if not settings.url_import_enabled:
        reason = "local-only mode is on" if settings.local_only else "it is switched off"
        raise ApiError(409, "url_import_disabled", f"URL import is unavailable because {reason} (see Settings). "
                                                   "Paste or upload the job description instead.")
    try:
        result = fetch_job_from_url(body.url, timeout=settings.url_timeout_seconds)
    except UrlImportError as exc:
        raise ApiError(422, "url_import_failed", str(exc), {"reason": exc.reason.value}) from exc
    return _draft(result.text, ImportMethod.URL, source_notes=result.notes, source_url=result.final_url,
                  title=result.title, company=result.company, location=result.location)


@router.post("/jobs/drafts/capture/{capture_id}", response_model=JobDraft)
def draft_from_capture(capture_id: str) -> JobDraft:
    capture = next((c for c in deps.job_store().list_captures() if c.id == capture_id), None)
    if capture is None:
        raise not_found("This capture")
    return _draft(capture.text, ImportMethod.EXTENSION,
                  source_notes=[f"Captured by the browser extension ({capture.method}) from a page you were "
                                "viewing. Check it against the original posting."],
                  source_url=capture.url, title=capture.title, company=capture.company,
                  location=capture.location, capture_id=capture.id)


@router.get("/captures", response_model=CaptureList)
def list_captures() -> CaptureList:
    return deps.job_store().list_captures()


@router.delete("/captures/{capture_id}", status_code=204)
def discard_capture(capture_id: str) -> Response:
    if not deps.job_store().delete_capture(capture_id):
        raise not_found("This capture")
    return Response(status_code=204)


# ---- saved jobs -------------------------------------------------------------------


def _summaries(store: JobStore) -> list[JobSummary]:
    jobs = store.list()
    analysis_ids, reported, counts = store.analysis_ids(), store.match_report_ids(), store.resume_counts()
    out = []
    for job in jobs:
        state = "none"
        if job.id in analysis_ids:
            analysis = store.get_analysis(job.id)
            state = "confirmed" if analysis and analysis.confirmed_at else "draft"
        versions, approved = counts.get(job.id, (0, 0))
        out.append(JobSummary(job=job, display_name=job.display_name, analysis_state=state,
                              has_match_report=job.id in reported, versions=versions, approved_versions=approved))
    return out


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs() -> list[JobSummary]:
    return _summaries(deps.job_store())


@router.post("/jobs", response_model=JobCreateOut, status_code=201,
             responses={409: {"description": "Looks like a saved job (code 'duplicate', details.duplicates)"}})
def create_job(body: JobCreateIn) -> JobCreateOut:
    store = deps.job_store()
    try:
        job = build_job(body.text, title=body.title, company=body.company, location=body.location,
                        source_url=body.source_url, source_platform=body.source_platform,
                        import_method=body.method, source_label=body.source_label, notes=body.source_notes)
    except JDImportError as exc:
        raise _import_error(exc) from exc
    existing = store.list()
    merged = False
    if body.on_duplicate == "check":
        matches = find_duplicates(job, existing)
        if matches:
            raise ApiError(409, "duplicate", "This looks like a job you already saved.", {
                "duplicates": [DuplicateView(job=m.job, reason=m.reason).model_dump(mode="json") for m in matches]})
        saved = store.add(job)
    elif body.on_duplicate == "merge":
        target = store.get(body.merge_into_id or "")
        if target is None:
            raise not_found("The job to update")
        saved, merged = store.update(merge_import_into(target, job)), True
    else:
        saved = store.add(job)
    if body.capture_id:
        store.delete_capture(body.capture_id)  # a saved capture leaves the inbox, as in Streamlit
    return JobCreateOut(job=saved, merged=merged)


@router.get("/jobs/{job_id}", response_model=JobSummary)
def get_job(job_id: str) -> JobSummary:
    store = deps.job_store()
    deps.require_job(store, job_id)
    return next(s for s in _summaries(store) if s.job.id == job_id)


@router.patch("/jobs/{job_id}", response_model=Job)
def patch_job(job_id: str, body: JobPatchIn) -> Job:
    """Edit details and JD text. Status and dates are changed on the tracker (PATCH /tracker/{id})."""
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    changes = body.model_dump(exclude_none=True)
    if "description" in changes:
        try:
            changes["description"], _ = check_jd_text(changes["description"])
        except JDImportError as exc:
            raise _import_error(exc) from exc
    return store.update(Job.model_validate({**job.model_dump(), **changes}))


@router.delete("/jobs/{job_id}", status_code=204)
def remove_job(job_id: str) -> Response:
    """Delete the job with its analysis, match report, resume versions and exported files."""
    store = deps.job_store()
    deps.require_job(store, job_id)
    delete_job(store, deps.settings().output_dir, job_id)
    return Response(status_code=204)


# ---- analysis ---------------------------------------------------------------------


@router.get("/jobs/{job_id}/analysis", response_model=AnalysisView, tags=["analysis"])
def get_analysis(job_id: str) -> AnalysisView:
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    analysis = store.get_analysis(job_id)
    return AnalysisView(job=job, analysis=analysis, stale=bool(analysis and is_stale(analysis, job)))


@router.post("/jobs/{job_id}/analysis", response_model=AnalyzeOut, tags=["analysis"])
def run_analysis(job_id: str, body: AnalyzeIn) -> AnalyzeOut:
    """Run the deterministic parser. Re-analyzing replaces the user's edits, so it needs ``replace: true``."""
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    if store.get_analysis(job_id) is not None and not body.replace:
        raise ApiError(409, "analysis_exists", "This job already has an analysis. Re-analyzing discards your edits.")
    try:
        profile = deps.profile_store().load()
    except ProfileStoreError:
        profile = None
    result = analyze_job(job, profile)
    filled = {f: v for f, v in (("title", result.suggested_title), ("company", result.suggested_company),
                                ("location", result.suggested_location)) if v and not getattr(job, f)}
    if filled:
        job = store.update(job.model_copy(update=filled))
    analysis = store.save_analysis(result.analysis)
    return AnalyzeOut(analysis=analysis, job=job, filled=list(filled))


@router.put("/jobs/{job_id}/analysis", response_model=AnalysisView, tags=["analysis"])
def review_analysis(job_id: str, body: AnalysisReviewIn) -> AnalysisView:
    """Save the user's corrections. Any change clears confirmation."""
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    analysis = store.get_analysis(job_id)
    if analysis is None:
        raise ApiError(409, "analysis_missing", "Analyze this job first.")
    try:
        requirements = apply_requirement_edits(analysis.requirements,
                                               [r.model_dump(exclude_none=False) for r in body.requirements])
    except ValueError as exc:
        if hasattr(exc, "errors"):
            raise
        raise ApiError(422, "invalid_requirements", str(exc)) from exc
    updated = update_analysis(analysis, requirements=requirements, work_arrangement=body.work_arrangement,
                              experience_min_years=body.experience_min_years,
                              experience_max_years=body.experience_max_years)
    details = {"title": body.title, "company": body.company, "location": body.location}
    if any(getattr(job, k) != v for k, v in details.items()):
        job = store.update(job.model_copy(update=details))
        updated = updated.model_copy(update={"confirmed_at": None})
    saved = store.save_analysis(updated)
    return AnalysisView(job=job, analysis=saved, stale=is_stale(saved, job))


@router.post("/jobs/{job_id}/analysis/confirm", response_model=AnalysisView, tags=["analysis"])
def confirm_analysis(job_id: str) -> AnalysisView:
    store = deps.job_store()
    job = deps.require_job(store, job_id)
    analysis = store.get_analysis(job_id)
    if analysis is None:
        raise ApiError(409, "analysis_missing", "Analyze this job first.")
    if is_stale(analysis, job):
        raise ApiError(409, "analysis_stale", "The job description changed after this analysis. Re-analyze first.")
    if analysis.confirmed_at is None:
        analysis = store.save_analysis(analysis.model_copy(update={"confirmed_at": utc_now()}))
    return AnalysisView(job=job, analysis=analysis, stale=False)
