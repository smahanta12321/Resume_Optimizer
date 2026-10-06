"""Streamlit smoke tests for the Match Report page. Fictional data only."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.schemas.job import Job
from src.schemas.match import MatchStatus
from src.schemas.profile import utc_now
from src.services.jd_parser import parse_jd
from src.services.profile_service import load_sample_profile

JD = "Requirements\n• Strong Python and SQL\n• Experience with Kubernetes\n• Rust expertise\n"


@pytest.fixture(autouse=True)
def _temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def stores(_temp_data_dir):
    return ProfileStore(_temp_data_dir), JobStore(_temp_data_dir)


def _setup(stores, *, confirm_analysis=True):
    profiles, jobs = stores
    profiles.save_new_version(load_sample_profile())
    job = jobs.add(Job(description=JD, title="Fictional Engineer"))
    analysis = parse_jd(job).analysis
    if confirm_analysis:
        analysis = analysis.model_copy(update={"confirmed_at": utc_now()})
    jobs.save_analysis(analysis)
    return job, analysis


def _page():
    from src.ui.pages import match_report

    match_report.render()


def _run() -> AppTest:
    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_needs_profile():
    at = _run()
    assert any("master profile first" in w.value for w in at.warning)


def test_needs_analyzed_job(stores):
    stores[0].save_new_version(load_sample_profile())
    at = _run()
    assert any("No analyzed jobs" in i.value for i in at.info)


def test_unconfirmed_analysis_blocks_matching(stores):
    _setup(stores, confirm_analysis=False)
    at = _run()
    assert any("Confirm this job's analysis" in w.value for w in at.warning)
    assert not any(b.label == "Run matching" for b in at.button)


def test_run_matching_and_show_report(stores):
    job, analysis = _setup(stores)
    at = _click(_run(), "Run matching")
    report = stores[1].get_match_report(job.id)
    statuses = {r.normalized_term: report.by_requirement()[r.id].status for r in analysis.requirements}
    assert statuses["Python"] is MatchStatus.SUPPORTED
    assert statuses["Rust"] is MatchStatus.NOT_DOCUMENTED
    assert any("Rust" in m.value for m in at.markdown)  # listed under Gaps
    assert at.metric[0].label == "Required coverage"
    assert any("not been confirmed" in w.value for w in at.warning)  # sample profile was never confirmed


def test_override_requires_evidence_then_saves_and_clears(stores):
    job, analysis = _setup(stores)
    at = _click(_run(), "Run matching")
    rust = next(r for r in analysis.requirements if r.normalized_term == "Rust")
    at.selectbox(key="override-req").set_value(rust.id).run()

    at.radio[0].set_value(MatchStatus.SUPPORTED)
    _click(at, "Save my judgement")
    assert any("at least one evidence" in e.value for e in at.error)
    assert stores[1].get_match_report(job.id).by_requirement()[rust.id].override is None

    at.radio[0].set_value(MatchStatus.PARTIAL)
    evidence = next(m for m in at.multiselect if m.label == "Evidence")
    evidence.set_value(["bul-sample01"])
    next(t for t in at.text_input if t.label == "Note (why)").set_value("Fictional note")
    _click(at, "Save my judgement")
    override = stores[1].get_match_report(job.id).by_requirement()[rust.id].override
    assert override.status is MatchStatus.PARTIAL and override.evidence_ids == ["bul-sample01"]

    _click(at, "Clear my judgement")
    assert stores[1].get_match_report(job.id).by_requirement()[rust.id].override is None


def test_profile_change_marks_report_stale(stores):
    job, _ = _setup(stores)
    _click(_run(), "Run matching")
    profile = stores[0].load()
    stores[0].save_new_version(profile.model_copy(update={"summary": "Edited fictional summary."}))
    at = _run()
    assert any("out of date" in w.value for w in at.warning)
    _click(at, "Re-run matching")
    assert stores[1].get_match_report(job.id).profile_version == 2
