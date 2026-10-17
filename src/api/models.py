"""Request and response models for the adapter.

Stored data is returned as the existing schemas (``MasterProfile``, ``Job``, ``ResumeVersion`` ...).
The models here only add derived values the Streamlit pages compute for display (staleness,
effective match status, coverage) and wrap the services' dataclasses.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.analysis import JDAnalysis, Requirement, WorkArrangement
from src.schemas.capture import Capture
from src.schemas.export import ExportRecord
from src.schemas.job import ImportMethod, Job, JobStatus, SourcePlatform
from src.schemas.match import MatchReport, MatchStatus
from src.schemas.profile import MasterProfile, RoleProfile, TargetLength
from src.schemas.resume import ResumeVersion


class In(BaseModel):
    """Request bodies reject unknown fields, like the stored schemas do."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---- system / settings ------------------------------------------------------------


class Health(BaseModel):
    ok: bool
    app: str
    api_version: int


class Session(BaseModel):
    ok: bool


class ProviderStatusView(BaseModel):
    available: bool
    message: str
    provider: str
    model: str


class SettingsValues(BaseModel):
    local_only: bool
    llm_provider: str
    llm_model: str
    template: str
    page_size: str
    url_import_enabled: bool
    extension_enabled: bool
    extension_port: int


class SettingsView(BaseModel):
    values: SettingsValues = Field(description="Effective values (local-only mode forces some off)")
    saved: SettingsValues = Field(description="Values to show in the form: the saved choice where local-only overrides it")
    sources: dict[str, str] = Field(description="setting -> env | file | default | local-only")
    locked: dict[str, str] = Field(description="setting -> why it can't be changed here (set by an environment variable)")
    provider_status: ProviderStatusView
    keys_detected: dict[str, bool] = Field(description="API key environment variable -> whether it is set (never the value)")
    llm_providers: list[str]
    templates: list[str]
    page_sizes: list[str]
    default_models: dict[str, str]
    data_dir: str
    output_dir: str


class SettingsPatch(In):
    local_only: Optional[bool] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    template: Optional[str] = None
    page_size: Optional[str] = None
    url_import_enabled: Optional[bool] = None
    extension_enabled: Optional[bool] = None
    extension_port: Optional[int] = None


# ---- profile ----------------------------------------------------------------------


class EvidenceItem(BaseModel):
    id: str
    kind: str
    label: str
    parent_id: Optional[str] = None


class ProfileWarningView(BaseModel):
    item_id: Optional[str]
    message: str


class ProfileView(BaseModel):
    profile: Optional[MasterProfile]
    warnings: list[ProfileWarningView] = []
    evidence: list[EvidenceItem] = []


class ProfileSaveIn(In):
    profile: dict[str, Any] = Field(description="A MasterProfile. Validated after removed evidence is pruned, "
                                                "so deleting an item that skills link to works as in Streamlit")
    expected_version: Optional[int] = Field(description="profile_version the edit was based on; null if none exists")


class ProfileSaveOut(BaseModel):
    profile: MasterProfile
    changed: bool
    notes: list[str]


class VersionCheckIn(In):
    expected_version: Optional[int]


class DeleteConfirmIn(In):
    confirm: str = Field(description="Must be the exact word DELETE")


class ProfileVersionInfo(BaseModel):
    version: int
    updated_at: Optional[datetime]
    readable: bool


class ProfileImportPreview(BaseModel):
    profile: MasterProfile
    full_name: str
    experience: int
    projects: int
    skills: int
    is_sample: bool


# ---- role profiles ----------------------------------------------------------------


class RoleProfileView(BaseModel):
    role: RoleProfile
    dangling: list[str]


class RoleProfileIn(In):
    name: str = Field(min_length=1)
    target_role: str = ""
    evidence_ids: list[str] = []
    skill_ids: list[str] = []
    target_pages: TargetLength = TargetLength.ONE_PAGE


class DuplicateRoleIn(In):
    name: str = Field(min_length=1)


# ---- jobs -------------------------------------------------------------------------


class JobDraft(BaseModel):
    """Imported text held for review. Nothing is saved until ``POST /jobs``."""

    text: str
    method: ImportMethod
    text_notes: list[str] = Field(description="Notes about the text as imported; recomputed on save")
    source_notes: list[str] = Field(description="Notes about the import; saved with the job")
    title: str = ""
    company: str = ""
    location: str = ""
    source_url: str = ""
    source_label: str = ""
    suggested_platform: SourcePlatform = SourcePlatform.OTHER
    capture_id: Optional[str] = None


class TextDraftIn(In):
    text: str


class UrlDraftIn(In):
    url: str = Field(min_length=1, max_length=2048)


class JobCreateIn(In):
    text: str
    method: ImportMethod
    title: str = ""
    company: str = ""
    location: str = ""
    source_url: str = ""
    source_platform: Optional[SourcePlatform] = None
    source_label: str = ""
    source_notes: list[str] = []
    capture_id: Optional[str] = None
    on_duplicate: Literal["check", "separate", "merge"] = Field(
        default="check", description="check: 409 if it looks like a saved job; separate: save anyway; "
                                     "merge: update merge_into_id with this import")
    merge_into_id: Optional[str] = None


class DuplicateView(BaseModel):
    job: Job
    reason: str


class JobCreateOut(BaseModel):
    job: Job
    merged: bool


class JobPatchIn(In):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None


class JobSummary(BaseModel):
    job: Job
    display_name: str
    analysis_state: Literal["none", "draft", "confirmed"]
    has_match_report: bool
    versions: int
    approved_versions: int


# ---- analysis ---------------------------------------------------------------------


class AnalysisView(BaseModel):
    job: Job
    analysis: Optional[JDAnalysis]
    stale: bool = Field(description="The JD text changed after this analysis was made")


class AnalyzeIn(In):
    replace: bool = Field(default=False, description="Must be true to discard an existing analysis and re-analyze")


class AnalyzeOut(BaseModel):
    analysis: JDAnalysis
    job: Job
    filled: list[str] = Field(description="Blank job fields filled in from the JD; the user should check them")


class RequirementRow(In):
    """One edited requirement. Rows without ``id`` are new; omitted existing rows are deleted."""

    id: Optional[str] = None
    category: str
    importance: str
    text: str
    normalized_term: str = ""
    min_years: Optional[float] = None
    max_years: Optional[float] = None


class AnalysisReviewIn(In):
    title: str = ""
    company: str = ""
    location: str = ""
    work_arrangement: WorkArrangement
    experience_min_years: Optional[float] = None
    experience_max_years: Optional[float] = None
    requirements: list[RequirementRow]


# ---- match ------------------------------------------------------------------------


class GroupStatsView(BaseModel):
    total: int
    supported: int
    partial: int
    not_documented: int
    coverage: Optional[float]


class MatchSummaryView(BaseModel):
    groups: dict[str, GroupStatsView]
    overall: Optional[float]
    overrides: int
    formula: str = Field(description="How coverage is calculated. It is not an ATS score or hiring probability.")


class MatchRow(BaseModel):
    requirement: Requirement
    status: MatchStatus = Field(description="Effective status (the user's judgement if set)")
    evidence_ids: list[str] = Field(description="Effective evidence IDs")
    match_type: str
    explanation: str
    has_override: bool
    override_note: str = ""


class RecommendationView(BaseModel):
    id: str
    name: str
    score: float
    covered: list[str]


class MatchView(BaseModel):
    job: Job
    blockers: list[str] = Field(description="Why matching can't run yet; empty when it can")
    report: Optional[MatchReport]
    stale_reasons: list[str] = []
    rows: list[MatchRow] = []
    summary: Optional[MatchSummaryView] = None
    gaps: list[Requirement] = []
    role_recommendations: list[RecommendationView] = []
    project_recommendations: list[RecommendationView] = []
    evidence: list[EvidenceItem] = []
    profile_version: Optional[int] = None
    profile_confirmed: bool = False
    has_role_profiles: bool = False


class MatchRunOut(BaseModel):
    view: MatchView
    notes: list[str]


class OverrideIn(In):
    status: MatchStatus
    evidence_ids: list[str] = []
    note: str = ""


# ---- resumes ----------------------------------------------------------------------


class VersionSummary(BaseModel):
    id: str
    job_id: str
    parent_id: Optional[str]
    generator: str
    created_at: datetime
    approved_at: Optional[datetime]
    target_pages: TargetLength
    role_profile_id: Optional[str]
    exported: bool


class VersionListItem(VersionSummary):
    job_display_name: str


class TailoringOptions(BaseModel):
    job: Job
    blockers: list[str] = Field(description="Why a draft can't be generated yet; empty when it can")
    stale_reasons: list[str]
    role_profiles: list[RoleProfile]
    recommended_role_id: Optional[str]
    role_recommendations: list[RecommendationView]
    provider_status: ProviderStatusView
    is_sample_profile: bool


class GenerateIn(In):
    role_profile_id: Optional[str] = None
    target_pages: TargetLength = TargetLength.ONE_PAGE
    use_ai: bool = False
    consent: bool = Field(default=False, description="Required with use_ai: the user agreed to send the preview")


class AiPreview(BaseModel):
    provider: str
    model: str
    system: str
    user: str


class GenerateOut(BaseModel):
    version: ResumeVersion
    notes: list[str]
    ai_failed: Optional[str]


class ValidationView(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]
    info: list[str]
    estimated_lines: int


class ChangeRowView(BaseModel):
    section: str
    item: str
    change: str
    original: str
    final: str
    evidence: str


class ExportView(BaseModel):
    record: ExportRecord
    failed: int
    warnings: int
    docx_available: bool
    pdf_available: bool
    docx_filename: str
    pdf_filename: str


class VersionDetail(BaseModel):
    version: ResumeVersion
    job: Job
    validation: Optional[ValidationView] = Field(description="Null if the profile, analysis or report is missing")
    changes: list[ChangeRowView]
    export: Optional[ExportView]


class BulletEdit(In):
    entry_id: str = Field(description="Evidence ID of the experience/project entry")
    evidence_id: str = Field(description="First evidence ID of the bullet")
    include: bool = True
    text: str = ""


class EditIn(In):
    summary_text: Optional[str] = None
    bullets: list[BulletEdit] = []


class EditOut(BaseModel):
    changed: bool
    version: ResumeVersion


class ApproveIn(In):
    confirm: bool = Field(description="The user confirmed they read the resume and it is accurate")
    note: str = ""


# ---- tracker ----------------------------------------------------------------------


class TrackerRowView(BaseModel):
    job: Job
    display_name: str
    analysis_state: str
    required_coverage: Optional[float]
    versions: int
    approved: int
    resume_label: str
    exported: bool
    follow_up_due: bool


class TrackerView(BaseModel):
    rows: list[TrackerRowView]
    total: int = Field(description="Jobs before filtering")
    counts: dict[str, int] = Field(description="Jobs per status, before filtering")
    follow_ups_due: int


class ApplicationIn(In):
    status: JobStatus
    applied_on: Optional[date] = None
    follow_up_on: Optional[date] = None
    notes: str = ""
    resume_version_id: Optional[str] = None


class ApplicationOut(BaseModel):
    job: Job
    info: list[str]


class DuplicatePairView(BaseModel):
    first: Job
    second: Job
    reason: str
    loss_if_first_dropped: list[str]
    loss_if_second_dropped: list[str]


class MergeIn(In):
    keep_id: str
    drop_id: str


# ---- dashboard --------------------------------------------------------------------


class DashboardProfile(BaseModel):
    state: Literal["missing", "unreadable", "ok"]
    version: Optional[int] = None
    is_sample: bool = False
    confirmed_at: Optional[datetime] = None
    experience: int = 0
    projects: int = 0
    skills: int = 0
    warnings: int = 0


class DashboardJob(BaseModel):
    id: str
    display_name: str
    status: JobStatus
    updated_at: datetime
    follow_up_on: Optional[date] = None


class Dashboard(BaseModel):
    profile: DashboardProfile
    role_profiles: list[str]
    jobs_total: int
    jobs_analyzed: int
    jobs_matched: int
    jobs_with_approved_resume: int
    jobs_exported: int
    versions_total: int
    applications_tracked: int = Field(description="Jobs whose status is past 'saved'")
    recent_jobs: list[DashboardJob]
    recent_versions: list[VersionListItem]
    follow_ups_due: list[DashboardJob]
    captures_waiting: int


CaptureList = list[Capture]
