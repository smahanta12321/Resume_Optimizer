"""Best-effort, user-initiated import of a single job page by URL.

Safety rules (see SPECIFICATION FR-3):

* only ``http``/``https`` on default ports, no embedded credentials;
* every hostname must resolve exclusively to public IP addresses (SSRF guard),
  re-checked on each redirect, with a small redirect limit;
* conservative timeouts, a total deadline, and a response-size cap;
* robots.txt is honoured, and login walls / CAPTCHAs / rate limits are never
  bypassed — they end the attempt with a request to paste the JD instead;
* no cookies, credentials, or proxy/netrc settings are sent;
* page content is untrusted data: only text is kept, never raw HTML.

Known limitation: the IP check and the connection resolve DNS separately, so a
hostile DNS server could still race (DNS rebinding). Acceptable for a local,
single-user tool fetching URLs the user typed.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import time
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from src.schemas.job import SourcePlatform
from src.services.jd_import_service import MIN_JD_CHARS, infer_platform, normalize_jd_text

logger = logging.getLogger(__name__)

USER_AGENT = "AIResumeOptimizer/0.2 (local personal tool; single user-initiated page fetch)"
MAX_RESPONSE_BYTES = 2_000_000
MAX_ROBOTS_BYTES = 500_000
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 10.0
_ALLOWED_PORTS = {None, 80, 443}
_HTML_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_BLOCKED_STATUSES = {401, 403, 407, 429, 999}  # 999: LinkedIn's anti-bot response
_LOGIN_PATH_RE = re.compile(r"/(authwall|login|signin|sign-in|uas/login|checkpoint|captcha)\b", re.I)
_BLOCK_MARKERS = (
    "captcha", "verify you are human", "are you a robot", "unusual traffic", "sign in to view",
    "join to view", "log in to continue", "please enable javascript", "access denied",
)

Resolver = Callable[[str], list[str]]


class FailureReason(str, Enum):
    DISABLED = "disabled"
    UNSAFE_URL = "unsafe_url"
    DISALLOWED = "disallowed_by_site"
    BLOCKED = "login_or_bot_check"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    UNSUPPORTED_CONTENT = "unsupported_content"
    INCOMPLETE = "incomplete"
    NETWORK = "network"


class UrlImportError(Exception):
    """URL import failed. ``message`` is user-facing and always suggests a fallback."""

    def __init__(self, reason: FailureReason, message: str) -> None:
        super().__init__(f"{message} Please paste the job description text or upload it as a file instead.")
        self.reason = reason


@dataclass
class UrlImportResult:
    text: str
    final_url: str
    platform: SourcePlatform
    method: str  # "structured" (schema.org JobPosting) or "page_text"
    title: str = ""
    company: str = ""
    location: str = ""
    notes: list[str] = field(default_factory=list)


# ---- URL safety -----------------------------------------------------------------


def system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


def _is_public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str, resolver: Resolver = system_resolver) -> str:
    """Return ``url`` if it is safe to fetch, else raise ``UrlImportError(UNSAFE_URL)``."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise UrlImportError(FailureReason.UNSAFE_URL, "That URL is not valid.") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise UrlImportError(FailureReason.UNSAFE_URL, "Only http:// and https:// URLs can be imported.")
    if parts.username or parts.password:
        raise UrlImportError(FailureReason.UNSAFE_URL, "URLs containing usernames or passwords are not allowed.")
    if not parts.hostname:
        raise UrlImportError(FailureReason.UNSAFE_URL, "The URL has no host name.")
    if port not in _ALLOWED_PORTS:
        raise UrlImportError(FailureReason.UNSAFE_URL, "Only standard web ports (80/443) are allowed.")
    try:
        ipaddress.ip_address(parts.hostname.split("%", 1)[0])
        addresses = [parts.hostname]  # IP literal: check it directly, no DNS lookup
    except ValueError:
        addresses = None
    try:
        addresses = addresses or resolver(parts.hostname)
    except (OSError, UnicodeError) as exc:
        raise UrlImportError(FailureReason.NETWORK, "The site's address could not be found.") from exc
    if not addresses or not all(_is_public(a) for a in addresses):
        logger.warning("event=url_blocked_non_public")
        raise UrlImportError(
            FailureReason.UNSAFE_URL, "That address points to a local or private network, which is not allowed."
        )
    return url.strip()


# ---- fetching -------------------------------------------------------------------


@dataclass
class _Response:
    url: str
    status: int
    content_type: str
    charset: Optional[str]
    body: bytes


def _new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # ignore proxy env vars and ~/.netrc credentials
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"})
    return session


def _safe_get(
    url: str,
    session: requests.Session,
    resolver: Resolver,
    timeout: float,
    max_bytes: int,
) -> _Response:
    deadline = time.monotonic() + timeout * 2
    for _hop in range(MAX_REDIRECTS + 1):
        validate_public_url(url, resolver)
        try:
            resp = session.get(url, allow_redirects=False, stream=True, timeout=(timeout, timeout))
        except requests.Timeout as exc:
            raise UrlImportError(FailureReason.TIMEOUT, "The site took too long to respond.") from exc
        except requests.RequestException as exc:
            logger.info("event=url_fetch_failed error_type=%s", type(exc).__name__)
            raise UrlImportError(FailureReason.NETWORK, "The page could not be reached.") from exc
        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise UrlImportError(FailureReason.HTTP_ERROR, "The site sent an invalid redirect.")
                url = urljoin(url, location)
                continue
            declared = resp.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise UrlImportError(FailureReason.TOO_LARGE, "The page is too large to import.")
            chunks, size = [], 0
            try:
                for chunk in resp.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UrlImportError(FailureReason.TOO_LARGE, "The page is too large to import.")
                    if time.monotonic() > deadline:
                        raise UrlImportError(FailureReason.TIMEOUT, "The site took too long to respond.")
                    chunks.append(chunk)
            except requests.RequestException as exc:
                raise UrlImportError(FailureReason.NETWORK, "The page download was interrupted.") from exc
            ctype = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([\w.-]+)", ctype, re.I)
            return _Response(url, resp.status_code, ctype.split(";")[0].strip().lower(),
                             m.group(1) if m else None, b"".join(chunks))
        finally:
            resp.close()
    raise UrlImportError(FailureReason.HTTP_ERROR, "The page redirected too many times.")


def _decode(resp: _Response) -> str:
    charset = resp.charset
    if not charset:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w.-]+)", resp.body[:4096], re.I)
        charset = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return resp.body.decode(charset, errors="replace")
    except LookupError:
        return resp.body.decode("utf-8", errors="replace")


def check_robots(url: str, session: requests.Session, resolver: Resolver, timeout: float) -> None:
    """Raise ``UrlImportError`` unless the site's robots.txt permits fetching ``url``.

    A missing robots.txt (404 etc.) means allowed. 401/403 means the site refuses
    automated clients outright (urllib.robotparser treats it as disallow-all). If
    robots.txt cannot be checked (5xx, network), we err on the side of not fetching.
    """
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    unverifiable = UrlImportError(
        FailureReason.DISALLOWED, "The site's access rules (robots.txt) could not be checked, so the page was not fetched."
    )
    try:
        resp = _safe_get(robots_url, session, resolver, timeout, MAX_ROBOTS_BYTES)
    except UrlImportError as exc:
        if exc.reason is FailureReason.UNSAFE_URL:
            raise
        raise unverifiable from exc
    if resp.status in _BLOCKED_STATUSES:
        raise UrlImportError(FailureReason.BLOCKED, "This site refuses automated access. The app does not bypass that.")
    if 400 <= resp.status < 500:
        return
    if resp.status >= 300:
        raise unverifiable
    parser = RobotFileParser()
    parser.parse(_decode(resp).splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise UrlImportError(
            FailureReason.DISALLOWED, "This site does not permit automated access to that page (robots.txt)."
        )


# ---- HTML extraction ------------------------------------------------------------


class _PageParser(HTMLParser):
    """Collect visible text, <title>, and JSON-LD blocks. Scripts/styles are never kept."""

    # Not "head": HTMLParser does not infer a missing </head>, which would hide the whole body.
    _SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object"}
    _BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self.json_ld: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_json_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
            self._in_json_ld, self._buf = True, []
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")
        if tag == "li" and not self._skip_depth:
            self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buf))
            self._in_json_ld = False
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buf.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return normalize_jd_text("".join(self.parts))


def html_to_text(html: str) -> str:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    return parser.text


def _iter_json_objects(node: Any) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _iter_json_objects(node[key])
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_objects(item)


def _is_job_posting(obj: dict) -> bool:
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return "JobPosting" in types


def _str(value: Any) -> str:
    if isinstance(value, dict):
        return _str(value.get("name", ""))
    if isinstance(value, list):
        return ", ".join(s for s in (_str(v) for v in value) if s)
    return str(value).strip() if value is not None else ""


def _location(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    places = places if isinstance(places, list) else [places]
    names = []
    for place in places:
        address = place.get("address", {}) if isinstance(place, dict) else {}
        if isinstance(address, dict):
            bits = [_str(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
            name = ", ".join(dict.fromkeys(b for b in bits if b))
        else:
            name = _str(address)
        if name:
            names.append(name)
    if "TELECOMMUTE" in _str(posting.get("jobLocationType")).upper():
        names.append("Remote")
    return "; ".join(dict.fromkeys(names))


def extract_job_posting(json_ld_blocks: list[str]) -> Optional[dict[str, str]]:
    """Return title/company/location/description from the first schema.org JobPosting, if any."""
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        for obj in _iter_json_objects(data):
            if _is_job_posting(obj):
                return {
                    "title": _str(obj.get("title")),
                    "company": _str(obj.get("hiringOrganization")),
                    "location": _location(obj),
                    "description": html_to_text(_str(obj.get("description"))),
                }
    return None


# ---- orchestration --------------------------------------------------------------


def fetch_job_from_url(
    url: str,
    *,
    session: Optional[requests.Session] = None,
    resolver: Resolver = system_resolver,
    timeout: float = DEFAULT_TIMEOUT,
    honour_robots: bool = True,
) -> UrlImportResult:
    """Fetch one job page and extract its JD text. Raises ``UrlImportError`` with a fallback hint."""
    url = (url or "").strip()
    if not url:
        raise UrlImportError(FailureReason.UNSAFE_URL, "Enter a URL.")
    if "://" not in url:
        url = f"https://{url}"
    validate_public_url(url, resolver)
    own_session = session is None
    session = session or _new_session()
    try:
        if honour_robots:
            check_robots(url, session, resolver, timeout)
        resp = _safe_get(url, session, resolver, timeout, MAX_RESPONSE_BYTES)
    finally:
        if own_session:
            session.close()

    platform = infer_platform(resp.url)
    logger.info("event=url_fetched status=%d platform=%s bytes=%d", resp.status, platform.value, len(resp.body))
    if resp.status in _BLOCKED_STATUSES or _LOGIN_PATH_RE.search(urlsplit(resp.url).path):
        raise UrlImportError(
            FailureReason.BLOCKED,
            "The site requires sign-in or a human check for this page. The app does not bypass these.",
        )
    if resp.status == 404 or resp.status == 410:
        raise UrlImportError(FailureReason.HTTP_ERROR, "The job page was not found. It may have been removed.")
    if resp.status >= 400:
        raise UrlImportError(FailureReason.HTTP_ERROR, f"The site returned an error (HTTP {resp.status}).")
    if not resp.content_type.startswith(_HTML_TYPES):
        raise UrlImportError(
            FailureReason.UNSUPPORTED_CONTENT,
            f"The URL returned {resp.content_type or 'unknown content'}, not a web page.",
        )

    html = _decode(resp)
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    posting = extract_job_posting(parser.json_ld)
    if posting and len(posting["description"]) >= MIN_JD_CHARS:
        return UrlImportResult(
            text=posting["description"], final_url=resp.url, platform=platform, method="structured",
            title=posting["title"], company=posting["company"], location=posting["location"],
            notes=["Extracted from the page's structured job data. Review it against the original posting."],
        )

    text = parser.text
    lowered = text.casefold()
    if len(text) < 2000 and any(marker in lowered for marker in _BLOCK_MARKERS):
        raise UrlImportError(
            FailureReason.BLOCKED,
            "The page asked for sign-in, JavaScript, or a human check. The app does not bypass these.",
        )
    if len(text) < MIN_JD_CHARS:
        raise UrlImportError(
            FailureReason.INCOMPLETE,
            "Too little text was found on the page (it may load the job with JavaScript).",
        )
    return UrlImportResult(
        text=text, final_url=resp.url, platform=platform, method="page_text",
        title=(posting or {}).get("title") or normalize_jd_text(parser.title),
        company=(posting or {}).get("company", ""), location=(posting or {}).get("location", ""),
        notes=[
            "Extracted from general page text, which may include menus or unrelated content, "
            "or miss parts of the JD. Trim and check it before saving."
        ],
    )
