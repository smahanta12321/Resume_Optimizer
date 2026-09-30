"""Streamlit smoke tests: pages render without exceptions against a temp data dir."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.persistence.profile_store import ProfileStore
from src.services.profile_service import load_sample_profile


@pytest.fixture(autouse=True)
def _temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    return tmp_path


def _profile_page():
    from src.ui.pages import master_profile

    master_profile.render()


def _library_page():
    from src.ui.pages import resume_library

    resume_library.render()


def _dashboard_page():
    from src.ui.pages import dashboard

    dashboard.render()


def _run(fn) -> AppTest:
    at = AppTest.from_function(fn, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_app_entrypoint_renders():
    at = AppTest.from_file("../app.py", default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_empty_state_pages_render():
    at = _run(_profile_page)
    assert any("No master profile" in i.value for i in at.info)
    _run(_library_page)
    _run(_dashboard_page)


def test_load_sample_then_confirm(_temp_data_dir):
    at = _run(_profile_page)
    next(b for b in at.button if b.label == "Load fictional sample profile").click().run()
    assert not at.exception
    store = ProfileStore(_temp_data_dir)
    assert store.load().profile_version == 1
    assert any("not confirmed" in w.value for w in at.warning)

    next(b for b in at.button if b.label == "Confirm profile").click().run()
    assert not at.exception
    assert store.load().confirmed_at is not None


def test_create_blank_profile_requires_name(_temp_data_dir):
    at = _run(_profile_page)
    at.text_input[0].set_value("")
    next(b for b in at.button if b.label == "Create profile").click().run()
    assert at.error, "empty name should show an error"
    assert ProfileStore(_temp_data_dir).load() is None


def test_populated_pages_render(_temp_data_dir):
    ProfileStore(_temp_data_dir).save_new_version(load_sample_profile())
    at = _run(_profile_page)
    assert any("fictional sample" in i.value for i in at.info)
    _run(_library_page)
    at = _run(_dashboard_page)
    assert at.metric[0].value == "1"


def test_edit_summary_creates_new_version(_temp_data_dir):
    store = ProfileStore(_temp_data_dir)
    store.save_new_version(load_sample_profile())
    at = _run(_profile_page)
    at.text_area[0].set_value("Edited summary for a fictional person.")
    next(b for b in at.button if b.label == "Save contact & summary").click().run()
    assert not at.exception
    assert store.load().profile_version == 2
    assert store.load().summary == "Edited summary for a fictional person."


def test_invalid_edit_shows_error_and_keeps_version(_temp_data_dir):
    store = ProfileStore(_temp_data_dir)
    store.save_new_version(load_sample_profile())
    at = _run(_profile_page)
    email = next(t for t in at.text_input if t.label == "Email")
    email.set_value("not-an-email")
    next(b for b in at.button if b.label == "Save contact & summary").click().run()
    assert any("email" in e.value.lower() for e in at.error)
    assert store.load().profile_version == 1


def test_create_role_profile_via_ui(_temp_data_dir):
    store = ProfileStore(_temp_data_dir)
    store.save_new_version(load_sample_profile())
    at = _run(_library_page)
    next(t for t in at.text_input if t.label == "Name *").set_value("ML Engineer")
    at.multiselect[0].set_value(["exp-sample01", "bul-sample01"])
    next(b for b in at.button if b.label == "Create").click().run()
    assert not at.exception
    roles = store.load_roles().role_profiles
    assert [r.name for r in roles] == ["ML Engineer"]
    assert roles[0].evidence_ids == ["exp-sample01", "bul-sample01"]


def test_edit_and_delete_experience_via_ui(_temp_data_dir):
    store = ProfileStore(_temp_data_dir)
    store.save_new_version(load_sample_profile())
    at = _run(_profile_page)
    title = next(t for t in at.text_input if t.label == "Job title *" and t.value == "Data Analyst")
    title.set_value("Senior Data Analyst")
    # Each experience form has its own Save button; the second experience is the Data Analyst entry.
    [b for b in at.button if b.label == "Save"][1].click().run()
    assert not at.exception
    p = store.load()
    assert p.profile_version == 2
    exp = next(e for e in p.experience if e.id == "exp-sample02")
    assert exp.title == "Senior Data Analyst"
    assert [b.id for b in exp.bullets] == ["bul-sample03"]  # bullet IDs preserved

    at.checkbox(key="del-chk-exp-sample02").check().run()
    at.button(key="del-exp-sample02").click().run()
    assert not at.exception
    # Deleting evidence prunes skill links to it and tells the user.
    p = store.load()
    assert p.profile_version == 3
    assert [e.id for e in p.experience] == ["exp-sample01"]
    assert "bul-sample03" not in next(s for s in p.skills if s.name == "SQL").evidence_ids
    assert any("SQL" in w.value for w in at.warning)
