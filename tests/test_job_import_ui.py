"""Streamlit smoke tests for the Job Import page. Fictional data only; no network."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.persistence.job_store import JobStore
from src.schemas.job import ImportMethod, JobStatus, SourcePlatform
from src.services.url_import import FailureReason, UrlImportError, UrlImportResult

JD = (
    "Fictional Corp is hiring a Machine Learning Engineer to build retrieval systems. "
    "You will design data pipelines in Python, deploy models with Docker and Kubernetes, "
    "and work with product teams. Requirements: 3+ years of Python, PyTorch, SQL."
)


@pytest.fixture(autouse=True)
def _temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RESUME_OPTIMIZER_URL_IMPORT", "on")
    return tmp_path


def _page():
    from src.ui.pages import job_import

    job_import.render()


def _run() -> AppTest:
    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _paste_and_review(at: AppTest, text: str = JD) -> AppTest:
    at.text_area[0].set_value(text)
    return _click(at, "Review pasted text")


def _fill(at: AppTest, label: str, value: str) -> None:
    next(t for t in at.text_input if t.label == label).set_value(value)


def test_empty_page_renders():
    at = _run()
    assert any("No saved jobs" in i.value for i in at.info)


def test_empty_paste_shows_error():
    at = _paste_and_review(_run(), "   ")
    assert any("empty" in e.value for e in at.error)


def test_paste_review_save(_temp_data_dir):
    at = _paste_and_review(_run())
    _fill(at, "Job title", "ML Engineer")
    _fill(at, "Company", "Fictional Corp")
    _click(at, "Save job")
    [job] = JobStore(_temp_data_dir).list()
    assert (job.title, job.company, job.import_method) == ("ML Engineer", "Fictional Corp", ImportMethod.PASTE)
    assert job.description == JD
    assert any("Saved" in s.value for s in at.success)


def test_short_paste_is_flagged_but_allowed(_temp_data_dir):
    at = _paste_and_review(_run(), "Fictional data role, Python.")
    assert any("short" in w.value for w in at.warning)
    _click(at, "Save job")
    assert len(JobStore(_temp_data_dir).list()) == 1


def test_discard_draft(_temp_data_dir):
    at = _click(_paste_and_review(_run()), "Discard draft")
    assert any(b.label == "Review pasted text" for b in at.button)
    assert JobStore(_temp_data_dir).list() == []


def test_duplicate_update_existing_keeps_status(_temp_data_dir):
    store = JobStore(_temp_data_dir)
    at = _paste_and_review(_run())
    _fill(at, "Job title", "ML Engineer")
    _click(at, "Save job")
    [first] = store.list()
    store.update(first.model_copy(update={"status": JobStatus.APPLIED}))

    at = _paste_and_review(_run(), JD.upper())  # same text modulo case -> duplicate
    _click(at, "Save job")
    assert any("already saved" in w.value for w in at.warning)
    next(b for b in at.button if b.label.startswith("Update")).click().run()
    [job] = store.list()
    assert job.id == first.id and job.status is JobStatus.APPLIED
    assert job.description == JD.upper()


def test_duplicate_save_separately(_temp_data_dir):
    at = _paste_and_review(_run())
    _click(at, "Save job")
    at = _paste_and_review(_run())
    _click(at, "Save job")
    _click(at, "Save as a separate job")
    assert len(JobStore(_temp_data_dir).list()) == 2


def test_url_import_success_prefills_review(_temp_data_dir, monkeypatch):
    from src.ui.pages import job_import

    def fake_fetch(url, timeout):
        return UrlImportResult(text=JD, final_url="https://www.naukri.com/job-listings-x-120924500123",
                               platform=SourcePlatform.NAUKRI, method="structured", title="ML Engineer",
                               company="Fictional Corp", location="Remote", notes=["Structured data note."])

    monkeypatch.setattr(job_import, "fetch_job_from_url", fake_fetch)
    at = _run()
    _fill(at, "Job page URL", "https://www.naukri.com/job-listings-x-120924500123")
    at.run()
    _click(at, "Fetch page")
    assert any("Structured data note" in w.value for w in at.warning)
    _click(at, "Save job")
    [job] = JobStore(_temp_data_dir).list()
    assert (job.title, job.source_platform, job.import_method) == ("ML Engineer", SourcePlatform.NAUKRI, ImportMethod.URL)
    assert job.canonical_url == "https://naukri.com/job-listings-120924500123"
    assert job.import_notes == ["Structured data note."]


def test_url_import_failure_offers_fallback(monkeypatch):
    from src.ui.pages import job_import

    def blocked(url, timeout):
        raise UrlImportError(FailureReason.BLOCKED, "The site requires sign-in.")

    monkeypatch.setattr(job_import, "fetch_job_from_url", blocked)
    at = _run()
    _fill(at, "Job page URL", "https://www.linkedin.com/jobs/view/3987654321")
    at.run()
    _click(at, "Fetch page")
    assert any("sign-in" in e.value and "paste" in e.value.lower() for e in at.error)


def test_url_import_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_URL_IMPORT", "off")
    at = _run()
    assert any("turned off" in i.value for i in at.info)


def test_edit_and_delete_saved_job(_temp_data_dir):
    store = JobStore(_temp_data_dir)
    at = _paste_and_review(_run())
    _click(at, "Save job")
    [job] = store.list()

    at = _run()
    next(t for t in at.text_area if t.label == "Notes").set_value("Referred by a fictional friend")
    _click(at, "Save changes")
    assert store.get(job.id).notes == "Referred by a fictional friend"

    at.checkbox(key=f"del-chk-{job.id}").check().run()
    at.button(key=f"del-{job.id}").click().run()
    assert not at.exception
    assert store.list() == []
