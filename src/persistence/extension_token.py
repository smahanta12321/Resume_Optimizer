"""Pairing token shared between the local receiver and the browser extension.

Stored in ``data_dir/extension_token`` (git-ignored with the rest of data/), never
in settings.json, logs or data exports. Regenerating it un-pairs the extension.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_FILE = "extension_token"


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / TOKEN_FILE


def read_token(data_dir: Path) -> str | None:
    path = _path(data_dir)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def regenerate_token(data_dir: Path) -> str:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # best effort; no-op on Windows ACLs
    except OSError:
        pass
    return token


def get_or_create_token(data_dir: Path) -> str:
    return read_token(data_dir) or regenerate_token(data_dir)


def delete_token(data_dir: Path) -> None:
    _path(data_dir).unlink(missing_ok=True)
