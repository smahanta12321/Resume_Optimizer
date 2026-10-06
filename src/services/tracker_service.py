"""Application tracker: per-job overview, filters, status/date updates, CSV export, duplicate merge.

The app never applies on the user's behalf; statuses and dates are what the user records.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from src.persistence.job_store import JobStore, JobStoreError
from src.schemas.analysis import Importance
from src.schemas.job import Job, JobStatus, SourcePlatform
from src.services.export_service import delete_job_outputs
from src.services.jd_import_service import find_duplicates
from src.services.match_report_service import summarize

logger = logging.getLogger(__name__)

APPLIED_STATES = {JobStatus.APPLIED, JobStatus.INTERVIEWING, JobStatus.OFFER, JobStatus.REJECTED}
CLOSED_STATES = {JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.ARCHIVED}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class TrackerError(ValueError):
    """Invalid tracker change. Message is user-facing."""


@dataclass
class TrackerRow:
    job: Job
    analysis_state: str            # none | draft | confirmed
    required_coverage: Optional[float]
    versions: int
    approved: int
    resume_label: str              # selected version, if any
    exported: bool
    follow_up_due: bool


def build_rows(store: JobStore, today: Optional[date] = None) -> list[TrackerRow]:
    today = today or date.today()
    counts = store.resume_counts()
    rows = []
    for job in store.list():
        try:
            analysis = store.get_analysis(job.id)
            report = store.get_match_report(job.id)
            selected = store.get_resume_version(job.resume_version_id) if job.resume_version_id else None
            exported = bool(selected and store.get_export(selected.id))
        except JobStoreError:
            analysis = report = selected = None
            exported = False
        coverage = None
        if analysis and report:
            coverage = summarize(report, analysis).groups[Importance.REQUIRED].coverage
        state = "none" if analysis is None else "confirmed" if analysis.confirmed_at else "draft"
        label = ""
        if selected:
            label = f"{selected.id}" + (" (approved)" if selected.approved_at else " (draft)")
        versions, approved = counts.get(job.id, (0, 0))
        rows.append(TrackerRow(job, state, coverage, versions, approved, label, exported, is_follow_up_due(job, today)))
    return rows


def is_follow_up_due(job: Job, today: date) -> bool:
    return bool(job.follow_up_on and job.follow_up_on <= today and job.status not in CLOSED_STATES)


def filter_rows(rows: list[TrackerRow], *, statuses: Optional[Iterable[JobStatus]] = None,
                platforms: Optional[Iterable[SourcePlatform]] = None, search: str = "",
                due_only: bool = False) -> list[TrackerRow]:
    statuses = set(statuses) if statuses is not None else None
    platforms = set(platforms) if platforms is not None else None
    needle = search.strip().casefold()
    out = []
    for r in rows:
        if statuses is not None and r.job.status not in statuses:
            continue
        if platforms is not None and r.job.source_platform not in platforms:
            continue
        if needle and needle not in " ".join([r.job.title, r.job.company, r.job.location, r.job.notes]).casefold():
            continue
        if due_only and not r.follow_up_due:
            continue
        out.append(r)
    return out


def update_application(store: JobStore, job: Job, *, status: JobStatus, applied_on: Optional[date],
                       follow_up_on: Optional[date], notes: str, resume_version_id: Optional[str],
                       today: Optional[date] = None) -> tuple[Job, list[str]]:
    """Validate and save the user's application details. Returns the saved job and info notes."""
    today = today or date.today()
    info: list[str] = []
    if resume_version_id:
        version = store.get_resume_version(resume_version_id)
        if version is None or version.job_id != job.id:
            raise TrackerError("That resume version doesn't belong to this job.")
        if version.approved_at is None:
            info.append("The selected resume version isn't approved yet.")
    if status in APPLIED_STATES and applied_on is None:
        applied_on = today
        info.append(f"Applied date set to today ({today:%Y-%m-%d}); change it if you applied earlier.")
    if applied_on and applied_on > today:
        raise TrackerError("The applied date is in the future.")
    if applied_on and follow_up_on and follow_up_on < applied_on:
        raise TrackerError("The follow-up date is before the applied date.")
    saved = store.update(job.model_copy(update={
        "status": status, "applied_on": applied_on, "follow_up_on": follow_up_on, "notes": notes,
        "resume_version_id": resume_version_id or None}))
    logger.info("event=application_updated job_id=%s status=%s", job.id, status.value)
    return saved, info


def follow_ups_due(jobs: Iterable[Job], today: Optional[date] = None) -> list[Job]:
    today = today or date.today()
    return sorted((j for j in jobs if is_follow_up_due(j, today)), key=lambda j: j.follow_up_on)


def _cell(value: object) -> str:
    """Neutralize spreadsheet formula injection (cells starting with = + - @ …)."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def to_csv(rows: list[TrackerRow], *, include_jd_text: bool = False) -> str:
    columns = ["company", "role", "location", "status", "applied_on", "follow_up_on", "imported_on", "platform",
               "source_url", "required_coverage", "resume_versions", "approved_versions", "selected_resume",
               "notes"] + (["jd_text"] if include_jd_text else [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        j = r.job
        values = [j.company, j.title, j.location, j.status.value, j.applied_on or "", j.follow_up_on or "",
                  f"{j.imported_at:%Y-%m-%d}", j.source_platform.value, j.source_url,
                  "" if r.required_coverage is None else f"{r.required_coverage:.0%}", r.versions, r.approved,
                  r.resume_label, j.notes] + ([j.description] if include_jd_text else [])
        writer.writerow([_cell(v) for v in values])
    return buf.getvalue()


# ---- duplicates -------------------------------------------------------------------


@dataclass
class DuplicatePair:
    first: Job
    second: Job
    reason: str


def duplicate_pairs(jobs: list[Job]) -> list[DuplicatePair]:
    pairs, seen = [], set()
    for job in jobs:
        for m in find_duplicates(job, jobs):
            key = tuple(sorted((job.id, m.job.id)))
            if key not in seen:
                seen.add(key)
                older, newer = sorted((job, m.job), key=lambda j: j.imported_at)
                pairs.append(DuplicatePair(older, newer, m.reason))
    return pairs


def merge_loss(store: JobStore, drop_id: str) -> list[str]:
    """What deleting the merged-away job removes, for the confirmation message."""
    lost = []
    if store.get_analysis(drop_id):
        lost.append("its JD analysis")
    if store.get_match_report(drop_id):
        lost.append("its match report")
    versions, approved = store.resume_counts().get(drop_id, (0, 0))
    if versions:
        lost.append(f"{versions} resume version(s) ({approved} approved) and any exported files")
    return lost


def merge_jobs(store: JobStore, keep_id: str, drop_id: str, output_dir: Path) -> Job:
    """Keep one record, fill its blanks from the other, append the other's notes, then delete the other."""
    if keep_id == drop_id:
        raise TrackerError("Choose two different jobs to merge.")
    keep, drop = store.get(keep_id), store.get(drop_id)
    if keep is None or drop is None:
        raise TrackerError("One of these jobs no longer exists.")
    update: dict = {}
    for name in ("title", "company", "location", "source_label"):
        if not getattr(keep, name) and getattr(drop, name):
            update[name] = getattr(drop, name)
    if not keep.source_url and drop.source_url:
        update.update(source_url=drop.source_url, canonical_url=drop.canonical_url,
                      source_platform=drop.source_platform)
    if keep.status is JobStatus.SAVED and drop.status is not JobStatus.SAVED:
        update.update(status=drop.status, applied_on=keep.applied_on or drop.applied_on)
    for name in ("applied_on", "follow_up_on"):
        if getattr(keep, name) is None and getattr(drop, name) is not None and name not in update:
            update[name] = getattr(drop, name)
    if drop.notes.strip():
        header = f"[Merged from “{drop.display_name}”, imported {drop.imported_at:%Y-%m-%d}]"
        update["notes"] = "\n\n".join(x for x in (keep.notes.strip(), f"{header}\n{drop.notes.strip()}") if x)
    merged = store.update(keep.model_copy(update=update)) if update else keep
    store.delete(drop_id)
    delete_job_outputs(output_dir, drop_id)
    logger.info("event=jobs_merged keep=%s drop=%s", keep_id, drop_id)
    return merged


def delete_job(store: JobStore, output_dir: Path, job_id: str) -> bool:
    """Delete a job, everything derived from it, and its exported files."""
    deleted = store.delete(job_id)
    delete_job_outputs(output_dir, job_id)
    return deleted
