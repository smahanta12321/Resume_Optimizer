"""Match Report: evidence-backed requirement coverage for a confirmed JD analysis."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from src.persistence.job_store import JobStore, JobStoreError
from src.persistence.profile_store import ProfileStoreError
from src.schemas.analysis import Importance, JDAnalysis, RequirementCategory
from src.schemas.job import Job
from src.schemas.match import MatchReport, MatchStatus
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
from src.services.matching_service import build_index, build_match_report
from src.ui.state import flash, get_job_store, get_store, sample_banner, show_flashes

STATUS_ICON = {MatchStatus.SUPPORTED: "✅", MatchStatus.PARTIAL: "🟡", MatchStatus.NOT_DOCUMENTED: "⬜"}
STATUS_LABEL = {MatchStatus.SUPPORTED: "supported", MatchStatus.PARTIAL: "partial",
                MatchStatus.NOT_DOCUMENTED: "not documented"}
SELECTED_KEY = "match_job_id"


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.0%}"


def _req_label(req) -> str:
    term = req.normalized_term if req.normalized_term and req.normalized_term != "overall" else ""
    text = req.text if len(req.text) <= 70 else req.text[:69] + "…"
    return f"[{req.category.value}] {term or text}"


def render() -> None:
    st.title("Match Report")
    st.caption(
        "Compares a confirmed JD analysis with your master profile. Each requirement is marked **supported**, "
        "**partial** or **not documented**, citing the evidence items behind it. Only your recorded evidence "
        "counts; nothing is inferred or invented."
    )
    show_flashes()
    jobs_store = get_job_store()
    try:
        profile = get_store().load()
    except ProfileStoreError as exc:
        st.error(f"Your master profile could not be loaded. {exc}")
        return
    if profile is None:
        st.warning("Create or import a master profile first (Master Profile page).")
        return
    try:
        jobs = jobs_store.list()
        analyzed = jobs_store.analysis_ids()
        reported = jobs_store.match_report_ids()
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        return
    candidates = [j for j in jobs if j.id in analyzed]
    if not candidates:
        st.info("No analyzed jobs yet. Import a job, then analyze and confirm it on the **JD Analysis** page.")
        return

    sample_banner(profile.is_sample)
    if not profile.confirmed_at:
        st.warning(f"Profile v{profile.profile_version} has not been confirmed. Matching uses it as-is; review "
                   "and confirm it on the Master Profile page so the report rests on checked facts.")

    ids = [j.id for j in candidates]
    by_id = {j.id: j for j in candidates}
    default = st.session_state.get(SELECTED_KEY)
    job_id = st.selectbox("Job", ids, index=ids.index(default) if default in ids else 0,
                          format_func=lambda i: f"{by_id[i].display_name} ({by_id[i].imported_at:%Y-%m-%d})"
                          + (" · report" if i in reported else ""))
    st.session_state[SELECTED_KEY] = job_id
    job = by_id[job_id]

    try:
        analysis = jobs_store.get_analysis(job.id)
        report = jobs_store.get_match_report(job.id)
    except JobStoreError as exc:
        st.error(str(exc))
        return
    if analysis is None:
        st.info("This job has no analysis yet.")
        return
    if is_stale(analysis, job):
        st.error("The JD text changed after it was analyzed. Re-analyze and confirm it on **JD Analysis** first.")
        return
    if not analysis.confirmed_at:
        st.warning("Confirm this job's analysis on the **JD Analysis** page before matching. Matching against "
                   "unreviewed requirements would give a misleading report.")
        return
    if not analysis.requirements:
        st.info("The analysis has no requirements to match. Add them on the **JD Analysis** page.")
        return

    if report is None:
        st.info("No match report yet for this job.")
        if st.button("Run matching", type="primary"):
            _run(jobs_store, analysis, profile, None)
        return

    reasons = stale_reasons(report, analysis, profile)
    if reasons:
        st.warning("This report is out of date: " + " ".join(reasons) + " Re-run matching (your judgements are kept).")
    if st.button("Re-run matching", type="primary" if reasons else "secondary"):
        _run(jobs_store, analysis, profile, report)
    st.caption(f"Matched against profile v{report.profile_version} on {report.updated_at:%Y-%m-%d %H:%M} UTC "
               f"using `{report.matcher}`.")

    _summary(report, analysis)
    labels = _evidence_labels(profile)
    _table(report, analysis, labels)
    _override_form(jobs_store, report, analysis, profile, labels)
    _gaps(report, analysis)
    _recommendations(report, analysis, profile)


def _run(store: JobStore, analysis: JDAnalysis, profile: MasterProfile, previous: Optional[MatchReport]) -> None:
    report, notes = build_match_report(analysis, profile, previous=previous)
    try:
        store.save_match_report(report)
    except JobStoreError as exc:
        st.error(f"Could not save the report. {exc}")
        return
    flash("success", f"Matched {len(report.matches)} requirement(s) against profile v{profile.profile_version}.")
    for note in notes:
        flash("warning", note)
    st.rerun()


def _evidence_labels(profile: MasterProfile) -> dict[str, str]:
    return {d.id: d.label for d in build_index(profile).docs}


def _summary(report: MatchReport, analysis: JDAnalysis) -> None:
    s = summarize(report, analysis)
    req, pref = s.groups[Importance.REQUIRED], s.groups[Importance.PREFERRED]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Required coverage", _pct(req.coverage),
              help=f"{req.supported} supported, {req.partial} partial, {req.not_documented} not documented")
    c2.metric("Preferred coverage", _pct(pref.coverage),
              help=f"{pref.supported} supported, {pref.partial} partial, {pref.not_documented} not documented")
    c3.metric("Overall coverage", _pct(s.overall))
    c4.metric("Your judgements", s.overrides)
    with st.expander("How these numbers are calculated"):
        st.markdown(FORMULA)
        rows = [{"Importance": i.value, "Total": g.total, "Supported": g.supported, "Partial": g.partial,
                 "Not documented": g.not_documented, "Coverage": _pct(g.coverage)} for i, g in s.groups.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True)


def _table(report: MatchReport, analysis: JDAnalysis, labels: dict[str, str]) -> None:
    st.subheader("Requirements")
    c1, c2 = st.columns(2)
    statuses = c1.multiselect("Status", list(MatchStatus), default=list(MatchStatus),
                              format_func=lambda s: STATUS_LABEL[s])
    categories = c2.multiselect("Category", list(RequirementCategory), default=list(RequirementCategory),
                                format_func=lambda c: c.value)
    by_req = report.by_requirement()
    rows = []
    for req in analysis.requirements:
        m = by_req.get(req.id)
        if m is None or m.effective_status not in statuses or req.category not in categories:
            continue
        status = m.effective_status
        rows.append({
            "Status": f"{STATUS_ICON[status]} {STATUS_LABEL[status]}" + (" (yours)" if m.override else ""),
            "Importance": req.importance.value,
            "Category": req.category.value,
            "Requirement": req.text,
            "Match": "your judgement" if m.override else m.match_type.value,
            "Evidence": "; ".join(labels.get(e, f"(removed) {e}") for e in m.effective_evidence_ids),
            "Why": (m.override.note or "Set by you.") if m.override else m.explanation,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     column_config={"Requirement": st.column_config.TextColumn(width="medium"),
                                    "Why": st.column_config.TextColumn(width="large")})
    else:
        st.info("No requirements match these filters.")


def _override_form(store: JobStore, report: MatchReport, analysis: JDAnalysis, profile: MasterProfile,
                   labels: dict[str, str]) -> None:
    with st.expander("Correct a result"):
        st.caption("If the matcher missed or misjudged something, record your judgement. Supported and partial "
                   "must cite at least one evidence item from your profile. If the evidence isn't there yet, "
                   "add it to the master profile first.")
        reqs = {r.id: r for r in analysis.requirements}
        req_id = st.selectbox("Requirement", list(reqs), format_func=lambda i: _req_label(reqs[i]),
                              key="override-req")
        current = report.by_requirement()[req_id]
        statuses = list(MatchStatus)
        with st.form("override-form"):
            status = st.radio("Status", statuses, horizontal=True, format_func=lambda s: STATUS_LABEL[s],
                              index=statuses.index(current.effective_status))
            evidence = st.multiselect("Evidence", list(labels), format_func=lambda e: labels[e],
                                      default=[e for e in current.effective_evidence_ids if e in labels])
            note = st.text_input("Note (why)", value=current.override.note if current.override else "")
            save = st.form_submit_button("Save my judgement")
        if save:
            try:
                store.save_match_report(set_override(report, req_id, status, evidence, note, profile))
            except (OverrideError, JobStoreError) as exc:
                st.error(str(exc))
                return
            flash("success", "Saved your judgement.")
            st.rerun()
        if current.override and st.button("Clear my judgement"):
            store.save_match_report(clear_override(report, req_id))
            flash("success", "Cleared. The matcher's result applies again.")
            st.rerun()


def _gaps(report: MatchReport, analysis: JDAnalysis) -> None:
    st.subheader("Gaps")
    missing = gaps(report, analysis)
    if not missing:
        st.success("Every required and preferred requirement has at least some documented evidence.")
        return
    st.markdown("\n".join(f"- **{r.importance.value}**: {r.text}" for r in missing))
    st.caption("These won't appear in a tailored resume. If you do have this experience, add it to your master "
               "profile with real evidence and re-run matching. Otherwise, leave it out.")


def _recommendations(report: MatchReport, analysis: JDAnalysis, profile: MasterProfile) -> None:
    st.subheader("Recommendations")
    st.caption("Based on which evidence supports the matched requirements, weighted required ×3, preferred ×2, "
               "other ×1. You make the final choice on the **Resume Builder** page.")
    try:
        roles = get_store().load_roles().role_profiles
    except ProfileStoreError:
        roles = []
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Base role profile**")
        recs = recommend_role_profiles(report, analysis, profile, roles)
        if not roles:
            st.info("No role profiles yet. Create one in **Resume Library**.")
        elif not recs:
            st.info("None of your role profiles include evidence for the matched requirements.")
        else:
            st.dataframe(pd.DataFrame([{"Role profile": r.name, "Covers": _pct(r.score),
                                        "Requirements": ", ".join(r.covered)} for r in recs]), hide_index=True)
    with c2:
        st.markdown("**Most relevant projects**")
        projects = recommend_projects(report, analysis, profile)
        if not projects:
            st.info("No projects support the matched requirements.")
        else:
            st.dataframe(pd.DataFrame([{"Project": r.name, "Covers": _pct(r.score),
                                        "Requirements": ", ".join(r.covered)} for r in projects[:5]]),
                         hide_index=True)
