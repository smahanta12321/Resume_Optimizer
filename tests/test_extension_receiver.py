"""Local extension receiver tests over real HTTP on an ephemeral port. Fictional data only."""

from __future__ import annotations

import json
import threading

import pytest
import requests

from src.extension_receiver import TOKEN_HEADER, make_server
from src.persistence.extension_token import get_or_create_token, read_token, regenerate_token
from src.persistence.job_store import JobStore
from src.persistence.settings_store import SettingsStore

JD = ("Fictional Corp is hiring a Data Engineer to build pipelines in Python and SQL. "
      "Requirements: 3+ years of experience, Airflow, and cloud data warehouses. " * 2)
EXT = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RESUME_OPTIMIZER_EXTENSION", raising=False)
    monkeypatch.delenv("RESUME_OPTIMIZER_LOCAL_ONLY", raising=False)
    SettingsStore(tmp_path).save({"extension_enabled": True})
    token = get_or_create_token(tmp_path)
    server = make_server(port=0)  # ephemeral port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield {"url": f"http://127.0.0.1:{port}", "token": token, "port": port, "dir": tmp_path}
    server.shutdown()
    server.server_close()


def _post(r, body=None, *, token=None, origin=EXT, ctype="application/json", host=None, raw=None):
    headers = {"Content-Type": ctype}
    if token is not False:
        headers[TOKEN_HEADER] = token or r["token"]
    if origin:
        headers["Origin"] = origin
    if host:
        headers["Host"] = host
    data = raw if raw is not None else json.dumps(body if body is not None else {"text": JD, "method": "selection"})
    return requests.post(r["url"] + "/capture", data=data, headers=headers, timeout=5)


def test_valid_capture_lands_in_inbox(receiver):
    resp = _post(receiver, {"text": JD, "url": "https://careers.example.com/jobs/1", "title": "Data Engineer",
                            "company": "Fictional Corp", "method": "structured", "extension_version": "0.1.0"})
    assert resp.status_code == 201, resp.text
    assert resp.headers["Access-Control-Allow-Origin"] == EXT
    [capture] = JobStore(receiver["dir"]).list_captures()
    assert capture.id == resp.json()["id"] and capture.title == "Data Engineer"
    assert capture.text.startswith("Fictional Corp is hiring")


def test_health(receiver):
    r = requests.get(receiver["url"] + "/health", timeout=5)
    assert r.json() == {"ok": True, "app": "resume-optimizer", "enabled": True}
    assert "Access-Control-Allow-Origin" not in r.headers  # no CORS for non-extension callers


@pytest.mark.parametrize("kwargs,status", [
    ({"token": False}, 401),
    ({"token": "wrong-token"}, 401),
    ({"origin": "https://evil.example"}, 403),
    ({"origin": "http://localhost:8501"}, 403),
    ({"host": "evil.example:80"}, 403),
    ({"ctype": "text/plain"}, 415),
    ({"raw": "{not json"}, 422),
    ({"body": {"text": JD, "unexpected": 1}}, 422),
    ({"body": {"text": "   "}}, 422),
    ({"body": {"text": JD, "url": "javascript:alert(1)"}}, 422),
    ({"raw": "x" * 400_000}, 413),
], ids=["no-token", "bad-token", "web-origin", "app-origin", "rebinding-host", "text-plain", "bad-json",
        "extra-field", "blank-text", "js-url", "too-large"])
def test_rejections_store_nothing(receiver, kwargs, status):
    resp = _post(receiver, **kwargs)
    assert resp.status_code == status, resp.text
    assert resp.json()["ok"] is False
    assert JobStore(receiver["dir"]).list_captures() == []


def test_disabled_in_settings(receiver):
    SettingsStore(receiver["dir"]).save({"extension_enabled": False})
    assert _post(receiver).status_code == 403


def test_regenerated_token_unpairs(receiver):
    old = receiver["token"]
    new = regenerate_token(receiver["dir"])
    assert new != old and read_token(receiver["dir"]) == new
    assert _post(receiver, token=old).status_code == 401
    assert _post(receiver, token=new).status_code == 201


def test_preflight(receiver):
    ok = requests.options(receiver["url"] + "/capture", headers={"Origin": EXT}, timeout=5)
    assert ok.status_code == 204 and TOKEN_HEADER in ok.headers["Access-Control-Allow-Headers"]
    bad = requests.options(receiver["url"] + "/capture", headers={"Origin": "https://evil.example"}, timeout=5)
    assert bad.status_code == 403


def test_unknown_paths(receiver):
    assert requests.get(receiver["url"] + "/", timeout=5).status_code == 404
    assert requests.post(receiver["url"] + "/jobs", timeout=5).status_code == 404


def test_inbox_limit(receiver, monkeypatch):
    monkeypatch.setattr(JobStore, "MAX_PENDING_CAPTURES", 1)
    assert _post(receiver).status_code == 201
    assert _post(receiver).status_code == 503


def test_server_binds_localhost_only(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path))
    server = make_server(port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
