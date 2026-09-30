"""Shared fixtures. All profile data used in tests is fictional."""

from __future__ import annotations

import pytest

from src.persistence.profile_store import ProfileStore
from src.schemas.profile import MasterProfile
from src.services.profile_service import load_sample_profile


@pytest.fixture
def sample_profile() -> MasterProfile:
    return load_sample_profile()


@pytest.fixture
def store(tmp_path) -> ProfileStore:
    return ProfileStore(tmp_path)


@pytest.fixture
def saved_store(store, sample_profile) -> ProfileStore:
    store.save_new_version(sample_profile)
    return store
