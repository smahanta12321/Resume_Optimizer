"""FastAPI application factory for the local adapter."""

from __future__ import annotations

from typing import Iterable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import TOKEN_HEADER, ApiConfig, load_api_config
from src.api.errors import install_error_handlers
from src.api.routes import jobs, match, profile, resumes, system, tracker
from src.api.security import make_guard

PREFIX = "/api/v1"


def create_app(config: Optional[ApiConfig] = None, *, hosts: Optional[Iterable[str]] = None) -> FastAPI:
    """Build the app. ``hosts`` overrides the allowed Host headers (tests use ``testserver``)."""
    config = config or load_api_config()
    app = FastAPI(title="Resume Optimizer local API", version=str(system.API_VERSION),
                  description="Local-only adapter over the Resume Optimizer services, for the React frontend.")
    install_error_handlers(app)
    for module in (system, profile, jobs, match, resumes, tracker):
        app.include_router(module.router, prefix=PREFIX)
    allowed_hosts = hosts or (f"127.0.0.1:{config.port}", f"localhost:{config.port}")
    app.middleware("http")(make_guard(token=config.token, origins=config.origins, hosts=allowed_hosts))
    # Added last, so it runs first: answers preflights and adds CORS headers to every response, errors included.
    app.add_middleware(CORSMiddleware, allow_origins=list(config.origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", TOKEN_HEADER], expose_headers=["Content-Disposition"],
                       max_age=600)
    return app
