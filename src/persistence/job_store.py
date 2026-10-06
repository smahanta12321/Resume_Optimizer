"""SQLite storage for jobs, JD analyses, match reports, resume versions and exports (``data_dir/jobs.sqlite3``).

Only extracted JD text, URL, timestamps and user-entered metadata are stored —
never raw page HTML. The schema is versioned with ``PRAGMA user_version`` and
upgraded in place by the ordered scripts in ``_MIGRATIONS``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from src.schemas.analysis import JDAnalysis
from src.schemas.capture import Capture
from src.schemas.export import ExportRecord
from src.schemas.job import Job, JobStatus
from src.schemas.match import MatchReport
from src.schemas.resume import ResumeVersion
from src.schemas.profile import utc_now

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 7

_COLUMNS = [
    "id", "source_platform", "import_method", "source_url", "canonical_url", "source_label",
    "title", "company", "location", "description", "import_notes", "status", "notes",
    "imported_at", "updated_at", "applied_on", "follow_up_on", "resume_version_id",
]

_CREATE = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL,
    import_method   TEXT NOT NULL,
    source_url      TEXT NOT NULL DEFAULT '',
    canonical_url   TEXT NOT NULL DEFAULT '',
    source_label    TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    company         TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL,
    import_notes    TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL,
    notes           TEXT NOT NULL DEFAULT '',
    imported_at     TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical_url ON jobs(canonical_url);
"""

_CREATE_ANALYSES = """
CREATE TABLE IF NOT EXISTS jd_analyses (
    job_id     TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_MATCH_REPORTS = """
CREATE TABLE IF NOT EXISTS match_reports (
    job_id     TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Resume content is write-once; only the approval columns may change afterwards.
_CREATE_RESUME_VERSIONS = """
CREATE TABLE IF NOT EXISTS resume_versions (
    id            TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    approved_at   TEXT,
    approval_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_resume_versions_job ON resume_versions(job_id);
"""

# _MIGRATIONS[n] upgrades a database from user_version n to n + 1.
_CREATE_EXPORTS = """
CREATE TABLE IF NOT EXISTS resume_exports (
    version_id TEXT PRIMARY KEY REFERENCES resume_versions(id) ON DELETE CASCADE,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_ADD_TRACKER_COLUMNS = """
ALTER TABLE jobs ADD COLUMN applied_on TEXT;
ALTER TABLE jobs ADD COLUMN follow_up_on TEXT;
ALTER TABLE jobs ADD COLUMN resume_version_id TEXT;
"""

# Browser-extension inbox: captured JDs awaiting review. Rows are deleted once imported or discarded.
_CREATE_CAPTURES = """
CREATE TABLE IF NOT EXISTS captures (
    id          TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    content     TEXT NOT NULL
);
"""

_MIGRATIONS = [_CREATE, _CREATE_ANALYSES, _CREATE_MATCH_REPORTS, _CREATE_RESUME_VERSIONS, _CREATE_EXPORTS,
               _ADD_TRACKER_COLUMNS, _CREATE_CAPTURES]


class JobStoreError(RuntimeError):
    """Raised when the job database is unreadable or a job is missing."""


def _to_row(job: Job) -> tuple:
    d = job.model_dump(mode="json")
    d["import_notes"] = json.dumps(d["import_notes"])
    return tuple(d[c] for c in _COLUMNS)


def _from_row(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["import_notes"] = json.loads(d["import_notes"] or "[]")
    return Job.model_validate(d)


class JobStore:
    """CRUD access to the jobs table. Opens a short-lived connection per call."""

    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / "jobs.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                conn.close()
                raise JobStoreError(
                    f"Job database {self.path} was created by a newer app version (schema {version})."
                )
            for step in range(version, SCHEMA_VERSION):
                with conn:
                    conn.executescript(_MIGRATIONS[step])
                    conn.execute(f"PRAGMA user_version = {step + 1}")
                logger.info("event=job_db_migrated to_version=%d", step + 1)
            return conn
        except sqlite3.DatabaseError as exc:
            logger.error("event=job_db_open_failed error_type=%s", type(exc).__name__)
            raise JobStoreError(f"Job database {self.path} could not be opened: {exc}") from exc

    def add(self, job: Job) -> Job:
        job = Job.model_validate(job.model_dump())
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with closing(self._connect()) as conn, conn:
            conn.execute(f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({placeholders})", _to_row(job))
        logger.info("event=job_added job_id=%s method=%s", job.id, job.import_method.value)
        return job

    def update(self, job: Job) -> Job:
        """Replace a stored job's fields (``imported_at`` is preserved, ``updated_at`` refreshed)."""
        existing = self.get(job.id)
        if existing is None:
            raise JobStoreError(f"Job {job.id} does not exist.")
        job = Job.model_validate(
            job.model_dump() | {"imported_at": existing.imported_at, "updated_at": utc_now()}
        )
        assignments = ", ".join(f"{c} = ?" for c in _COLUMNS[1:])
        row = _to_row(job)
        with closing(self._connect()) as conn, conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*row[1:], job.id))
        logger.info("event=job_updated job_id=%s", job.id)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _from_row(row) if row else None

    def list(self, status: Optional[JobStatus] = None) -> list[Job]:
        """All jobs, newest import first, optionally filtered by status."""
        query, params = "SELECT * FROM jobs", ()
        if status is not None:
            query, params = query + " WHERE status = ?", (status.value,)
        with closing(self._connect()) as conn:
            rows = conn.execute(query + " ORDER BY imported_at DESC", params).fetchall()
        return [_from_row(r) for r in rows]

    def delete(self, job_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            deleted = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount
        if deleted:
            logger.info("event=job_deleted job_id=%s", job_id)
        return bool(deleted)

    def delete_all(self) -> int:
        """Delete every job (cascading to derived data) and the extension inbox."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM captures")
            count = conn.execute("DELETE FROM jobs").rowcount
        logger.info("event=jobs_deleted count=%d", count)
        return count

    # ---- JD analyses ------------------------------------------------------------

    def get_analysis(self, job_id: str) -> Optional[JDAnalysis]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT content FROM jd_analyses WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        try:
            return JDAnalysis.model_validate_json(row["content"])
        except ValueError as exc:
            raise JobStoreError(f"Stored analysis for job {job_id} is unreadable: {exc}") from exc

    def save_analysis(self, analysis: JDAnalysis) -> JDAnalysis:
        """Insert or replace the analysis for its job (``updated_at`` refreshed)."""
        analysis = JDAnalysis.model_validate(analysis.model_dump() | {"updated_at": utc_now()})
        if self.get(analysis.job_id) is None:
            raise JobStoreError(f"Job {analysis.job_id} does not exist.")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO jd_analyses (job_id, content, updated_at) VALUES (?, ?, ?)",
                (analysis.job_id, analysis.model_dump_json(), analysis.updated_at.isoformat()),
            )
        logger.info("event=analysis_saved job_id=%s requirements=%d confirmed=%s",
                    analysis.job_id, len(analysis.requirements), analysis.confirmed_at is not None)
        return analysis

    def delete_analysis(self, job_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return bool(conn.execute("DELETE FROM jd_analyses WHERE job_id = ?", (job_id,)).rowcount)

    def analysis_ids(self) -> set[str]:
        """Job IDs that have an analysis (cheap, for list badges)."""
        with closing(self._connect()) as conn:
            return {r[0] for r in conn.execute("SELECT job_id FROM jd_analyses")}

    # ---- match reports ----------------------------------------------------------

    def get_match_report(self, job_id: str) -> Optional[MatchReport]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT content FROM match_reports WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        try:
            return MatchReport.model_validate_json(row["content"])
        except ValueError as exc:
            raise JobStoreError(f"Stored match report for job {job_id} is unreadable: {exc}") from exc

    def save_match_report(self, report: MatchReport) -> MatchReport:
        """Insert or replace the match report for its job (``updated_at`` refreshed)."""
        report = MatchReport.model_validate(report.model_dump() | {"updated_at": utc_now()})
        if self.get(report.job_id) is None:
            raise JobStoreError(f"Job {report.job_id} does not exist.")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO match_reports (job_id, content, updated_at) VALUES (?, ?, ?)",
                (report.job_id, report.model_dump_json(), report.updated_at.isoformat()),
            )
        logger.info("event=match_report_saved job_id=%s matches=%d", report.job_id, len(report.matches))
        return report

    def match_report_ids(self) -> set[str]:
        with closing(self._connect()) as conn:
            return {r[0] for r in conn.execute("SELECT job_id FROM match_reports")}

    # ---- resume versions (immutable content) ------------------------------------

    def add_resume_version(self, version: ResumeVersion) -> ResumeVersion:
        """Store a new version. Existing versions are never overwritten."""
        version = ResumeVersion.model_validate(version.model_dump() | {"approved_at": None, "approval_note": ""})
        if self.get(version.job_id) is None:
            raise JobStoreError(f"Job {version.job_id} does not exist.")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO resume_versions (id, job_id, content, created_at) VALUES (?, ?, ?, ?)",
                (version.id, version.job_id, version.model_dump_json(exclude={"approved_at", "approval_note"}),
                 version.created_at.isoformat()),
            )
        logger.info("event=resume_version_added job_id=%s version_id=%s generator=%s",
                    version.job_id, version.id, version.generator)
        return version

    def _version_from_row(self, row: sqlite3.Row) -> ResumeVersion:
        try:
            data = json.loads(row["content"])
            data["approved_at"] = row["approved_at"]
            data["approval_note"] = row["approval_note"]
            return ResumeVersion.model_validate(data)
        except ValueError as exc:
            raise JobStoreError(f"Stored resume version {row['id']} is unreadable: {exc}") from exc

    def get_resume_version(self, version_id: str) -> Optional[ResumeVersion]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM resume_versions WHERE id = ?", (version_id,)).fetchone()
        return self._version_from_row(row) if row else None

    def list_resume_versions(self, job_id: str) -> list[ResumeVersion]:
        """Versions for a job, newest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM resume_versions WHERE job_id = ? ORDER BY created_at DESC, rowid DESC",
                                (job_id,)).fetchall()
        return [self._version_from_row(r) for r in rows]

    def approve_resume_version(self, version_id: str, note: str = "") -> ResumeVersion:
        """Record approval. Content is not touched."""
        with closing(self._connect()) as conn, conn:
            updated = conn.execute(
                "UPDATE resume_versions SET approved_at = ?, approval_note = ? WHERE id = ? AND approved_at IS NULL",
                (utc_now().isoformat(), note, version_id),
            ).rowcount
        if not updated:
            raise JobStoreError(f"Resume version {version_id} does not exist or is already approved.")
        logger.info("event=resume_version_approved version_id=%s", version_id)
        return self.get_resume_version(version_id)

    def resume_counts(self) -> dict[str, tuple[int, int]]:
        """job_id -> (versions, approved versions)."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT job_id, COUNT(*), COUNT(approved_at) FROM resume_versions GROUP BY job_id")
            return {r[0]: (r[1], r[2]) for r in rows}

    # ---- exports ----------------------------------------------------------------

    def save_export(self, record: ExportRecord) -> ExportRecord:
        """Insert or replace the export record for an approved version."""
        version = self.get_resume_version(record.version_id)
        if version is None:
            raise JobStoreError(f"Resume version {record.version_id} does not exist.")
        if version.approved_at is None:
            raise JobStoreError("Only approved versions can be exported.")
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO resume_exports (version_id, content, created_at) VALUES (?, ?, ?)",
                         (record.version_id, record.model_dump_json(), record.created_at.isoformat()))
        return record

    def get_export(self, version_id: str) -> Optional[ExportRecord]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT content FROM resume_exports WHERE version_id = ?", (version_id,)).fetchone()
        if row is None:
            return None
        try:
            return ExportRecord.model_validate_json(row["content"])
        except ValueError as exc:
            raise JobStoreError(f"Stored export record for {version_id} is unreadable: {exc}") from exc

    def export_counts(self) -> dict[str, int]:
        """job_id -> number of exported versions."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT v.job_id, COUNT(*) FROM resume_exports e "
                                "JOIN resume_versions v ON v.id = e.version_id GROUP BY v.job_id")
            return {r[0]: r[1] for r in rows}

    # ---- browser-extension inbox --------------------------------------------------

    MAX_PENDING_CAPTURES = 50

    def add_capture(self, capture: Capture) -> Capture:
        capture = Capture.model_validate(capture.model_dump())
        with closing(self._connect()) as conn, conn:
            pending = conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
            if pending >= self.MAX_PENDING_CAPTURES:
                raise JobStoreError(f"The extension inbox is full ({pending} items). Review or discard some first.")
            conn.execute("INSERT INTO captures (id, received_at, content) VALUES (?, ?, ?)",
                         (capture.id, capture.received_at.isoformat(), capture.model_dump_json()))
        logger.info("event=capture_received capture_id=%s method=%s", capture.id, capture.method)
        return capture

    def list_captures(self) -> list[Capture]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT content FROM captures ORDER BY received_at DESC").fetchall()
        out = []
        for r in rows:
            try:
                out.append(Capture.model_validate_json(r["content"]))
            except ValueError:
                logger.warning("event=capture_unreadable")
        return out

    def delete_capture(self, capture_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return bool(conn.execute("DELETE FROM captures WHERE id = ?", (capture_id,)).rowcount)
