"""Per-request access to settings and stores, rooted at the configured data directory (as Streamlit does)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from src.api.errors import ApiError, not_found
from src.config import Settings, get_settings
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.persistence.settings_store import SettingsStore
from src.schemas.job import Job
from src.schemas.profile import MasterProfile


def settings() -> Settings:
    return get_settings()


def profile_store() -> ProfileStore:
    return ProfileStore(get_settings().data_dir)


_migrate_lock = threading.Lock()
_migrated: set[Path] = set()


def job_store() -> JobStore:
    """A JobStore whose database schema is known to be current.

    ``JobStore`` migrates the schema on first open, but two connections opening a new (or older)
    database at the same moment can both apply the same migration and fail. Streamlit rarely
    does that; a concurrent API does. So the first open per database runs once, under a lock,
    before any other request in this process touches it.
    """
    store = JobStore(get_settings().data_dir)
    if store.path not in _migrated:
        with _migrate_lock:
            if store.path not in _migrated:
                store.analysis_ids()  # opens a connection, which applies any pending migrations
                _migrated.add(store.path)
    return store


def settings_store() -> SettingsStore:
    return SettingsStore(get_settings().data_dir)


def require_profile(store: ProfileStore) -> MasterProfile:
    profile = store.load()
    if profile is None:
        raise ApiError(409, "profile_missing", "Create or import a master profile first.")
    return profile


def require_job(store: JobStore, job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise not_found("This job")
    return job


def check_version(current: Optional[MasterProfile], expected: Optional[int]) -> None:
    """Refuse to save over a profile version the client hasn't seen (e.g. one saved in Streamlit meanwhile)."""
    actual = current.profile_version if current else None
    if actual != expected:
        raise ApiError(409, "version_conflict",
                       "The profile changed since you opened it (perhaps in another window). Reload it and "
                       "re-apply your edits.", {"expected_version": expected, "current_version": actual})
