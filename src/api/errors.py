"""One error shape for every failure: ``{"error": {"code", "message", "details"}}``."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.persistence.job_store import JobStoreError
from src.persistence.profile_store import ProfileStoreError
from src.services.profile_service import format_validation_error

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """A user-facing failure. ``message`` is shown in the UI as-is."""

    def __init__(self, status: int, code: str, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} was not found. It may have been deleted.")


def error_body(code: str, message: str, details: Optional[Any] = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


def _field_errors(errors: list[dict]) -> list[dict]:
    # Field locations and messages only. ``input`` is dropped: it may hold profile or JD text.
    return [{"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "")} for e in errors[:20]]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _request_invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(error_body("invalid_request", "Some fields are missing or invalid.",
                                       _field_errors(list(exc.errors()))), status_code=422)

    @app.exception_handler(ValidationError)
    async def _model_invalid(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(error_body("invalid_data", "Could not save. Please fix:\n" + format_validation_error(exc),
                                       _field_errors(list(exc.errors()))), status_code=422)

    @app.exception_handler(ProfileStoreError)
    @app.exception_handler(JobStoreError)
    async def _store_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("event=api_store_error error_type=%s", type(exc).__name__)
        return JSONResponse(error_body("store_unavailable", str(exc)), status_code=503)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Exception messages can quote profile or JD text, so the traceback is only logged at DEBUG.
        logger.error("event=api_unexpected_error error_type=%s", type(exc).__name__)
        logger.debug("event=api_unexpected_error_trace", exc_info=exc)
        return JSONResponse(error_body("internal_error", "Something went wrong in the local app. "
                                       "Check the API terminal for details."), status_code=500)
