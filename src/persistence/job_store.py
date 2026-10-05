"""SQLite storage for imported job records and their JD analyses (``data_dir/jobs.sqlite3``).

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
from src.schemas.job import Job, JobStatus
from src.schemas.profile import utc_now

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_COLUMNS = [
    "id", "source_platform", "import_method", "source_url", "canonical_url", "source_label",
    "title", "company", "location", "description", "import_notes", "status", "notes",
    "imported_at", "updated_at",
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

# _MIGRATIONS[n] upgrades a database from user_version n to n + 1.
_MIGRATIONS = [_CREATE, _CREATE_ANALYSES]


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
        with closing(self._connect()) as conn, conn:
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
