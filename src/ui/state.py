"""Shared UI helpers: store access and common status messages."""

from __future__ import annotations

import streamlit as st

from src.config import get_settings
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore


def get_store() -> ProfileStore:
    """One ProfileStore per session, rooted at the configured data directory."""
    if "profile_store" not in st.session_state:
        st.session_state.profile_store = ProfileStore(get_settings().data_dir)
    return st.session_state.profile_store


def get_job_store() -> JobStore:
    """One JobStore per session, rooted at the configured data directory."""
    if "job_store" not in st.session_state:
        st.session_state.job_store = JobStore(get_settings().data_dir)
    return st.session_state.job_store


def flash(kind: str, message: str) -> None:
    """Queue a message to show after the next rerun (st.rerun discards current output)."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flashes() -> None:
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def sample_banner(is_sample: bool) -> None:
    if is_sample:
        st.info(
            "You are viewing the **fictional sample profile**. Replace it with your own data "
            "(Import/Export tab or edit each section) before generating real resumes.",
            icon="🧪",
        )
