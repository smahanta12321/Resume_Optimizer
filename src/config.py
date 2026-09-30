"""Application configuration loaded from environment variables (and an optional .env)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    output_dir: Path
    log_level: str


def get_settings() -> Settings:
    """Read settings from the environment. ``.env`` is loaded but never overrides real env vars."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    data_dir = Path(os.getenv("RESUME_OPTIMIZER_DATA_DIR", PROJECT_ROOT / "data"))
    output_dir = Path(os.getenv("RESUME_OPTIMIZER_OUTPUT_DIR", PROJECT_ROOT / "output"))
    return Settings(
        data_dir=data_dir,
        output_dir=output_dir,
        log_level=os.getenv("RESUME_OPTIMIZER_LOG_LEVEL", "INFO").upper(),
    )


def configure_logging(level: str = "INFO") -> None:
    """Configure structured-ish key=value logging. Callers must never log profile content or secrets."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
    )
