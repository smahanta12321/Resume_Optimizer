"""Versioned file storage for the master profile."""

from __future__ import annotations

import pytest

from src.persistence.profile_store import ProfileStore, ProfileStoreError


def test_load_returns_none_when_empty(store):
    assert store.load() is None
    assert store.list_versions() == []


def test_first_save_is_version_1(store, sample_profile):
    saved = store.save_new_version(sample_profile)
    assert saved.profile_version == 1
    assert saved.confirmed_at is None
    assert store.list_versions() == [1]
    assert store.load() == saved


def test_unchanged_save_does_not_create_version(saved_store):
    current = saved_store.load()
    again = saved_store.save_new_version(current)
    assert again.profile_version == 1
    assert saved_store.list_versions() == [1]


def test_edit_creates_new_version_and_keeps_old_snapshot(saved_store):
    current = saved_store.load()
    edited = current.model_copy(update={"summary": "Changed summary (fictional)."})
    v2 = saved_store.save_new_version(edited)
    assert v2.profile_version == 2
    assert saved_store.list_versions() == [1, 2]
    assert saved_store.load_version(1).summary == current.summary
    assert saved_store.load_version(2).summary == "Changed summary (fictional)."


def test_snapshots_are_never_overwritten(saved_store):
    # Simulate a stale current file pointing at v1 while v2 exists: the next save must be v3.
    current = saved_store.load()
    saved_store.save_new_version(current.model_copy(update={"summary": "v2"}))
    (saved_store.current_path).write_text(saved_store.load_version(1).model_dump_json(), encoding="utf-8")
    v3 = saved_store.save_new_version(current.model_copy(update={"summary": "v3"}))
    assert v3.profile_version == 3
    assert saved_store.load_version(2).summary == "v2"


def test_confirmation_is_cleared_by_edit(saved_store):
    confirmed = saved_store.mark_confirmed()
    assert confirmed.confirmed_at is not None
    assert saved_store.load().confirmed_at is not None
    edited = saved_store.save_new_version(confirmed.model_copy(update={"headline": "New (fictional)"}))
    assert edited.confirmed_at is None


def test_confirm_without_profile_fails(store):
    with pytest.raises(ProfileStoreError):
        store.mark_confirmed()


def test_corrupt_current_file_raises_clear_error(saved_store):
    saved_store.current_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProfileStoreError, match="could not be read"):
        saved_store.load()


def test_can_recover_from_corrupt_current_file(saved_store, sample_profile):
    saved_store.current_path.write_text("{not json", encoding="utf-8")
    recovered = saved_store.save_new_version(sample_profile)
    assert recovered.profile_version == 2
    assert saved_store.load() == recovered
    assert saved_store.load_version(1) is not None


def test_missing_version_raises(saved_store):
    with pytest.raises(ProfileStoreError, match="does not exist"):
        saved_store.load_version(99)


def test_delete_all_removes_everything(saved_store):
    saved_store.save_roles(saved_store.load_roles())
    saved_store.delete_all()
    assert saved_store.load() is None
    assert saved_store.list_versions() == []
    assert not saved_store.roles_path.exists()


def test_store_uses_given_directory(tmp_path, sample_profile):
    store = ProfileStore(tmp_path / "nested")
    store.save_new_version(sample_profile)
    assert (tmp_path / "nested" / "profile" / "master_profile.json").exists()
