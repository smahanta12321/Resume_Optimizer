"""AI Resume Optimizer — Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src.config import configure_logging, get_settings
from src.ui.pages import (
    dashboard,
    jd_analysis,
    job_import,
    master_profile,
    match_report,
    resume_builder,
    resume_library,
    settings,
    tracker,
)

configure_logging(get_settings().log_level)

st.set_page_config(page_title="AI Resume Optimizer", page_icon="📄", layout="wide")

pages = [
    st.Page(dashboard.render, title="Dashboard", icon="🏠", url_path="dashboard", default=True),
    st.Page(master_profile.render, title="Master Profile", icon="👤", url_path="profile"),
    st.Page(resume_library.render, title="Resume Library", icon="📚", url_path="library"),
    st.Page(job_import.render, title="Job Import", icon="📥", url_path="jobs"),
    st.Page(jd_analysis.render, title="JD Analysis", icon="🔎", url_path="analysis"),
    st.Page(match_report.render, title="Match Report", icon="🧩", url_path="match"),
    st.Page(resume_builder.render, title="Resume Builder", icon="📝", url_path="builder"),
    st.Page(tracker.render, title="Application Tracker", icon="📋", url_path="tracker"),
    st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
]

st.navigation(pages).run()
