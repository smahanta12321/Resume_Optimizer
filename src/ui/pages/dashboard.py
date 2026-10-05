"""Dashboard: profile status and next steps."""

from __future__ import annotations

import streamlit as st

from src.persistence.job_store import JobStoreError
from src.persistence.profile_store import ProfileStoreError
from src.services.profile_service import profile_warnings
from src.ui.state import get_job_store, get_store, sample_banner, show_flashes


def render() -> None:
    st.title("AI Resume Optimizer")
    st.caption(
        "Local-first assistant for tailoring truthful resumes. It never applies to jobs or "
        "contacts recruiters, and it does not guarantee ATS outcomes."
    )
    show_flashes()
    store = get_store()

    try:
        profile = store.load()
    except ProfileStoreError as exc:
        st.error(f"Your saved profile could not be loaded. {exc}")
        st.markdown("Open **Master Profile** to import a backup or restore an earlier version.")
        return

    if profile is None:
        st.warning("No master profile yet. Start by creating or importing one.")
        st.markdown("Open **Master Profile** in the sidebar to begin.")
        return

    sample_banner(profile.is_sample)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profile version", profile.profile_version)
    c2.metric("Experience entries", len(profile.experience))
    c3.metric("Projects", len(profile.projects))
    c4.metric("Skills", len(profile.skills))

    if profile.confirmed_at:
        st.success(f"Profile v{profile.profile_version} confirmed on {profile.confirmed_at:%Y-%m-%d %H:%M} UTC.")
    else:
        st.warning("This profile version has not been reviewed and confirmed yet (Master Profile → Confirm).")

    n_warn = len(profile_warnings(profile))
    if n_warn:
        st.info(f"{n_warn} profile quality note(s) to review on the Master Profile page.")

    roles = store.load_roles().role_profiles
    st.subheader("Role profiles")
    st.write(", ".join(r.name for r in roles) if roles else "None yet — create them in Resume Library.")

    st.subheader("Jobs")
    try:
        jobs = get_job_store().list()
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        jobs = []
    if jobs:
        try:
            analyzed = len(get_job_store().analysis_ids())
        except JobStoreError:
            analyzed = 0
        st.write(f"{len(jobs)} saved job(s), {analyzed} analyzed. Latest: **{jobs[0].display_name}** "
                 f"({jobs[0].imported_at:%Y-%m-%d}).")
    else:
        st.write("None yet. Import a job description on the Job Import page.")

    st.subheader("Coming next")
    st.markdown(
        "- Evidence-based match report\n"
        "- Tailored draft, approval, and DOCX/PDF export\n"
        "- Application tracker and settings"
    )
    st.caption(
        "Privacy: all data is stored locally in the configured data folder. No LLM provider is used yet. "
        "URL import contacts only the job site you enter."
    )
