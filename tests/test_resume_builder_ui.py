"""Streamlit smoke tests for the Resume Builder page. Fictional data only; no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.schemas.job import Job
from src.schemas.profile import utc_now
from src.services.jd_parser import parse_jd
from src.services.llm.provider import LLMError, ProviderStatus
from src.services.matching_service import build_match_report
from src.services.profile_service import load_sample_profile

JD = "Requirements\n• Strong Python and SQL\n• Experience with Docker\n"


@pytest.fixture(autouse=True)
def _temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RESUME_OPTIMIZER_LLM_PROVIDER", "none")
    monkeypatch.setenv("RESUME_OPTIMIZER_OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


@pytest.fixture
def stores(_temp_data_dir):
    return ProfileStore(_temp_data_dir), JobStore(_temp_data_dir)


def _setup(stores):
    profiles, jobs = stores
    profile = profiles.save_new_version(load_sample_profile())
    job = jobs.add(Job(description=JD, title="Fictional Data Engineer"))
    analysis = parse_jd(job).analysis.model_copy(update={"confirmed_at": utc_now()})
    jobs.save_analysis(analysis)
    report, _ = build_match_report(analysis, profile)
    jobs.save_match_report(report)
    return job


def _page():
    from src.ui.pages import resume_builder

    resume_builder.render()


def _run() -> AppTest:
    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_needs_matched_job(stores):
    at = _run()
    assert any("master profile first" in w.value for w in at.warning)
    stores[0].save_new_version(load_sample_profile())
    at = _run()
    assert any("No matched jobs" in i.value for i in at.info)


def test_generate_deterministic_and_approve(stores):
    job = _setup(stores)
    at = _run()
    assert any("AI rewriting is off" in c.value for c in at.caption)
    _click(at, "Generate draft")
    [version] = stores[1].list_resume_versions(job.id)
    assert version.generator == "deterministic"
    assert any("Asha Example" in m.value for m in at.markdown)  # preview rendered

    approve = next(b for b in at.button if b.label == "Approve this version")
    assert approve.disabled  # needs the accuracy confirmation
    at.checkbox(key=f"approve-chk-{version.id}").check().run()
    _click(at, "Approve this version")
    assert stores[1].get_resume_version(version.id).approved_at is not None


def test_summary_edit_creates_new_version_and_blocks_approval(stores):
    job = _setup(stores)
    at = _click(_run(), "Generate draft")
    [v1] = stores[1].list_resume_versions(job.id)
    next(t for t in at.text_area if t.label == "Summary").set_value(
        "Fictional engineer with 15 years of Kubernetes experience.")
    _click(at, "Save as new version")
    v2, older = stores[1].list_resume_versions(job.id)
    assert older.id == v1.id and v2.parent_id == v1.id and v2.generator == "user_edit"
    assert any("15 years" in e.value for e in at.error)
    assert not any(b.label == "Approve this version" for b in at.button)


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def generate_json(self, *, system, user, schema, max_tokens):
        self.calls += 1
        if self.fail:
            raise LLMError("Fake outage.")
        return json.dumps({"summary": {"text": "Fictional engineer using Python and SQL.",
                                       "evidence_ids": ["bul-sample03"]}, "bullets": []})


def _enable_fake_ai(monkeypatch, provider):
    from src.ui.pages import resume_builder

    monkeypatch.setattr(resume_builder, "provider_status",
                        lambda s: ProviderStatus(True, "AI rewriting available via fake (fake-1).", "fake", "fake-1"))
    monkeypatch.setattr(resume_builder, "get_provider", lambda s: provider)


def test_ai_requires_consent_and_hides_contact(stores, monkeypatch):
    job = _setup(stores)
    provider = FakeProvider()
    _enable_fake_ai(monkeypatch, provider)
    at = _run()
    at.checkbox(key=f"gen-ai-{job.id}").check().run()
    assert next(b for b in at.button if b.label == "Generate draft").disabled
    sent = " ".join(c.value for c in at.code)
    assert "<job_requirements>" in sent and "asha" not in sent.lower()  # sample contact is never sent
    at.checkbox(key=f"gen-consent-{job.id}").check().run()
    _click(at, "Generate draft")
    [version] = stores[1].list_resume_versions(job.id)
    assert provider.calls == 1 and version.generator == "llm:fake/fake-1"
    assert version.content.summary.text == "Fictional engineer using Python and SQL."


def test_ai_failure_falls_back_to_deterministic(stores, monkeypatch):
    job = _setup(stores)
    _enable_fake_ai(monkeypatch, FakeProvider(fail=True))
    at = _run()
    at.checkbox(key=f"gen-ai-{job.id}").check().run()
    at.checkbox(key=f"gen-consent-{job.id}").check().run()
    _click(at, "Generate draft")
    [version] = stores[1].list_resume_versions(job.id)
    assert version.generator == "deterministic"
    assert any("Fake outage" in w.value for w in at.warning)


def test_stale_match_report_blocks_generation(stores):
    _setup(stores)
    profile = stores[0].load()
    stores[0].save_new_version(profile.model_copy(update={"summary": "Changed fictional summary."}))
    at = _run()
    assert any("out of date" in w.value for w in at.warning)
    assert next(b for b in at.button if b.label == "Generate draft").disabled


def test_export_after_approval_and_cleanup_on_job_delete(stores, _temp_data_dir):
    job = _setup(stores)
    at = _click(_run(), "Generate draft")
    [version] = stores[1].list_resume_versions(job.id)
    assert any("Approve this version on" in i.value for i in at.info)  # Export tab before approval
    assert not any(b.label == "Export DOCX and PDF" for b in at.button)

    at.checkbox(key=f"approve-chk-{version.id}").check().run()
    _click(at, "Approve this version")
    _click(at, "Export DOCX and PDF")
    record = stores[1].get_export(version.id)
    assert record is not None and record.failed == []
    assert Path(record.docx_path).is_file() and Path(record.pdf_path).is_file()
    assert str(_temp_data_dir / "output" / job.id) in record.pdf_path
    assert any("All export checks passed" in s.value for s in at.success)
    assert any(b.label == "Export again" for b in at.button)

    # Deleting the job on Job Import removes its exported files too.
    def job_page():
        from src.ui.pages import job_import

        job_import.render()

    jp = AppTest.from_function(job_page, default_timeout=30)
    jp.run()
    jp.checkbox(key=f"del-chk-{job.id}").check().run()
    jp.button(key=f"del-{job.id}").click().run()
    assert not jp.exception
    assert not (_temp_data_dir / "output" / job.id).exists()
    assert stores[1].get_resume_version(version.id) is None
