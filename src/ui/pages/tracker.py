"""Application Tracker: every job's status, dates, coverage and resume, with filters, CSV export and merging."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import get_settings
from src.persistence.job_store import JobStore, JobStoreError
from src.schemas.job import JobStatus, SourcePlatform
from src.services.tracker_service import (
    TrackerError,
    TrackerRow,
    build_rows,
    delete_job,
    duplicate_pairs,
    filter_rows,
    merge_jobs,
    merge_loss,
    to_csv,
    update_application,
)
from src.ui.state import flash, get_job_store, show_flashes

SELECTED_KEY = "tracker_job_id"


def _pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


def render() -> None:
    st.title("Application Tracker")
    st.caption("Track where you applied and with which resume. You record statuses and dates yourself; "
               "the app never applies or contacts anyone for you.")
    show_flashes()
    store = get_job_store()
    try:
        rows = build_rows(store)
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        return
    if not rows:
        st.info("No jobs yet. Import one on the **Job Import** page.")
        return

    due = [r for r in rows if r.follow_up_due]
    if due:
        st.warning("Follow-ups due: " + "; ".join(f"**{r.job.display_name}** ({r.job.follow_up_on:%Y-%m-%d})"
                                                   for r in due))
    counts = {s: sum(r.job.status is s for r in rows) for s in JobStatus}
    cols = st.columns(5)
    for col, s in zip(cols, [JobStatus.SAVED, JobStatus.APPLIED, JobStatus.INTERVIEWING, JobStatus.OFFER,
                             JobStatus.REJECTED]):
        col.metric(s.value.capitalize(), counts[s])

    shown = _filters(rows)
    _table(shown)
    _csv(shown)
    if shown:
        _editor(store, shown)
    _duplicates(store)


def _filters(rows: list[TrackerRow]) -> list[TrackerRow]:
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    statuses = c1.multiselect("Status", list(JobStatus), default=list(JobStatus), format_func=lambda s: s.value)
    platforms = c2.multiselect("Platform", list(SourcePlatform), default=list(SourcePlatform),
                               format_func=lambda p: p.value)
    search = c3.text_input("Search company, role, location, notes")
    due_only = c4.checkbox("Follow-up due")
    return filter_rows(rows, statuses=statuses, platforms=platforms, search=search, due_only=due_only)


def _table(rows: list[TrackerRow]) -> None:
    if not rows:
        st.info("No jobs match these filters.")
        return
    st.dataframe(pd.DataFrame([{
        "Company": r.job.company, "Role": r.job.title or "(untitled)", "Location": r.job.location,
        "Status": r.job.status.value, "Applied": r.job.applied_on, "Follow-up": r.job.follow_up_on,
        "Required coverage": _pct(r.required_coverage), "Analysis": r.analysis_state,
        "Resumes": f"{r.approved}/{r.versions} approved", "Using": r.resume_label or "—",
        "Exported": "yes" if r.exported else "", "Platform": r.job.source_platform.value,
        "Imported": f"{r.job.imported_at:%Y-%m-%d}",
    } for r in rows]), hide_index=True)


def _csv(rows: list[TrackerRow]) -> None:
    c1, c2 = st.columns([3, 1])
    include_jd = c2.checkbox("Include JD text", help="Adds each job description to the CSV.")
    c1.download_button("Download CSV of these jobs", data=to_csv(rows, include_jd_text=include_jd),
                       file_name=f"applications_{date.today():%Y%m%d}.csv", mime="text/csv", disabled=not rows)


def _editor(store: JobStore, rows: list[TrackerRow]) -> None:
    st.subheader("Update an application")
    by_id = {r.job.id: r for r in rows}
    ids = list(by_id)
    default = st.session_state.get(SELECTED_KEY)
    job_id = st.selectbox("Job", ids, index=ids.index(default) if default in ids else 0,
                          format_func=lambda i: f"{by_id[i].job.display_name} ({by_id[i].job.status.value})")
    st.session_state[SELECTED_KEY] = job_id
    job = by_id[job_id].job
    versions = store.list_resume_versions(job.id)
    labels = {v.id: f"{v.id} · {v.created_at:%Y-%m-%d}" + (" · approved" if v.approved_at else " · draft")
              for v in versions}
    options = [None] + [v.id for v in sorted(versions, key=lambda v: v.approved_at is None)]
    if job.source_url:
        st.caption(f"Source: [{job.source_url}]({job.source_url})")

    statuses = list(JobStatus)
    with st.form(f"tracker-{job.id}"):
        c1, c2, c3 = st.columns(3)
        status = c1.selectbox("Status", statuses, index=statuses.index(job.status), format_func=lambda s: s.value)
        applied = c2.date_input("Applied on", value=job.applied_on, format="YYYY-MM-DD",
                                min_value=date(2000, 1, 1), max_value=date.today())
        follow_up = c3.date_input("Follow up on", value=job.follow_up_on, format="YYYY-MM-DD",
                                  min_value=date(2000, 1, 1), max_value=date.today() + timedelta(days=3 * 365))
        version_id = st.selectbox("Resume used", options,
                                  index=options.index(job.resume_version_id) if job.resume_version_id in options else 0,
                                  format_func=lambda v: "None" if v is None else labels[v])
        notes = st.text_area("Notes", value=job.notes, height=90)
        save = st.form_submit_button("Save", type="primary")
    if save:
        try:
            _, info = update_application(store, job, status=status, applied_on=applied, follow_up_on=follow_up,
                                         notes=notes, resume_version_id=version_id)
        except (TrackerError, JobStoreError) as exc:
            st.error(str(exc))
            return
        flash("success", f"Saved **{job.display_name}**.")
        for note in info:
            flash("info", note)
        st.rerun()

    if job.resume_version_id:
        record = store.get_export(job.resume_version_id)
        if record:
            c1, c2 = st.columns(2)
            for col, path, label in ((c1, record.docx_path, "DOCX"), (c2, record.pdf_path, "PDF")):
                file = Path(path)
                if file.is_file():
                    col.download_button(f"Download {label} used", data=file.read_bytes(), file_name=file.name,
                                        key=f"tr-dl-{label}-{job.id}")

    with st.expander("Delete this job"):
        st.caption("Deletes the job with its analysis, match report, resume versions and exported files.")
        sure = st.checkbox("I understand this can't be undone", key=f"tr-del-chk-{job.id}")
        if st.button("Delete job", disabled=not sure, key=f"tr-del-{job.id}"):
            delete_job(store, get_settings().output_dir, job.id)
            flash("success", f"Deleted **{job.display_name}**.")
            st.rerun()


def _duplicates(store: JobStore) -> None:
    pairs = duplicate_pairs(store.list())
    if not pairs:
        return
    with st.expander(f"Possible duplicates ({len(pairs)})"):
        st.caption("Merging keeps the record you choose, fills its blank details from the other, appends the "
                   "other's notes, then deletes the other record. Nothing is merged automatically.")
        for i, pair in enumerate(pairs):
            a, b = pair.first, pair.second
            st.markdown(f"**{a.display_name}** (imported {a.imported_at:%Y-%m-%d}, {a.status.value}) and "
                        f"**{b.display_name}** (imported {b.imported_at:%Y-%m-%d}, {b.status.value}): {pair.reason}.")
            keep_id = st.radio("Keep", [a.id, b.id], key=f"dup-keep-{i}", horizontal=True,
                               format_func=lambda j: f"{(a if j == a.id else b).display_name} ({j})")
            drop_id = b.id if keep_id == a.id else a.id
            lost = merge_loss(store, drop_id)
            if lost:
                st.warning("The other record's " + ", ".join(lost).replace("its ", "") + " will be deleted.")
            sure = st.checkbox("Merge these two", key=f"dup-chk-{i}")
            if st.button("Merge", disabled=not sure, key=f"dup-merge-{i}"):
                try:
                    merged = merge_jobs(store, keep_id, drop_id, get_settings().output_dir)
                except (TrackerError, JobStoreError) as exc:
                    st.error(str(exc))
                    return
                flash("success", f"Merged into **{merged.display_name}**.")
                st.rerun()
            st.divider()
