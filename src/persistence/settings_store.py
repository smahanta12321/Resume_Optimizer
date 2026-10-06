"""User-editable, non-secret settings saved from the Settings page (``data_dir/settings.json``).

Secrets (API keys) are rejected here by design: they belong in the environment.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import SETTINGS_FILE, USER_EDITABLE, parse_setting, read_settings_file
from src.persistence.profile_store import _atomic_write

logger = logging.getLogger(__name__)


class SettingsError(ValueError):
    """Invalid settings change. Message is user-facing."""


class SettingsStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = Path(data_dir) / SETTINGS_FILE

    def load(self) -> dict[str, Any]:
        return read_settings_file(self.path.parent)

    def save(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate and merge ``changes`` into settings.json. Nothing is written if any value is invalid."""
        unknown = set(changes) - set(USER_EDITABLE)
        if unknown:
            raise SettingsError(f"Not a saveable setting: {', '.join(sorted(unknown))}. API keys go in the "
                                "environment (.env), never in app settings.")
        clean = {}
        for name, value in changes.items():
            try:
                clean[name] = parse_setting(name, value)
            except (ValueError, TypeError) as exc:
                raise SettingsError(f"Invalid value for {name}: {exc}") from exc
        merged = {**self.load(), **clean}
        _atomic_write(self.path, json.dumps(merged, indent=2, sort_keys=True))
        logger.info("event=settings_saved keys=%s", ",".join(sorted(clean)))
        return merged

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
