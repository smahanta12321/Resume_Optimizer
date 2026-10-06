"""Browser-extension inbox (Job Import) and pairing (Settings) UI tests. Fictional data only."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from streamlit.testing.v1 import AppTest

from src.persistence.extension_token import read_token
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.persistence.settings_store import SettingsStore
from src.schemas.capture import Capture
from src.schemas.job import ImportMethod
from src.services.data_service import delete_everything, export_all_data

JD = ("Fictional Corp is hiring a Data Engineer to build pipelines in Python and SQL. "
      "Requirements: 3+ years of experience, Airflow, and cloud data warehouses. ") * 2


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    for v in ("RESUME_OPTIMIZER_EXTENSION", "RESUME_OPTIMIZER_EXTENSION_PORT", "RESUME_OPTIMIZER_LOCAL_ONLY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RESUME_OPTIMIZER_OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


def _run(module: str) -> AppTest:
    at = AppTest.from_string(f"import importlib\nimportlib.import_module('src.ui.pages.{module}').render()\n",
                             default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _capture(store: JobStore) -> Capture:
    return store.add_capture(Capture(text=JD, url="https://careers.example.com/jobs/7", title="Data Engineer",
                                     company="Fictional Corp", method="selection"))


def test_inbox_explains_setup_when_off():
    at = _run("job_import")
    assert any("browser extension" in i.value for i in at.info)


def test_capture_review_and_save_removes_it_from_inbox(_env):
    store = JobStore(_env)
    cap = _capture(store)
    at = _run("job_import")
    at.button(key=f"cap-review-{cap.id}").click().run()
    assert any("Captured by the browser extension" in w.value for w in at.warning)
    assert next(t for t in at.text_input if t.label == "Job title").value == "Data Engineer"
    assert store.list_captures(), "still in the inbox until saved"
    next(b for b in at.button if b.label == "Save job").click().run()
    assert not at.exception
    [job] = store.list()
    assert job.import_method is ImportMethod.EXTENSION and job.company == "Fictional Corp"
    assert job.source_url == "https://careers.example.com/jobs/7"
    assert store.list_captures() == []


def test_discarding_draft_keeps_capture_and_discard_removes_it(_env):
    store = JobStore(_env)
    cap = _capture(store)
    at = _run("job_import")
    at.button(key=f"cap-review-{cap.id}").click().run()
    next(b for b in at.button if b.label == "Discard draft").click().run()
    assert [c.id for c in store.list_captures()] == [cap.id]
    at.button(key=f"cap-discard-{cap.id}").click().run()
    assert store.list_captures() == [] and store.list() == []


def test_settings_pairing_section(_env):
    at = _run("settings")
    assert not any("Pair the browser extension" in s.value for s in at.subheader)
    next(t for t in at.toggle if t.label.startswith("Accept job descriptions")).set_value(True)
    next(b for b in at.button if b.label == "Save settings").click().run()
    assert any("Pair the browser extension" in s.value for s in at.subheader)
    assert any("isn't running" in w.value for w in at.warning)
    token = read_token(_env)
    assert token and not any(token in c.value for c in at.code)  # hidden until revealed
    next(c for c in at.checkbox if c.label == "Show pairing token").check().run()
    assert any(c.value == token for c in at.code)
    next(b for b in at.button if b.label.startswith("Generate a new token")).click().run()
    assert read_token(_env) != token


def test_data_export_includes_inbox_and_delete_removes_token(_env):
    from src.persistence.extension_token import get_or_create_token

    jobs, profiles, settings = JobStore(_env), ProfileStore(_env), SettingsStore(_env)
    _capture(jobs)
    get_or_create_token(_env)
    data = export_all_data(profiles, jobs, settings, _env / "output")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        [cap] = json.loads(z.read("captures.json"))
        assert cap["company"] == "Fictional Corp"
        assert not any("token" in n for n in z.namelist())  # pairing token never exported
    delete_everything(profiles, jobs, settings, _env / "output")
    assert jobs.list_captures() == [] and read_token(_env) is None
