"""Application tracker and data export/deletion tests. Fictional data only."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date

import pytest

from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.persistence.settings_store import SettingsStore
from src.schemas.job import Job, JobStatus, SourcePlatform
from src.schemas.profile import TargetLength, utc_now
from src.services.data_service import delete_everything, export_all_data
from src.services.export_service import export_version
from src.services.jd_parser import parse_jd
from src.services.matching_service import build_match_report
from src.services.resume_generator import build_draft, new_version
from src.services.tracker_service import (
    TrackerError,
    build_rows,
    delete_job,
    duplicate_pairs,
    filter_rows,
    follow_ups_due,
    merge_jobs,
    merge_loss,
    to_csv,
    update_application,
)

TODAY = date(2026, 10, 5)
JD = "Requirements\n• Strong Python and SQL\n• Experience with Docker\n"


@pytest.fixture
def stores(tmp_path):
    return ProfileStore(tmp_path), JobStore(tmp_path), SettingsStore(tmp_path)


def _full_job(stores, sample_profile, tmp_path, **kw):
    """A job with analysis, match report, an approved + exported resume version."""
    profiles, jobs, _ = stores
    profile = profiles.load() or profiles.save_new_version(sample_profile)
    job = jobs.add(Job(description=JD, title="Fictional Data Engineer", company="Fictional Corp", **kw))
    analysis = parse_jd(job).analysis.model_copy(update={"confirmed_at": utc_now()})
    jobs.save_analysis(analysis)
    report, _ = build_match_report(analysis, profile)
    jobs.save_match_report(report)
    content, omitted = build_draft(profile, analysis, report)
    v = jobs.add_resume_version(new_version(job.id, profile, report, content, omitted, generator="deterministic",
                                            role=None, target_pages=TargetLength.ONE_PAGE))
    v = jobs.approve_resume_version(v.id)
    jobs.save_export(export_version(v, output_dir=tmp_path / "output"))
    return job, v


# ---- rows / filters ------------------------------------------------------------------


def test_rows_show_pipeline_state(stores, sample_profile, tmp_path):
    job, v = _full_job(stores, sample_profile, tmp_path)
    _, jobs, _ = stores
    jobs.add(Job(description="Another fictional JD", title="Analyst", source_platform=SourcePlatform.NAUKRI))
    update_application(jobs, jobs.get(job.id), status=JobStatus.APPLIED, applied_on=date(2026, 10, 1),
                       follow_up_on=date(2026, 10, 4), notes="", resume_version_id=v.id, today=TODAY)
    rows = {r.job.id: r for r in build_rows(jobs, TODAY)}
    full = rows[job.id]
    assert full.analysis_state == "confirmed" and full.required_coverage is not None
    assert (full.versions, full.approved, full.exported) == (1, 1, True)
    assert full.resume_label == f"{v.id} (approved)" and full.follow_up_due
    other = next(r for r in rows.values() if r.job.id != job.id)
    assert other.analysis_state == "none" and other.required_coverage is None

    all_rows = list(rows.values())
    assert [r.job.id for r in filter_rows(all_rows, statuses=[JobStatus.APPLIED])] == [job.id]
    assert len(filter_rows(all_rows, platforms=[SourcePlatform.NAUKRI])) == 1
    assert [r.job.id for r in filter_rows(all_rows, search="fictional corp")] == [job.id]
    assert [r.job.id for r in filter_rows(all_rows, due_only=True)] == [job.id]


# ---- updates ---------------------------------------------------------------------------


def test_update_application_rules(stores):
    _, jobs, _ = stores
    job = jobs.add(Job(description="Fictional JD"))
    other = jobs.add(Job(description="Other fictional JD"))
    saved, info = update_application(jobs, job, status=JobStatus.APPLIED, applied_on=None, follow_up_on=None,
                                     notes="n", resume_version_id=None, today=TODAY)
    assert saved.applied_on == TODAY and "today" in info[0]
    with pytest.raises(TrackerError, match="future"):
        update_application(jobs, job, status=JobStatus.APPLIED, applied_on=date(2026, 12, 1), follow_up_on=None,
                           notes="", resume_version_id=None, today=TODAY)
    with pytest.raises(TrackerError, match="before the applied"):
        update_application(jobs, job, status=JobStatus.APPLIED, applied_on=date(2026, 10, 3),
                           follow_up_on=date(2026, 10, 1), notes="", resume_version_id=None, today=TODAY)
    with pytest.raises(TrackerError, match="doesn't belong"):
        update_application(jobs, other, status=JobStatus.SAVED, applied_on=None, follow_up_on=None, notes="",
                           resume_version_id="res-nope", today=TODAY)


def test_follow_ups_due_excludes_closed():
    due = Job(description="a", follow_up_on=date(2026, 10, 1), status=JobStatus.APPLIED)
    future = Job(description="b", follow_up_on=date(2026, 10, 9), status=JobStatus.APPLIED)
    closed = Job(description="c", follow_up_on=date(2026, 9, 1), status=JobStatus.REJECTED)
    assert follow_ups_due([due, future, closed], TODAY) == [due]


# ---- CSV ---------------------------------------------------------------------------------


def test_csv_export_and_formula_injection(stores):
    _, jobs, _ = stores
    jobs.add(Job(description="=HYPERLINK(\"http://x\")", title="=cmd|' /C calc'!A0", company="+Fictional",
                 notes="-2+3"))
    rows = build_rows(jobs, TODAY)
    data = list(csv.reader(io.StringIO(to_csv(rows))))
    header, row = data
    assert "jd_text" not in header
    rec = dict(zip(header, row))
    assert rec["role"].startswith("'=") and rec["company"] == "'+Fictional" and rec["notes"] == "'-2+3"
    with_jd = dict(zip(*list(csv.reader(io.StringIO(to_csv(rows, include_jd_text=True))))))
    assert with_jd["jd_text"].startswith("'=")


# ---- duplicates / merge ----------------------------------------------------------------


def test_duplicate_merge_keeps_chosen_record(stores, sample_profile, tmp_path):
    _, jobs, _ = stores
    keep, keep_version = _full_job(stores, sample_profile, tmp_path)
    jobs.update(jobs.get(keep.id).model_copy(update={"notes": "keep notes"}))
    drop = jobs.add(Job(description=JD, title="", source_url="https://www.naukri.com/job-listings-x-120924500123",
                        source_platform=SourcePlatform.NAUKRI,
                        status=JobStatus.APPLIED, applied_on=date(2026, 9, 30), notes="drop notes"))
    [pair] = duplicate_pairs(jobs.list())
    assert {pair.first.id, pair.second.id} == {keep.id, drop.id} and "identical" in pair.reason

    assert merge_loss(jobs, keep.id)  # keep has analysis/report/versions: user is told before choosing
    assert merge_loss(jobs, drop.id) == []
    merged = merge_jobs(jobs, keep.id, drop.id, tmp_path / "output")
    assert jobs.get(drop.id) is None and merged.id == keep.id
    assert merged.title == "Fictional Data Engineer"                       # keep's value wins
    assert merged.source_platform is SourcePlatform.NAUKRI                 # filled from drop
    assert (merged.status, merged.applied_on) == (JobStatus.APPLIED, date(2026, 9, 30))
    assert "keep notes" in merged.notes and "drop notes" in merged.notes
    assert jobs.get_resume_version(keep_version.id) is not None            # keep's resumes untouched
    with pytest.raises(TrackerError):
        merge_jobs(jobs, keep.id, keep.id, tmp_path)


def test_delete_job_removes_files(stores, sample_profile, tmp_path):
    _, jobs, _ = stores
    job, _ = _full_job(stores, sample_profile, tmp_path)
    assert (tmp_path / "output" / job.id).is_dir()
    assert delete_job(jobs, tmp_path / "output", job.id)
    assert not (tmp_path / "output" / job.id).exists() and jobs.get(job.id) is None


# ---- export all / delete everything -----------------------------------------------------


def test_export_all_data_zip(stores, sample_profile, tmp_path):
    profiles, jobs, settings = stores
    job, v = _full_job(stores, sample_profile, tmp_path)
    profiles.save_roles(profiles.load_roles())
    settings.save({"page_size": "Letter"})
    data = export_all_data(profiles, jobs, settings, tmp_path / "output")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert {"README.txt", "profile/master_profile.json", "profile/history/master_profile_v1.json",
                "profile/role_profiles.json", "settings.json", f"jobs/{job.id}.json"} <= names
        assert any(n.startswith(f"files/{job.id}/{v.id}/") and n.endswith(".pdf") for n in names)
        bundle = json.loads(z.read(f"jobs/{job.id}.json"))
        assert bundle["analysis"] and bundle["match_report"] and len(bundle["resume_versions"]) == 1
        assert "API" not in z.read("settings.json").decode()
    no_files = export_all_data(profiles, jobs, settings, tmp_path / "output", include_files=False)
    with zipfile.ZipFile(io.BytesIO(no_files)) as z:
        assert not any(n.startswith("files/") for n in z.namelist())


def test_delete_everything(stores, sample_profile, tmp_path):
    profiles, jobs, settings = stores
    job, _ = _full_job(stores, sample_profile, tmp_path)
    settings.save({"template": "compact"})
    (tmp_path / "output" / "keep-me.txt").write_text("not ours", encoding="utf-8")
    (tmp_path / "output" / "job-orphan1").mkdir()
    result = delete_everything(profiles, jobs, settings, tmp_path / "output")
    assert result == {"jobs": 1}
    assert profiles.load() is None and jobs.list() == [] and settings.load() == {}
    assert not (tmp_path / "output" / job.id).exists() and not (tmp_path / "output" / "job-orphan1").exists()
    assert (tmp_path / "output" / "keep-me.txt").exists()  # unrelated files are left alone
