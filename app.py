"""AI Resume Optimizer — Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src.config import configure_logging, get_settings
from src.ui.pages import dashboard, master_profile, resume_library

configure_logging(get_settings().log_level)

st.set_page_config(page_title="AI Resume Optimizer", page_icon="📄", layout="wide")

pages = [
    st.Page(dashboard.render, title="Dashboard", icon="🏠", url_path="dashboard", default=True),
    st.Page(master_profile.render, title="Master Profile", icon="👤", url_path="profile"),
    st.Page(resume_library.render, title="Resume Library", icon="📚", url_path="library"),
]

st.navigation(pages).run()
