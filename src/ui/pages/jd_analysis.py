"""JD Analysis: run the rule-based parser on a saved job, correct the result, confirm it."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from src.persistence.job_store import JobStore, JobStoreError
from src.persistence.profile_store import ProfileStoreError
from src.schemas.analysis import Importance, JDAnalysis, RequirementCategory, WorkArrangement
from src.schemas.job import Job
from src.schemas.profile import MasterProfile, utc_now
from src.services.jd_analysis_service import analyze_job, apply_requirement_edits, is_stale, update_analysis
from src.services.profile_service import format_validation_error
from src.ui.state import flash, get_job_store, get_store, show_flashes
from src.ui.table_convert import models_to_rows

REQ_COLS = ["id", "category", "importance", "text", "normalized_term", "min_years", "max_years",
            "source_excerpt", "confidence", "origin"]
SELECTED_KEY = "analysis_job_id"


def _records(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _load_profile() -> Optional[MasterProfile]:
    try:
        return get_store().load()
    except ProfileStoreError:
        return None


def _status_label(job: Job, analysis_ids: set[str], confirmed: set[str]) -> str:
    state = "✅ confirmed" if job.id in confirmed else "📝 draft" if job.id in analysis_ids else "· not analyzed"
    return f"{job.display_name} ({job.imported_at:%Y-%m-%d}) {state}"


def render() -> None:
    st.title("JD Analysis")
    st.caption(
        "The app turns a saved job description into structured requirements using deterministic rules "
        "(no AI service, nothing leaves your computer). The result is a first draft. Correct it, then confirm."
    )
    show_flashes()
    store = get_job_store()
    try:
        jobs = store.list()
        analysis_ids = store.analysis_ids()
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        return
    if not jobs:
        st.info("No saved jobs yet. Import a job description on the **Job Import** page first.")
        return

    confirmed = set()
    for job_id in analysis_ids:
        try:
            a = store.get_analysis(job_id)
        except JobStoreError:
            continue
        if a and a.confirmed_at:
            confirmed.add(job_id)

    ids = [j.id for j in jobs]
    default = st.session_state.get(SELECTED_KEY)
    jobs_by_id = {j.id: j for j in jobs}
    job_id = st.selectbox(
        "Job", ids, index=ids.index(default) if default in ids else 0,
        format_func=lambda i: _status_label(jobs_by_id[i], analysis_ids, confirmed),
    )
    st.session_state[SELECTED_KEY] = job_id
    job = jobs_by_id[job_id]

    with st.expander("Original job description text"):
        st.text(job.description)

    try:
        analysis = store.get_analysis(job.id)
    except JobStoreError as exc:
        st.error(f"{exc} Re-analyze to replace it.")
        analysis = None

    if analysis is None:
        st.info("This job has not been analyzed yet.")
        if st.button("Analyze job description", type="primary"):
            _run_analysis(store, job)
        return

    _review(store, job, analysis)


def _run_analysis(store: JobStore, job: Job) -> None:
    result = analyze_job(job, _load_profile())
    filled = {}
    for field, value in (("title", result.suggested_title), ("company", result.suggested_company),
                         ("location", result.suggested_location)):
        if value and not getattr(job, field):
            filled[field] = value
    try:
        if filled:
            store.update(job.model_copy(update=filled))
        store.save_analysis(result.analysis)
    except JobStoreError as exc:
        st.error(f"Could not save the analysis. {exc}")
        return
    msg = f"Found {len(result.analysis.requirements)} requirement(s). Review and correct them below."
    if filled:
        msg += " Filled in blank " + ", ".join(filled) + " from the JD; please check."
    flash("success", msg)
    st.rerun()


def _review(store: JobStore, job: Job, analysis: JDAnalysis) -> None:
    stale = is_stale(analysis, job)
    if stale:
        st.warning("The job description text changed after this analysis was made. Re-analyze it, or review "
                   "the requirements carefully before confirming.")
    elif analysis.confirmed_at:
        st.success(f"Confirmed on {analysis.confirmed_at:%Y-%m-%d %H:%M} UTC. Any edit will require re-confirmation.")
    else:
        st.info("Draft: review the details and requirements, save any corrections, then confirm.")
    for w in analysis.warnings:
        st.warning(w)

    _summary(analysis)

    arrangements = list(WorkArrangement)
    categories = [c.value for c in RequirementCategory]
    importances = [i.value for i in Importance]
    with st.form("analysis-review"):
        st.markdown("**Job details**")
        c1, c2, c3 = st.columns(3)
        title = c1.text_input("Job title", value=job.title)
        company = c2.text_input("Company", value=job.company)
        location = c3.text_input("Location", value=job.location)
        c4, c5, c6 = st.columns(3)
        arrangement = c4.selectbox("Work arrangement", arrangements,
                                   index=arrangements.index(analysis.work_arrangement), format_func=lambda a: a.value)
        exp_min = c5.number_input("Experience: minimum years", min_value=0.0, max_value=60.0, step=0.5,
                                  value=analysis.experience_min_years)
        exp_max = c6.number_input("Experience: maximum years", min_value=0.0, max_value=60.0, step=0.5,
                                  value=analysis.experience_max_years)
        st.markdown("**Requirements**. Edit cells, add rows at the bottom, or select rows and delete them. "
                    "Excerpt, confidence and origin are filled in automatically.")
        df = st.data_editor(
            pd.DataFrame(models_to_rows(analysis.requirements, REQ_COLS), columns=REQ_COLS),
            # Key includes the save time so stale cell edits are never replayed onto refreshed data.
            num_rows="dynamic", key=f"req-editor-{job.id}-{analysis.updated_at.timestamp()}", hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "category": st.column_config.SelectboxColumn("Category", options=categories, required=True,
                                                             default="skill"),
                "importance": st.column_config.SelectboxColumn("Importance", options=importances, required=True,
                                                               default="required"),
                "text": st.column_config.TextColumn("Requirement", width="large", required=True),
                "normalized_term": st.column_config.TextColumn("Normalized term"),
                "min_years": st.column_config.NumberColumn("Min yrs", min_value=0, max_value=60),
                "max_years": st.column_config.NumberColumn("Max yrs", min_value=0, max_value=60),
                "source_excerpt": st.column_config.TextColumn("JD excerpt", disabled=True),
                "confidence": st.column_config.NumberColumn("Confidence", disabled=True, format="%.2f"),
                "origin": st.column_config.TextColumn("Origin", disabled=True),
            },
        )
        save = st.form_submit_button("Save review", type="primary")

    if save:
        try:
            requirements = apply_requirement_edits(analysis.requirements, _records(df))
            updated = update_analysis(analysis, requirements=requirements, work_arrangement=arrangement,
                                      experience_min_years=exp_min, experience_max_years=exp_max)
            details = {"title": title.strip(), "company": company.strip(), "location": location.strip()}
            if any(getattr(job, k) != v for k, v in details.items()):
                store.update(job.model_copy(update=details))
                updated = updated.model_copy(update={"confirmed_at": None})
            store.save_analysis(updated)
        except JobStoreError as exc:
            st.error(f"Could not save. {exc}")
            return
        except ValueError as exc:  # includes pydantic.ValidationError
            errors = getattr(exc, "errors", None)
            st.error("Could not save — please fix:\n" + (format_validation_error(exc) if callable(errors) else str(exc)))
            return
        flash("success", "Review saved." + ("" if updated.confirmed_at else " Confirm it when you're satisfied."))
        st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("Confirm analysis", type="primary", disabled=bool(analysis.confirmed_at) or stale,
                 help="Re-analyze first if the JD changed." if stale else None):
        store.save_analysis(analysis.model_copy(update={"confirmed_at": utc_now()}))
        flash("success", "Analysis confirmed. Next, open **Match Report** to compare it with your profile.")
        st.rerun()
    with c2.expander("Re-analyze from the JD text"):
        st.caption("Replaces the current requirements with a fresh parser draft. Your edits will be lost.")
        sure = st.checkbox("Discard my edits and re-analyze", key=f"reanalyze-chk-{job.id}")
        if st.button("Re-analyze", disabled=not sure, key=f"reanalyze-{job.id}"):
            _run_analysis(store, job)


def _summary(analysis: JDAnalysis) -> None:
    reqs = analysis.requirements
    skills = analysis.by_category(RequirementCategory.SKILL)
    exp = analysis.experience_min_years, analysis.experience_max_years
    exp_label = ("—" if exp == (None, None) else
                 f"{exp[0]:g}+ yrs" if exp[1] is None else
                 f"up to {exp[1]:g} yrs" if exp[0] is None else f"{exp[0]:g}–{exp[1]:g} yrs")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requirements", len(reqs))
    c2.metric("Required skills", sum(r.importance is Importance.REQUIRED for r in skills))
    c3.metric("Preferred skills", sum(r.importance is Importance.PREFERRED for r in skills))
    c4.metric("Experience", exp_label)
