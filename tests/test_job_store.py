"""Job schema and SQLite store tests. All job data is fictional."""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from src.persistence.job_store import _COLUMNS, _CREATE, JobStore, JobStoreError, _to_row
from src.schemas.analysis import Importance, JDAnalysis, Requirement, RequirementCategory
from src.schemas.job import MAX_JD_CHARS, ImportMethod, Job, JobStatus, SourcePlatform


@pytest.fixture
def job_store(tmp_path) -> JobStore:
    return JobStore(tmp_path)


def _job(**kw) -> Job:
    base = dict(title="ML Engineer", company="Fictional Corp", location="Remote",
                description="Build fictional ML systems with Python.")
    return Job(**(base | kw))


def test_job_requires_non_blank_description():
    with pytest.raises(ValidationError):
        Job(description="   ")
    with pytest.raises(ValidationError):
        Job(description="x" * (MAX_JD_CHARS + 1))


def test_job_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Job(description="ok", salary="lots")


def test_add_get_roundtrip(job_store):
    job = _job(import_notes=["note one"], source_platform=SourcePlatform.NAUKRI, import_method=ImportMethod.URL)
    job_store.add(job)
    got = job_store.get(job.id)
    assert got == job
    assert got.import_notes == ["note one"]


def test_get_missing_returns_none(job_store):
    assert job_store.get("job-nothere") is None


def test_list_newest_first_and_filter(job_store):
    a = job_store.add(_job(title="A"))
    b = job_store.add(_job(title="B", status=JobStatus.APPLIED))
    assert [j.id for j in job_store.list()] == [b.id, a.id]
    assert [j.id for j in job_store.list(JobStatus.APPLIED)] == [b.id]


def test_update_preserves_imported_at(job_store):
    job = job_store.add(_job())
    updated = job_store.update(job.model_copy(update={"title": "Senior ML Engineer", "notes": "n"}))
    got = job_store.get(job.id)
    assert got.title == "Senior ML Engineer"
    assert got.imported_at == job.imported_at
    assert updated.updated_at >= job.updated_at


def test_update_missing_raises(job_store):
    with pytest.raises(JobStoreError):
        job_store.update(_job())


def test_delete_and_delete_all(job_store):
    a = job_store.add(_job())
    job_store.add(_job())
    assert job_store.delete(a.id) is True
    assert job_store.delete(a.id) is False
    assert job_store.delete_all() == 1
    assert job_store.list() == []


def test_duplicate_id_rejected(job_store):
    job = job_store.add(_job())
    with pytest.raises(sqlite3.IntegrityError):
        job_store.add(job)


def test_newer_schema_refused(tmp_path):
    store = JobStore(tmp_path)
    store.list()
    with sqlite3.connect(store.path) as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(JobStoreError, match="newer"):
        store.list()


def test_corrupt_db_raises_store_error(tmp_path):
    (tmp_path / "jobs.sqlite3").write_bytes(b"not a database at all" * 100)
    with pytest.raises(JobStoreError):
        JobStore(tmp_path).list()


# ---- JD analyses ----------------------------------------------------------------


def _analysis(job_id: str) -> JDAnalysis:
    return JDAnalysis(job_id=job_id, jd_hash="h", requirements=[
        Requirement(text="Python", normalized_term="Python", category=RequirementCategory.SKILL,
                    importance=Importance.REQUIRED)])


def test_analysis_roundtrip_and_replace(job_store):
    job = job_store.add(_job())
    assert job_store.get_analysis(job.id) is None
    saved = job_store.save_analysis(_analysis(job.id))
    assert job_store.get_analysis(job.id) == saved
    job_store.save_analysis(saved.model_copy(update={"requirements": []}))
    assert job_store.get_analysis(job.id).requirements == []
    assert job_store.analysis_ids() == {job.id}


def test_analysis_requires_existing_job(job_store):
    with pytest.raises(JobStoreError):
        job_store.save_analysis(_analysis("job-missing"))


def test_deleting_job_deletes_analysis(job_store):
    a, b = job_store.add(_job()), job_store.add(_job())
    job_store.save_analysis(_analysis(a.id))
    job_store.save_analysis(_analysis(b.id))
    job_store.delete(a.id)
    assert job_store.analysis_ids() == {b.id}
    job_store.delete_all()
    assert job_store.analysis_ids() == set()


def test_migrates_v1_database_keeping_jobs(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(_CREATE)
        conn.execute("PRAGMA user_version = 1")
    conn.close()
    job = _job()
    # Insert a job through raw SQL as a v1 app would have, then let the store migrate.
    v1_cols = _COLUMNS[:15]
    with sqlite3.connect(path) as conn:
        conn.execute(f"INSERT INTO jobs ({', '.join(v1_cols)}) VALUES ({', '.join('?' for _ in v1_cols)})",
                     _to_row(job)[:15])
    conn.close()
    store = JobStore(tmp_path)
    assert store.get(job.id) == job
    store.save_analysis(_analysis(job.id))
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()


def test_analysis_validation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JDAnalysis(job_id="j", jd_hash="h", experience_min_years=5, experience_max_years=3)
    with pytest.raises(ValidationError):
        Requirement(text="x", min_years=4, max_years=2)
    r = Requirement(text="x")
    with pytest.raises(ValidationError):
        JDAnalysis(job_id="j", jd_hash="h", requirements=[r, r])


def test_match_report_roundtrip_and_cascade(job_store):
    from src.schemas.match import MatchReport, MatchStatus, RequirementMatch

    job = job_store.add(_job())
    report = MatchReport(job_id=job.id, profile_version=1, analysis_fingerprint="f",
                         matches=[RequirementMatch(requirement_id="req-1", status=MatchStatus.PARTIAL)])
    saved = job_store.save_match_report(report)
    assert job_store.get_match_report(job.id) == saved
    assert job_store.match_report_ids() == {job.id}
    job_store.delete(job.id)
    assert job_store.match_report_ids() == set()
    with pytest.raises(JobStoreError):
        job_store.save_match_report(report)


def _resume_version(job_id: str):
    from src.schemas.profile import Contact
    from src.schemas.resume import ResumeContent, ResumeVersion

    return ResumeVersion(job_id=job_id, profile_version=1, match_profile_version=1, generator="deterministic",
                         content=ResumeContent(contact=Contact(full_name="Fictional Person")))


def test_resume_versions_immutable_and_approval(job_store):
    job = job_store.add(_job())
    v1 = job_store.add_resume_version(_resume_version(job.id))
    v2 = job_store.add_resume_version(_resume_version(job.id).model_copy(update={"parent_id": v1.id}))
    assert [v.id for v in job_store.list_resume_versions(job.id)] == [v2.id, v1.id]
    with pytest.raises(sqlite3.IntegrityError):
        job_store.add_resume_version(v1)  # never overwritten
    approved = job_store.approve_resume_version(v1.id, "looks right")
    assert approved.approved_at is not None and approved.approval_note == "looks right"
    assert approved.content == v1.content
    with pytest.raises(JobStoreError):
        job_store.approve_resume_version(v1.id)  # already approved
    assert job_store.resume_counts() == {job.id: (2, 1)}
    job_store.delete(job.id)
    assert job_store.get_resume_version(v1.id) is None


def test_added_version_cannot_arrive_pre_approved(job_store):
    from src.schemas.profile import utc_now

    job = job_store.add(_job())
    v = job_store.add_resume_version(_resume_version(job.id).model_copy(update={"approved_at": utc_now()}))
    assert job_store.get_resume_version(v.id).approved_at is None


def test_tracker_fields_roundtrip(job_store):
    from datetime import date

    job = job_store.add(_job(applied_on=date(2026, 10, 1), follow_up_on=date(2026, 10, 8),
                             resume_version_id="res-12345678"))
    got = job_store.get(job.id)
    assert (got.applied_on, got.follow_up_on, got.resume_version_id) == (date(2026, 10, 1), date(2026, 10, 8),
                                                                         "res-12345678")
