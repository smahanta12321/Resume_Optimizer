"""Application configuration.

Each setting resolves in this order: a non-empty environment variable (``.env``
included) -> ``<data_dir>/settings.json`` (saved from the Settings page) -> default.
``Settings.sources`` records which one applied, so the UI can explain it.
API keys are never part of these settings: provider SDKs read them from the environment.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = "settings.json"

LLM_PROVIDERS = ("none", "anthropic", "openai")
PAGE_SIZES = ("A4", "Letter")
TEMPLATES = ("classic", "compact")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    output_dir: Path
    log_level: str
    url_import_enabled: bool = True
    url_timeout_seconds: float = 10.0
    llm_provider: str = "none"  # none | anthropic | openai
    llm_model: str = ""         # empty -> provider default (Anthropic only; OpenAI requires a model)
    llm_timeout_seconds: float = 60.0
    page_size: str = "A4"       # A4 | Letter (resume export)
    template: str = "classic"   # classic | compact
    local_only: bool = False    # True blocks URL import and AI calls
    extension_enabled: bool = False  # local receiver for the optional browser extension
    extension_port: int = 8765
    sources: dict[str, str] = field(default_factory=dict, compare=False)  # setting -> env | file | default | local-only


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "off", "false", "no", "")


def _choice(options: tuple[str, ...]) -> Callable[[Any], str]:
    def parse(value: Any) -> str:
        v = str(value).strip()
        match = next((o for o in options if o.lower() == v.lower()), None)
        if match is None:
            raise ValueError(f"must be one of {', '.join(options)}")
        return match
    return parse


def _clamped(low: float, high: float) -> Callable[[Any], float]:
    return lambda v: min(max(float(v), low), high)


def _port(value: Any) -> int:
    port = int(value)
    if not 1024 <= port <= 65535:
        raise ValueError("must be a port between 1024 and 65535")
    return port


# setting -> (environment variable, parser, default)
_SPEC: dict[str, tuple[str, Callable[[Any], Any], Any]] = {
    "url_import_enabled": ("RESUME_OPTIMIZER_URL_IMPORT", _bool, True),
    "url_timeout_seconds": ("RESUME_OPTIMIZER_URL_TIMEOUT", _clamped(1.0, 30.0), 10.0),
    "llm_provider": ("RESUME_OPTIMIZER_LLM_PROVIDER", _choice(LLM_PROVIDERS), "none"),
    "llm_model": ("RESUME_OPTIMIZER_LLM_MODEL", lambda v: str(v).strip(), ""),
    "llm_timeout_seconds": ("RESUME_OPTIMIZER_LLM_TIMEOUT", _clamped(5.0, 600.0), 60.0),
    "page_size": ("RESUME_OPTIMIZER_PAGE_SIZE", _choice(PAGE_SIZES), "A4"),
    "template": ("RESUME_OPTIMIZER_TEMPLATE", _choice(TEMPLATES), "classic"),
    "local_only": ("RESUME_OPTIMIZER_LOCAL_ONLY", _bool, False),
    "extension_enabled": ("RESUME_OPTIMIZER_EXTENSION", _bool, False),
    "extension_port": ("RESUME_OPTIMIZER_EXTENSION_PORT", _port, 8765),
}
USER_EDITABLE = tuple(_SPEC)


def env_var_for(setting: str) -> str:
    return _SPEC[setting][0]


def parse_setting(setting: str, value: Any) -> Any:
    """Validate/normalize one user-editable setting. Raises ValueError/TypeError if invalid."""
    return _SPEC[setting][1](value)


def read_settings_file(data_dir: Path) -> dict[str, Any]:
    path = Path(data_dir) / SETTINGS_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("event=settings_file_unreadable")
        return {}
    return {k: v for k, v in data.items() if k in _SPEC} if isinstance(data, dict) else {}


def get_settings() -> Settings:
    """Resolve settings: environment (incl. ``.env``) > settings.json > defaults. Never overrides real env vars."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    data_dir = Path(os.getenv("RESUME_OPTIMIZER_DATA_DIR") or PROJECT_ROOT / "data")
    output_dir = Path(os.getenv("RESUME_OPTIMIZER_OUTPUT_DIR") or PROJECT_ROOT / "output")
    saved = read_settings_file(data_dir)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name, (env, parse, default) in _SPEC.items():
        values[name], sources[name] = default, "default"
        for source, raw in (("env", os.getenv(env, "").strip() or None), ("file", saved.get(name))):
            if raw is None:
                continue
            try:
                values[name], sources[name] = parse(raw), source
                break
            except (ValueError, TypeError):
                logger.warning("event=setting_invalid name=%s source=%s", name, source)
    if values["local_only"]:
        for name, off in (("url_import_enabled", False), ("llm_provider", "none")):
            values[name], sources[name] = off, "local-only"
    return Settings(data_dir=data_dir, output_dir=output_dir,
                    log_level=os.getenv("RESUME_OPTIMIZER_LOG_LEVEL", "INFO").upper(), sources=sources, **values)


def configure_logging(level: str = "INFO") -> None:
    """Configure structured-ish key=value logging. Callers must never log profile content or secrets."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
    )


def setting_default(setting: str) -> Any:
    return _SPEC[setting][2]
