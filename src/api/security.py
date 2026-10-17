"""Request guard for the local API.

A localhost API can be reached by any web page the user happens to visit, so every request must:

* address 127.0.0.1/localhost on our port (Host check; blocks DNS rebinding);
* come from an allowed frontend origin, or from no browser origin at all (curl, tests);
* carry the per-launch session token (constant-time comparison), except ``GET /api/v1/health``;
* stay under the body-size limit.

The custom token header also forces a CORS preflight, so other sites can't send "simple" requests.
"""

from __future__ import annotations

import hmac
import logging
from typing import Awaitable, Callable, Iterable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from src.api.config import TOKEN_HEADER
from src.api.errors import error_body

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 6_000_000  # JD uploads are capped at 5 MB by the import service
PUBLIC_PATHS = {"/api/v1/health"}


def make_guard(*, token: str, origins: Iterable[str], hosts: Iterable[str]
               ) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    allowed_origins = set(origins)
    allowed_hosts = {h.lower() for h in hosts}

    def deny(status: int, code: str, message: str) -> JSONResponse:
        logger.info("event=api_request_rejected status=%d code=%s", status, code)
        return JSONResponse(error_body(code, message), status_code=status)

    async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if (request.headers.get("host") or "").lower() not in allowed_hosts:
            return deny(403, "bad_host", "Requests must address the local app directly.")
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in allowed_origins:
            return deny(403, "origin_not_allowed", "This web page is not allowed to use the local app. "
                                                   "Add its origin to RESUME_OPTIMIZER_API_ORIGINS if it is yours.")
        if request.method == "OPTIONS":
            return await call_next(request)  # preflight: answered by the CORS middleware
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            return deny(413, "too_large", "The request is too large.")
        if request.url.path not in PUBLIC_PATHS:
            given = request.headers.get(TOKEN_HEADER, "")
            if not given or not hmac.compare_digest(given.encode(), token.encode()):
                return deny(401, "session_token_invalid", "Session token missing or wrong. Open the link printed "
                                                          "by `python -m src.api`, or paste the token in Settings.")
        return await call_next(request)

    return guard
