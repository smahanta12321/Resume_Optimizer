"""Local receiver for the optional browser extension.

Run with:  python -m src.extension_receiver

It listens on 127.0.0.1 only and accepts one thing: a JD the user captured and
approved in the extension popup, which goes into the review inbox (Job Import page).
Requests must:

* be enabled in Settings (re-checked on every request);
* address 127.0.0.1/localhost on the configured port (Host check; blocks DNS rebinding);
* come from a browser-extension origin, or from no browser origin at all; web pages are refused;
* carry the pairing token from Settings (constant-time comparison);
* be JSON, under the size limit, and pass schema validation.

Captured content is untrusted data: it is stored for review, never acted on.
"""

from __future__ import annotations

import hmac
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from pydantic import ValidationError

from src.config import configure_logging, get_settings
from src.persistence.extension_token import read_token
from src.persistence.job_store import JobStore, JobStoreError
from src.schemas.capture import Capture, CaptureIn
from src.services.jd_import_service import JDImportError, check_jd_text

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-Resume-Optimizer-Token"
MAX_BODY_BYTES = 300_000
EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://")


class CaptureHandler(BaseHTTPRequestHandler):
    server_version = "ResumeOptimizerReceiver"
    sys_version = ""

    # ---- helpers ----------------------------------------------------------------

    def _origin(self) -> Optional[str]:
        return self.headers.get("Origin")

    def _origin_allowed(self) -> bool:
        origin = self._origin()
        return origin is None or origin.startswith(EXTENSION_ORIGINS)

    def _host_allowed(self) -> bool:
        port = self.server.server_address[1]
        return (self.headers.get("Host") or "").lower() in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _send(self, status: HTTPStatus, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self._origin()
        if origin and origin.startswith(EXTENSION_ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        logger.info("event=capture_rejected status=%d", status.value)
        self._send(status, {"ok": False, "error": message})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature from BaseHTTPRequestHandler
        logger.debug("event=receiver_request line=%s", args[0] if args else "")  # request line only, no bodies

    # ---- routes -------------------------------------------------------------------

    def do_OPTIONS(self) -> None:  # CORS preflight from the extension
        if not (self._host_allowed() and self._origin() and self._origin().startswith(EXTENSION_ORIGINS)):
            return self._error(HTTPStatus.FORBIDDEN, "Origin not allowed.")
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", self._origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {TOKEN_HEADER}")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/health":
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")
        if not (self._host_allowed() and self._origin_allowed()):
            return self._error(HTTPStatus.FORBIDDEN, "Not allowed.")
        self._send(HTTPStatus.OK, {"ok": True, "app": "resume-optimizer",
                                   "enabled": get_settings().extension_enabled})

    def do_POST(self) -> None:
        if self.path != "/capture":
            return self._error(HTTPStatus.NOT_FOUND, "Not found.")
        settings = get_settings()
        if not settings.extension_enabled:
            return self._error(HTTPStatus.FORBIDDEN, "The browser extension is turned off in Settings.")
        if not self._host_allowed():
            return self._error(HTTPStatus.FORBIDDEN, "Bad host.")
        if not self._origin_allowed():
            return self._error(HTTPStatus.FORBIDDEN, "Web pages cannot send data here.")
        expected = read_token(settings.data_dir)
        given = self.headers.get(TOKEN_HEADER, "")
        if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
            return self._error(HTTPStatus.UNAUTHORIZED, "Pairing token missing or wrong. Copy it from Settings.")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_BODY_BYTES:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Empty or too large.")
        try:
            payload = CaptureIn.model_validate_json(self.rfile.read(length))
            text, _ = check_jd_text(payload.text)
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, e["loc"])) or "body" for e in exc.errors()[:5])
            return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, f"Invalid capture ({fields}).")
        except JDImportError as exc:
            return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        try:
            capture = JobStore(settings.data_dir).add_capture(Capture(**payload.model_dump() | {"text": text}))
        except JobStoreError as exc:
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        self._send(HTTPStatus.CREATED, {"ok": True, "id": capture.id,
                                        "message": "Sent. Review it in Resume Optimizer → Job Import."})


def make_server(port: Optional[int] = None) -> ThreadingHTTPServer:
    """Bind the receiver to 127.0.0.1 (never all interfaces)."""
    return ThreadingHTTPServer(("127.0.0.1", get_settings().extension_port if port is None else port),
                               CaptureHandler)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    server = make_server(settings.extension_port)
    state = "enabled" if settings.extension_enabled else "DISABLED (turn it on in Settings)"
    print(f"Resume Optimizer extension receiver on http://127.0.0.1:{settings.extension_port} ({state}). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
