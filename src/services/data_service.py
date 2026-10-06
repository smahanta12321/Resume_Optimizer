"""Export all of the user's data as one zip, or delete all of it."""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from src.persistence.extension_token import delete_token
from src.persistence.job_store import JobStore
from src.persistence.profile_store import ProfileStore
from src.persistence.settings_store import SettingsStore
from src.services.export_service import delete_job_outputs

logger = logging.getLogger(__name__)
_JOB_DIR_RE = re.compile(r"^job-[A-Za-z0-9-]{1,40}$")

README = """AI Resume Optimizer: data export ({when})

profile/master_profile.json      current master profile (re-importable on the Master Profile page)
profile/history/                 every saved profile version
profile/role_profiles.json       role profiles
jobs/<job id>.json               job, JD analysis, match report, resume versions and export records
files/<job id>/<version id>/     exported DOCX/PDF files (if included)
settings.json                    app settings (no API keys; those live only in your environment)
captures.json                    browser-extension captures still awaiting review

This archive contains personal data. Store it somewhere private.
"""


def export_all_data(profiles: ProfileStore, jobs: JobStore, settings: SettingsStore, output_dir: Path,
                    *, include_files: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README.format(when=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
        for path, arc in ((profiles.current_path, "profile/master_profile.json"),
                          (profiles.roles_path, "profile/role_profiles.json"), (settings.path, "settings.json")):
            if path.is_file():
                z.write(path, arc)
        for v in profiles.list_versions():
            z.write(profiles.history_dir / f"master_profile_v{v}.json", f"profile/history/master_profile_v{v}.json")
        captures = jobs.list_captures()
        if captures:
            z.writestr("captures.json", json.dumps([c.model_dump(mode="json") for c in captures], indent=2,
                                                   ensure_ascii=False))
        for job in jobs.list():
            versions = jobs.list_resume_versions(job.id)
            analysis, report = jobs.get_analysis(job.id), jobs.get_match_report(job.id)
            exports = [e for e in (jobs.get_export(v.id) for v in versions) if e]
            bundle = {
                "job": job.model_dump(mode="json"),
                "analysis": analysis.model_dump(mode="json") if analysis else None,
                "match_report": report.model_dump(mode="json") if report else None,
                "resume_versions": [v.model_dump(mode="json") for v in versions],
                "exports": [e.model_dump(mode="json") for e in exports],
            }
            z.writestr(f"jobs/{job.id}.json", json.dumps(bundle, indent=2, ensure_ascii=False))
            if include_files:
                for e in exports:
                    for p in (Path(e.docx_path), Path(e.pdf_path)):
                        if p.is_file():
                            z.write(p, f"files/{job.id}/{e.version_id}/{p.name}")
    logger.info("event=data_exported")
    return buf.getvalue()


def delete_everything(profiles: ProfileStore, jobs: JobStore, settings: SettingsStore, output_dir: Path) -> dict:
    """Delete the profile (all versions), role profiles, all jobs and derived data, exported files, the
    extension inbox and pairing token, and settings."""
    job_list = jobs.list()
    for job in job_list:
        delete_job_outputs(output_dir, job.id)
    root = Path(output_dir)
    if root.is_dir():  # leftovers from jobs deleted outside the app; only folders this app creates
        for child in root.iterdir():
            if child.is_dir() and _JOB_DIR_RE.match(child.name):
                shutil.rmtree(child)
    removed_jobs = jobs.delete_all()  # also empties the extension inbox
    profiles.delete_all()
    settings.delete()
    delete_token(settings.path.parent)
    logger.info("event=all_data_deleted jobs=%d", removed_jobs)
    return {"jobs": removed_jobs}
