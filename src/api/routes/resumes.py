"""Resume tailoring and versions (mirrors the Resume Builder page).

Drafts are built only from master-profile evidence. Optional AI rewriting runs only when a provider is
configured and the request carries the user's consent. Versions are immutable: edits create a child
version, and only approved versions can be exported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse

from src.api import deps
from src.api.errors import ApiError, not_found
from src.api.models import (
    AiPreview,
    ApproveIn,
    ChangeRowView,
    EditIn,
    EditOut,
    ExportView,
    GenerateIn,
    GenerateOut,
    TailoringOptions,
    ValidationView,
    VersionDetail,
    VersionListItem,
    VersionSummary,
)
from src.api.routes.match import recommendations
from src.api.routes.system import provider_view
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStoreError
from src.schemas.export import ExportRecord
from src.schemas.profile import MasterProfile, RoleProfile
from src.schemas.resume import ResumeVersion
from src.services.export_service import ExportError, export_version
from src.services.llm.provider import get_provider, provider_status
from src.services.match_report_service import recommend_role_profiles, stale_reasons
from src.services.render.style import TEMPLATES
from src.services.resume_generator import build_draft
from src.services.resume_rewriter import build_request
from src.services.resume_service import apply_user_edits, generate_version
from src.services.resume_validation import change_summary, validate_resume

router = APIRouter(tags=["resumes"])

MEDIA = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "pdf": "application/pdf"}


def _summary(store: JobStore, v: ResumeVersion) -> dict:
    return dict(id=v.id, job_id=v.job_id, parent_id=v.parent_id, generator=v.generator, created_at=v.created_at,
                approved_at=v.approved_at, target_pages=v.target_pages, role_profile_id=v.role_profile_id,
                exported=store.get_export(v.id) is not None)


def _require_version(store: JobStore, version_id: str) -> ResumeVersion:
    version = store.get_resume_version(version_id)
    if version is None:
        raise not_found("This resume version")
    return version


def _context(store: JobStore, job_id: str):
    """Job, profile, roles, analysis and report, plus the reasons a draft can't be generated."""
    job = deps.require_job(store, job_id)
    profile_store = deps.profile_store()
    profile = profile_store.load()
    try:
        roles = profile_store.load_roles().role_profiles
    except ProfileStoreError:
        roles = []
    analysis, report = store.get_analysis(job_id), store.get_match_report(job_id)
    blockers: list[str] = []
    reasons: list[str] = []
    if profile is None:
        blockers.append("Create or import a master profile first.")
    elif analysis is None or report is None:
        blockers.append("This job needs a confirmed analysis and a match report first.")
    else:
        reasons = stale_reasons(report, analysis, profile)
        if reasons:
            blockers.append("The match report is out of date: " + " ".join(reasons)
                            + " Re-run matching before generating a new version.")
    return job, profile, roles, analysis, report, blockers, reasons


def _role(roles: list[RoleProfile], role_id: Optional[str]) -> Optional[RoleProfile]:
    if role_id is None:
        return None
    role = next((r for r in roles if r.id == role_id), None)
    if role is None:
        raise not_found("This role profile")
    return role


@router.get("/jobs/{job_id}/resumes", response_model=list[VersionSummary])
def list_job_versions(job_id: str) -> list[VersionSummary]:
    store = deps.job_store()
    deps.require_job(store, job_id)
    return [VersionSummary(**_summary(store, v)) for v in store.list_resume_versions(job_id)]


@router.get("/resumes", response_model=list[VersionListItem])
def list_all_versions() -> list[VersionListItem]:
    """Every resume version across jobs, newest first."""
    store = deps.job_store()
    out = [VersionListItem(**_summary(store, v), job_display_name=job.display_name)
           for job in store.list() for v in store.list_resume_versions(job.id)]
    return sorted(out, key=lambda v: v.created_at, reverse=True)


@router.get("/jobs/{job_id}/tailoring", response_model=TailoringOptions)
def tailoring_options(job_id: str) -> TailoringOptions:
    store = deps.job_store()
    job, profile, roles, analysis, report, blockers, reasons = _context(store, job_id)
    recs = (recommend_role_profiles(report, analysis, profile, roles)
            if profile and analysis and report else [])
    return TailoringOptions(job=job, blockers=blockers, stale_reasons=reasons, role_profiles=roles,
                            recommended_role_id=recs[0].id if recs else None,
                            role_recommendations=recommendations(recs),
                            provider_status=provider_view(deps.settings()),
                            is_sample_profile=bool(profile and profile.is_sample))


@router.post("/jobs/{job_id}/resumes/ai-preview", response_model=AiPreview)
def ai_preview(job_id: str, body: GenerateIn) -> AiPreview:
    """Exactly what would be sent to the AI provider. Nothing is sent by this call."""
    store = deps.job_store()
    job, profile, roles, analysis, report, blockers, _ = _context(store, job_id)
    if blockers:
        raise ApiError(409, "generation_blocked", blockers[0])
    status = provider_status(deps.settings())
    if not status.available:
        raise ApiError(409, "ai_unavailable", status.message)
    content, _ = build_draft(profile, analysis, report, role=_role(roles, body.role_profile_id),
                             target_pages=body.target_pages)
    request = build_request(content, profile, analysis, report, job.title)
    return AiPreview(provider=status.provider, model=status.model, system=request.system, user=request.user)


@router.post("/jobs/{job_id}/resumes", response_model=GenerateOut, status_code=201)
def generate(job_id: str, body: GenerateIn) -> GenerateOut:
    store = deps.job_store()
    job, profile, roles, analysis, report, blockers, _ = _context(store, job_id)
    if blockers:
        raise ApiError(409, "generation_blocked", blockers[0])
    provider = None
    if body.use_ai:
        if not body.consent:
            raise ApiError(422, "consent_required", "Tick the consent box to send this content to the AI provider.")
        provider = get_provider(deps.settings())
        if provider is None:
            raise ApiError(409, "ai_unavailable", provider_status(deps.settings()).message)
    outcome = generate_version(job, profile, analysis, report, role=_role(roles, body.role_profile_id),
                               target_pages=body.target_pages, provider=provider)
    saved = store.add_resume_version(outcome.version)
    return GenerateOut(version=saved, notes=outcome.notes, ai_failed=outcome.ai_failed)


def _export_view(record: ExportRecord) -> ExportView:
    docx, pdf = Path(record.docx_path), Path(record.pdf_path)
    return ExportView(record=record, failed=len(record.failed), warnings=len(record.warnings),
                      docx_available=docx.is_file(), pdf_available=pdf.is_file(),
                      docx_filename=docx.name, pdf_filename=pdf.name)


def _validation(version: ResumeVersion, profile: Optional[MasterProfile], store: JobStore
                ) -> Optional[ValidationView]:
    if profile is None:
        return None
    analysis, report = store.get_analysis(version.job_id), store.get_match_report(version.job_id)
    v = validate_resume(version, profile, analysis=analysis, report=report)
    return ValidationView(ok=v.ok, errors=v.errors, warnings=v.warnings, info=v.info,
                          estimated_lines=v.estimated_lines)


@router.get("/resumes/{version_id}", response_model=VersionDetail)
def get_version(version_id: str) -> VersionDetail:
    store = deps.job_store()
    version = _require_version(store, version_id)
    job = deps.require_job(store, version.job_id)
    profile = deps.profile_store().load()
    record = store.get_export(version_id)
    changes = [ChangeRowView(**vars(r)) for r in change_summary(version, profile)] if profile else []
    return VersionDetail(version=version, job=job, validation=_validation(version, profile, store),
                         changes=changes, export=_export_view(record) if record else None)


@router.post("/resumes/{version_id}/edits", response_model=EditOut)
def edit_version(version_id: str, body: EditIn) -> EditOut:
    """Save edits as a NEW version. Header facts (titles, employers, dates) are edited in the profile."""
    store = deps.job_store()
    version = _require_version(store, version_id)
    bullets = {(b.entry_id, b.evidence_id): (b.include, b.text) for b in body.bullets}
    new = apply_user_edits(version, summary_text=body.summary_text, bullets=bullets or None)
    if new is version:
        return EditOut(changed=False, version=version)
    return EditOut(changed=True, version=store.add_resume_version(new))


@router.post("/resumes/{version_id}/approve", response_model=VersionDetail)
def approve_version(version_id: str, body: ApproveIn) -> VersionDetail:
    """Approve after the user confirmed accuracy. Versions with validation errors can't be approved."""
    store = deps.job_store()
    version = _require_version(store, version_id)
    if version.approved_at:
        raise ApiError(409, "already_approved", "This version is already approved.")
    if not body.confirm:
        raise ApiError(422, "confirmation_required", "Confirm that you read this resume and everything is accurate.")
    validation = _validation(version, deps.profile_store().load(), store)
    if validation is None:
        raise ApiError(409, "profile_missing", "Create or import a master profile first.")
    if not validation.ok:
        raise ApiError(409, "validation_failed", "Fix the validation errors before approving.",
                       {"errors": validation.errors})
    store.approve_resume_version(version_id, body.note)
    return get_version(version_id)


@router.post("/resumes/{version_id}/export", response_model=ExportView)
def export(version_id: str) -> ExportView:
    """Render DOCX and PDF with the template and paper size from Settings, then run the export checks."""
    store = deps.job_store()
    version = _require_version(store, version_id)
    settings = deps.settings()
    job = store.get(version.job_id)
    try:
        record = export_version(version, output_dir=settings.output_dir, page_size=settings.page_size,
                                style=TEMPLATES[settings.template],
                                company=job.company if job else "", role=job.title if job else "")
    except ExportError as exc:
        raise ApiError(409, "export_failed", str(exc)) from exc
    return _export_view(store.save_export(record))


@router.get("/resumes/{version_id}/files/{kind}", response_class=FileResponse,
            responses={200: {"content": {MEDIA["docx"]: {}, MEDIA["pdf"]: {}}, "description": "Exported file"}})
def download(version_id: str, kind: Literal["docx", "pdf"]) -> FileResponse:
    """Stream an exported file. The path comes from the stored export record, never from the client."""
    store = deps.job_store()
    _require_version(store, version_id)
    record = store.get_export(version_id)
    if record is None:
        raise ApiError(404, "not_exported", "This version hasn't been exported yet.")
    path = Path(record.docx_path if kind == "docx" else record.pdf_path)
    if not path.is_file():
        raise ApiError(410, "file_missing", f"The {kind.upper()} file is no longer on disk. Export again.")
    return FileResponse(path, media_type=MEDIA[kind], filename=path.name)
