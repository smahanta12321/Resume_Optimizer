"""Streamlit smoke tests for the Application Tracker and Settings pages. Fictional data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from src.config import get_settings
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.schemas.job import Job, JobStatus
from src.services.profile_service import load_sample_profile

ENV_VARS = ["RESUME_OPTIMIZER_URL_IMPORT", "RESUME_OPTIMIZER_LLM_PROVIDER", "RESUME_OPTIMIZER_LLM_MODEL",
            "RESUME_OPTIMIZER_PAGE_SIZE", "RESUME_OPTIMIZER_TEMPLATE", "RESUME_OPTIMIZER_LOCAL_ONLY"]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RESUME_OPTIMIZER_OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


def _run(module: str) -> AppTest:
    at = AppTest.from_string(
        f"import importlib\nimportlib.import_module('src.ui.pages.{module}').render()\n", default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


# ---- tracker ---------------------------------------------------------------------------


def test_tracker_empty():
    assert any("No jobs yet" in i.value for i in _run("tracker").info)


def _fill_tracker(at, status, follow_up, notes):
    next(s for s in at.selectbox if s.label == "Status").set_value(status)
    next(d for d in at.date_input if d.label == "Follow up on").set_value(follow_up)
    next(t for t in at.text_area if t.label == "Notes").set_value(notes)
    return _click(at, "Save")


def test_tracker_update_sets_applied_date(_env):
    store = JobStore(_env)
    job = store.add(Job(description="Fictional JD", title="Fictional Analyst", company="Fictional Co"))
    at = _run("tracker")
    assert at.metric[0].label == "Saved" and at.metric[0].value == "1"
    follow = date.today() + timedelta(days=7)
    at = _fill_tracker(at, JobStatus.APPLIED, follow, "Fictional recruiter call")
    saved = store.get(job.id)
    assert (saved.status, saved.applied_on, saved.follow_up_on) == (JobStatus.APPLIED, date.today(), follow)
    assert saved.notes == "Fictional recruiter call"
    assert any("Applied date set to today" in i.value for i in at.info)


def test_tracker_rejects_follow_up_before_applied(_env):
    store = JobStore(_env)
    job = store.add(Job(description="Fictional JD", title="Fictional Analyst"))
    at = _fill_tracker(_run("tracker"), JobStatus.APPLIED, date(2020, 1, 1), "x")
    assert any("before the applied" in e.value for e in at.error)
    assert store.get(job.id).status is JobStatus.SAVED  # nothing saved


def test_tracker_merge_duplicates(_env):
    store = JobStore(_env)
    a = store.add(Job(description="Same fictional JD text " * 10, title="Engineer", notes="first"))
    b = store.add(Job(description="Same fictional JD text " * 10, title="", notes="second"))
    at = _run("tracker")
    at.checkbox(key="dup-chk-0").check().run()
    at.button(key="dup-merge-0").click().run()
    assert not at.exception
    [left] = store.list()
    assert left.id == a.id and "second" in left.notes


# ---- settings ---------------------------------------------------------------------------


def test_settings_save_and_local_only(_env):
    at = _run("settings")
    assert any("AI rewriting is off" in i.value for i in at.info)
    next(r for r in at.radio if r.label == "Template").set_value("compact")
    next(r for r in at.radio if r.label == "Paper size").set_value("Letter")
    next(t for t in at.toggle if t.label.startswith("Local-only")).set_value(True)
    _click(at, "Save settings")
    s = get_settings()
    assert (s.template, s.page_size, s.local_only, s.url_import_enabled) == ("compact", "Letter", True, False)
    assert any("Local-only mode is on" in i.value for i in at.info)


def test_settings_env_locks_field(_env, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_PAGE_SIZE", "Letter")
    at = _run("settings")
    paper = next(r for r in at.radio if r.label == "Paper size")
    assert paper.disabled and paper.value == "Letter"


def test_settings_export_and_delete_everything(_env):
    ProfileStore(_env).save_new_version(load_sample_profile())
    JobStore(_env).add(Job(description="Fictional JD"))
    at = _click(_run("settings"), "Prepare data export")
    assert any(b.proto.label == "Download all my data (.zip)" for b in at.get("download_button"))
    at.text_input(key="delete-everything-confirm").set_value("DELETE EVERYTHING").run()
    _click(at, "Delete all my data")
    assert ProfileStore(_env).load() is None and JobStore(_env).list() == []
