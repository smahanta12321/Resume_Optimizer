"""File-backed storage for the master profile and role-profile library.

Layout under ``data_dir/profile``::

    master_profile.json            current version (plus confirmation metadata)
    history/master_profile_v{N}.json   write-once snapshot of every saved version
    role_profiles.json             role-profile library

Snapshots are opened in exclusive-create mode so an existing version can never
be overwritten.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from src.schemas.profile import MasterProfile, RoleProfileLibrary, utc_now

logger = logging.getLogger(__name__)

_SNAPSHOT_RE = re.compile(r"^master_profile_v(\d+)\.json$")
# Fields that describe a version rather than profile content.
_META_FIELDS = {"profile_version", "updated_at", "confirmed_at"}


class ProfileStoreError(RuntimeError):
    """Raised when stored profile data is missing, unreadable, or invalid."""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def profile_content(profile: MasterProfile) -> dict:
    """Profile data minus version metadata; used to detect real changes."""
    return profile.model_dump(mode="json", exclude=_META_FIELDS)


class ProfileStore:
    """Reads and writes the master profile and role profiles as JSON files."""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir) / "profile"
        self.current_path = self.root / "master_profile.json"
        self.history_dir = self.root / "history"
        self.roles_path = self.root / "role_profiles.json"

    # ---- master profile -------------------------------------------------

    def load(self) -> Optional[MasterProfile]:
        """Return the current profile, or ``None`` if none has been saved."""
        if not self.current_path.exists():
            return None
        try:
            return MasterProfile.model_validate_json(self.current_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("event=profile_load_failed path=%s error_type=%s", self.current_path, type(exc).__name__)
            raise ProfileStoreError(f"Stored profile at {self.current_path} could not be read: {exc}") from exc

    def save_new_version(self, profile: MasterProfile) -> MasterProfile:
        """Persist ``profile`` as a new immutable version if its content changed.

        Returns the stored profile. If content is identical to the current
        version, nothing is written and the current profile is returned.
        A new version always clears ``confirmed_at``: edited data must be re-reviewed.
        """
        try:
            current = self.load()
        except ProfileStoreError:
            # A corrupt current file must not block recovery (import/restore); snapshots stay intact.
            logger.warning("event=profile_save_over_unreadable_current")
            current = None
        if current is not None and profile_content(current) == profile_content(profile):
            return current

        next_version = max(self.list_versions(), default=0) + 1
        stored = profile.model_copy(
            update={"profile_version": next_version, "updated_at": utc_now(), "confirmed_at": None}
        )
        # Round-trip through validation so nothing invalid reaches disk.
        stored = MasterProfile.model_validate(stored.model_dump())
        text = stored.model_dump_json(indent=2)

        self.history_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self.history_dir / f"master_profile_v{next_version}.json"
        with open(snapshot, "x", encoding="utf-8") as fh:  # "x": never overwrite a version
            fh.write(text)
        _atomic_write(self.current_path, text)
        logger.info("event=profile_saved version=%d", next_version)
        return stored

    def mark_confirmed(self) -> MasterProfile:
        """Record that the user reviewed and confirmed the current version."""
        current = self.load()
        if current is None:
            raise ProfileStoreError("No profile to confirm.")
        confirmed = current.model_copy(update={"confirmed_at": utc_now()})
        _atomic_write(self.current_path, confirmed.model_dump_json(indent=2))
        logger.info("event=profile_confirmed version=%d", confirmed.profile_version)
        return confirmed

    def list_versions(self) -> list[int]:
        """Sorted version numbers that have snapshots."""
        if not self.history_dir.exists():
            return []
        versions = []
        for p in self.history_dir.iterdir():
            m = _SNAPSHOT_RE.match(p.name)
            if m:
                versions.append(int(m.group(1)))
        return sorted(versions)

    def load_version(self, version: int) -> MasterProfile:
        path = self.history_dir / f"master_profile_v{int(version)}.json"
        if not path.exists():
            raise ProfileStoreError(f"Profile version {version} does not exist.")
        return MasterProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def delete_all(self) -> None:
        """Delete the current profile, all snapshots, and the role-profile library."""
        for p in [self.current_path, self.roles_path]:
            p.unlink(missing_ok=True)
        if self.history_dir.exists():
            for p in self.history_dir.iterdir():
                if _SNAPSHOT_RE.match(p.name):
                    p.unlink()
            try:
                self.history_dir.rmdir()
            except OSError:
                pass  # leave unexpected files in place
        logger.info("event=profile_data_deleted")

    # ---- role profiles ---------------------------------------------------

    def load_roles(self) -> RoleProfileLibrary:
        if not self.roles_path.exists():
            return RoleProfileLibrary()
        try:
            return RoleProfileLibrary.model_validate_json(self.roles_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProfileStoreError(f"Stored role profiles could not be read: {exc}") from exc

    def save_roles(self, library: RoleProfileLibrary) -> None:
        library = RoleProfileLibrary.model_validate(library.model_dump())
        _atomic_write(self.roles_path, library.model_dump_json(indent=2))
        logger.info("event=role_profiles_saved count=%d", len(library.role_profiles))


def read_json_file(path: Path) -> dict:
    """Small helper for loading bundled sample files."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
