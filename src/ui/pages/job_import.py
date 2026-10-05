"""Job Import: paste / upload / URL → review → save, plus the saved-jobs list."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from src.config import get_settings
from src.persistence.job_store import JobStore, JobStoreError
from src.schemas.job import ImportMethod, Job, JobStatus, SourcePlatform
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
from src.services.profile_service import format_validation_error
from src.services.url_import import UrlImportError, fetch_job_from_url
from src.ui.state import flash, get_job_store, show_flashes

DRAFT_KEY = "jd_draft"      # dict of reviewed-but-unsaved import fields
PENDING_KEY = "jd_pending"  # Job awaiting a duplicate decision

UNTRUSTED_NOTE = (
    "Job descriptions are treated as untrusted text: they are stored and shown, never followed as "
    "instructions. Only the extracted text and source URL are saved, not the web page."
)


def _set_draft(text: str, method: ImportMethod, text_notes: list[str],
               source_notes: Optional[list[str]] = None, **fields: str) -> None:
    """Hold imported text for review. ``source_notes`` describe the import and are saved with the job;
    ``text_notes`` describe the text as imported and are recomputed when the user saves."""
    st.session_state[DRAFT_KEY] = {"text": text, "method": method, "text_notes": text_notes,
                                   "source_notes": source_notes or [], **fields}
    st.session_state.pop(PENDING_KEY, None)


def render() -> None:
    st.title("Job Import")
    st.caption(
        "Bring in a job description from LinkedIn, Naukri or anywhere else. You review everything "
        "before it is saved. The app never applies to jobs for you."
    )
    show_flashes()
    store = get_job_store()
    try:
        jobs = store.list()
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        return

    if st.session_state.get(PENDING_KEY):
        _duplicate_decision(store, jobs)
    elif st.session_state.get(DRAFT_KEY):
        _review_form(store, jobs)
    else:
        _import_tabs()

    st.divider()
    _saved_jobs(store, jobs)


# ---- step 1: import -------------------------------------------------------------


def _import_tabs() -> None:
    st.subheader("1. Import a job description")
    paste, upload, url = st.tabs(["Paste text", "Upload file", "From URL"])

    with paste:
        text = st.text_area("Job description", height=260, placeholder="Paste the full job posting here…")
        if st.button("Review pasted text", type="primary"):
            try:
                clean, notes = check_jd_text(text)
            except JDImportError as exc:
                st.error(str(exc))
            else:
                _set_draft(clean, ImportMethod.PASTE, notes)
                st.rerun()

    with upload:
        st.caption(f"Text-based {', '.join(SUPPORTED_EXTENSIONS)} up to {MAX_UPLOAD_BYTES // 1_000_000} MB. "
                   "Scanned PDFs have no selectable text. Paste those instead.")
        uploaded = st.file_uploader("JD file", type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS])
        if st.button("Extract text", disabled=uploaded is None):
            try:
                clean, notes = check_jd_text(extract_text_from_file(uploaded.name, uploaded.getvalue()))
            except JDImportError as exc:
                st.error(str(exc))
            else:
                _set_draft(clean, ImportMethod.FILE, notes, source_label=uploaded.name)
                st.rerun()

    with url:
        settings = get_settings()
        if not settings.url_import_enabled:
            st.info("URL import is turned off (RESUME_OPTIMIZER_URL_IMPORT=off). Paste or upload the JD instead.")
            return
        st.caption(
            "Best effort: the app fetches the single public page you enter, respects the site's robots.txt, "
            "and stops at sign-in pages or human checks. LinkedIn job pages usually need sign-in, so "
            "**pasting is often the reliable route**."
        )
        url_value = st.text_input("Job page URL", placeholder="https://www.naukri.com/job-listings-…")
        if st.button("Fetch page", disabled=not url_value.strip()):
            with st.spinner("Fetching page…"):
                try:
                    result = fetch_job_from_url(url_value, timeout=settings.url_timeout_seconds)
                    clean, notes = check_jd_text(result.text)
                except (UrlImportError, JDImportError) as exc:
                    st.error(str(exc))
                    return
            _set_draft(
                clean, ImportMethod.URL, notes, result.notes, source_url=result.final_url,
                title=result.title, company=result.company, location=result.location,
            )
            st.rerun()


# ---- step 2: review -------------------------------------------------------------


def _review_form(store: JobStore, jobs: list[Job]) -> None:
    draft = st.session_state[DRAFT_KEY]
    st.subheader("2. Review and save")
    st.caption(UNTRUSTED_NOTE)
    for note in [*draft["source_notes"], *draft["text_notes"]]:
        st.warning(note)

    platforms = list(SourcePlatform)
    default_platform = infer_platform(draft.get("source_url", "")) if draft.get("source_url") else SourcePlatform.OTHER
    with st.form("jd-review"):
        c1, c2, c3 = st.columns(3)
        title = c1.text_input("Job title", value=draft.get("title", ""))
        company = c2.text_input("Company", value=draft.get("company", ""))
        location = c3.text_input("Location / work arrangement", value=draft.get("location", ""))
        c4, c5, c6 = st.columns([2, 1, 1])
        source_url = c4.text_input("Source URL (optional)", value=draft.get("source_url", ""))
        platform = c5.selectbox("Platform", platforms, index=platforms.index(default_platform),
                                format_func=lambda p: p.value.capitalize())
        source_label = c6.text_input("Source note (optional)", value=draft.get("source_label", ""))
        text = st.text_area("Job description text (edit to remove unrelated content)",
                            value=draft["text"], height=360)
        save = st.form_submit_button("Save job", type="primary")
    if st.button("Discard draft"):
        st.session_state.pop(DRAFT_KEY, None)
        st.rerun()

    if not save:
        return
    try:
        job = build_job(text, title=title, company=company, location=location, source_url=source_url,
                        source_platform=platform, import_method=draft["method"], source_label=source_label,
                        notes=draft["source_notes"])
    except JDImportError as exc:
        st.error(str(exc))
        return
    except ValueError as exc:  # pydantic.ValidationError
        errors = getattr(exc, "errors", None)
        st.error("Could not save — please fix:\n" + (format_validation_error(exc) if callable(errors) else str(exc)))
        return
    if find_duplicates(job, jobs):
        st.session_state[PENDING_KEY] = job
        st.rerun()
    _add(store, job)


def _add(store: JobStore, job: Job) -> None:
    try:
        store.add(job)
    except JobStoreError as exc:
        st.error(f"Could not save the job. {exc}")
        return
    st.session_state.pop(DRAFT_KEY, None)
    st.session_state.pop(PENDING_KEY, None)
    flash("success", f"Saved **{job.display_name}**. Next, open **JD Analysis** to extract its requirements.")
    st.rerun()


def _duplicate_decision(store: JobStore, jobs: list[Job]) -> None:
    job: Job = st.session_state[PENDING_KEY]
    matches = find_duplicates(job, jobs)
    if not matches:  # the matching job was deleted meanwhile
        _add(store, job)
        return
    st.subheader("2. Possible duplicate")
    st.warning("This looks like a job you already saved:\n" + "\n".join(
        f"- **{m.job.display_name}** (imported {m.job.imported_at:%Y-%m-%d}), {m.reason}" for m in matches))
    target = matches[0].job
    c1, c2, c3 = st.columns(3)
    if c1.button(f"Update “{target.display_name}” with this import", type="primary"):
        try:
            store.update(merge_import_into(target, job))
        except JobStoreError as exc:
            st.error(f"Could not update the job. {exc}")
            return
        st.session_state.pop(DRAFT_KEY, None)
        st.session_state.pop(PENDING_KEY, None)
        flash("success", f"Updated **{target.display_name}**. Its status and notes were kept.")
        st.rerun()
    if c2.button("Save as a separate job"):
        _add(store, job)
    if c3.button("Back to review"):
        st.session_state.pop(PENDING_KEY, None)
        st.rerun()


# ---- saved jobs -----------------------------------------------------------------


def _saved_jobs(store: JobStore, jobs: list[Job]) -> None:
    st.subheader(f"Saved jobs ({len(jobs)})")
    if not jobs:
        st.info("No saved jobs yet.")
        return
    statuses: list[Optional[JobStatus]] = [None, *JobStatus]
    status = st.selectbox("Filter by status", statuses, format_func=lambda s: "All" if s is None else s.value)
    shown = [j for j in jobs if status is None or j.status is status]
    for job in shown:
        label = f"{job.display_name}" + (f" · {job.location}" if job.location else "")
        with st.expander(f"{label}  ·  {job.status.value}  ·  {job.imported_at:%Y-%m-%d}"):
            meta = [f"ID `{job.id}`", f"via {job.import_method.value}", job.source_platform.value]
            if job.source_url:
                meta.append(f"[source]({job.source_url})")
            st.caption(" · ".join(meta))
            for note in job.import_notes:
                st.caption(f"⚠️ {note}")
            _edit_job_form(store, job)
            confirm = st.checkbox("Confirm delete", key=f"del-chk-{job.id}")
            if st.button("Delete job", key=f"del-{job.id}", disabled=not confirm):
                store.delete(job.id)
                flash("success", f"Deleted **{job.display_name}**.")
                st.rerun()

    with st.expander("Delete all job records"):
        typed = st.text_input("Type DELETE to confirm", key="del-all-jobs-confirm")
        if st.button("Delete all job records", disabled=typed != "DELETE"):
            count = store.delete_all()
            flash("success", f"Deleted {count} job record(s).")
            st.rerun()


def _edit_job_form(store: JobStore, job: Job) -> None:
    with st.form(f"job-{job.id}"):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        title = c1.text_input("Job title", value=job.title)
        company = c2.text_input("Company", value=job.company)
        location = c3.text_input("Location", value=job.location)
        statuses = list(JobStatus)
        status = c4.selectbox("Status", statuses, index=statuses.index(job.status), format_func=lambda s: s.value)
        notes = st.text_area("Notes", value=job.notes, height=80)
        description = st.text_area("Job description text", value=job.description, height=240)
        if not st.form_submit_button("Save changes"):
            return
    try:
        text, _ = check_jd_text(description)
        store.update(job.model_copy(update={"title": title.strip(), "company": company.strip(),
                                            "location": location.strip(), "status": status,
                                            "notes": notes, "description": text}))
    except (JDImportError, JobStoreError, ValueError) as exc:
        st.error(f"Could not save: {exc}")
        return
    flash("success", f"Saved changes to **{title or 'job'}**.")
    st.rerun()
