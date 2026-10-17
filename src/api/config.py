"""Adapter-only settings, read from the environment. The app's own settings stay in ``src.config``."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

DEFAULT_PORT = 8000
DEFAULT_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",  # Vite dev server
    "http://localhost:4173", "http://127.0.0.1:4173",  # vite preview (production build)
)
TOKEN_HEADER = "X-Resume-Optimizer-Session"


@dataclass(frozen=True)
class ApiConfig:
    port: int
    origins: tuple[str, ...]
    token: str


def _port(raw: str | None) -> int:
    if not raw:
        return DEFAULT_PORT
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise ValueError("RESUME_OPTIMIZER_API_PORT must be between 1024 and 65535")
    return port


def load_api_config() -> ApiConfig:
    """Port, allowed browser origins, and the session token (random per launch unless set)."""
    raw_origins = os.getenv("RESUME_OPTIMIZER_API_ORIGINS", "").strip()
    origins = tuple(o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()) or DEFAULT_ORIGINS
    if "*" in origins:
        raise ValueError("RESUME_OPTIMIZER_API_ORIGINS must list exact origins, not '*'")
    token = os.getenv("RESUME_OPTIMIZER_API_TOKEN", "").strip() or secrets.token_urlsafe(24)
    return ApiConfig(port=_port(os.getenv("RESUME_OPTIMIZER_API_PORT", "").strip()), origins=origins, token=token)
