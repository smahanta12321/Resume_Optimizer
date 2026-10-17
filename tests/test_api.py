"""Local API adapter tests: request guard, error shape, and the full tailoring workflow over HTTP.

Uses FastAPI's TestClient against real stores in a temporary data directory. Fictional data only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.config import TOKEN_HEADER, ApiConfig
from src.persistence.job_store import JobStore
from src.persistence.settings_store import SettingsStore
from src.schemas.capture import Capture
from src.services.profile_service import export_profile_json, load_sample_profile

TOKEN = "test-session-token"
ORIGIN = "http://localhost:5173"
JD = ("Fictional Corp is hiring a Data Engineer (fictional posting).\n\n"
      "Requirements\n• Python, SQL and Docker\n• 2+ years of experience building data pipelines\n\n"
      "Nice to have\n• Kubernetes\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_OPTIMIZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RESUME_OPTIMIZER_OUTPUT_DIR", str(tmp_path / "output"))
    for name in ("RESUME_OPTIMIZER_LOCAL_ONLY", "RESUME_OPTIMIZER_LLM_PROVIDER", "RESUME_OPTIMIZER_LLM_MODEL",
                 "RESUME_OPTIMIZER_URL_IMPORT", "RESUME_OPTIMIZER_TEMPLATE", "RESUME_OPTIMIZER_PAGE_SIZE",
                 "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def raw(env) -> TestClient:
    app = create_app(ApiConfig(port=8000, origins=(ORIGIN,), token=TOKEN), hosts=["testserver"])
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api(raw) -> TestClient:
    raw.headers.update({TOKEN_HEADER: TOKEN})
    return raw


def _error(resp) -> dict:
    return resp.json()["error"]


def _sample(api) -> dict:
    resp = api.post("/api/v1/profile/sample")
    assert resp.status_code == 200, resp.text
    return resp.json()["profile"]


def _job(api, text: str = JD) -> dict:
    draft = api.post("/api/v1/jobs/drafts/text", json={"text": text}).json()
    resp = api.post("/api/v1/jobs", json={"text": draft["text"], "method": draft["method"], "title": "Data Engineer",
                                          "company": "Fictional Corp"})
    assert resp.status_code == 201, resp.text
    return resp.json()["job"]


def _matched_job(api) -> str:
    _sample(api)
    job_id = _job(api)["id"]
    assert api.post(f"/api/v1/jobs/{job_id}/analysis", json={}).status_code == 200
    assert api.post(f"/api/v1/jobs/{job_id}/analysis/confirm").status_code == 200
    assert api.post(f"/api/v1/jobs/{job_id}/match").status_code == 200
    return job_id


# ---- guard ------------------------------------------------------------------------


def test_health_needs_no_token(raw):
    resp = raw.get("/api/v1/health")
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_missing_or_wrong_token_rejected(raw):
    assert _error(raw.get("/api/v1/session"))["code"] == "session_token_invalid"
    resp = raw.get("/api/v1/profile", headers={TOKEN_HEADER: "wrong"})
    assert resp.status_code == 401
    assert raw.get("/api/v1/session", headers={TOKEN_HEADER: TOKEN}).json() == {"ok": True}


def test_foreign_origin_and_bad_host_rejected(api):
    resp = api.get("/api/v1/profile", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403 and _error(resp)["code"] == "origin_not_allowed"
    resp = api.get("/api/v1/profile", headers={"Host": "rebound.example:8000"})
    assert resp.status_code == 403 and _error(resp)["code"] == "bad_host"


def test_cors_for_allowed_origin_including_errors(raw):
    pre = raw.options("/api/v1/profile", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "PUT",
                                                  "Access-Control-Request-Headers": TOKEN_HEADER})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == ORIGIN
    denied = raw.get("/api/v1/profile", headers={"Origin": ORIGIN})
    assert denied.status_code == 401 and denied.headers["access-control-allow-origin"] == ORIGIN


def test_oversized_body_rejected(api):
    resp = api.post("/api/v1/profile/import/preview", content=b"x" * 6_000_001)
    assert resp.status_code == 413


def test_concurrent_first_requests_on_a_new_database(env):
    """Parallel first opens of a fresh job database must not race the schema migration."""
    from concurrent.futures import ThreadPoolExecutor

    from src.api import deps

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: deps.job_store().list(), range(16)))
    assert results == [[]] * 16


# ---- profile ----------------------------------------------------------------------


def test_profile_lifecycle_with_version_check(api):
    assert api.get("/api/v1/profile").json()["profile"] is None
    profile = _sample(api)
    assert profile["profile_version"] == 1 and profile["is_sample"] is True
    assert _error(api.post("/api/v1/profile/sample"))["code"] == "profile_exists"

    profile["headline"] = "Changed headline (fictional)"
    stale = api.put("/api/v1/profile", json={"profile": profile, "expected_version": 99})
    assert stale.status_code == 409 and _error(stale)["details"]["current_version"] == 1
    saved = api.put("/api/v1/profile", json={"profile": profile, "expected_version": 1}).json()
    assert saved["changed"] is True and saved["profile"]["profile_version"] == 2
    assert saved["profile"]["confirmed_at"] is None
    same = api.put("/api/v1/profile", json={"profile": saved["profile"], "expected_version": 2}).json()
    assert same["changed"] is False

    confirmed = api.post("/api/v1/profile/confirm", json={"expected_version": 2}).json()
    assert confirmed["profile"]["confirmed_at"] and confirmed["evidence"]
    assert [v["version"] for v in api.get("/api/v1/profile/versions").json()] == [2, 1]
    restored = api.post("/api/v1/profile/versions/1/restore", json={"expected_version": 2}).json()
    assert restored["profile"]["profile_version"] == 3


def test_invalid_profile_returns_field_errors(api):
    profile = _sample(api)
    profile["skills"].append({"name": "x", "category": "not-a-category"})
    resp = api.put("/api/v1/profile", json={"profile": profile, "expected_version": 1})
    assert resp.status_code == 422 and _error(resp)["details"]


def test_deleting_linked_evidence_prunes_links_with_a_note(api):
    profile = _sample(api)
    linked = next(s for s in profile["skills"] if s["evidence_ids"])
    target = linked["evidence_ids"][0]
    profile["experience"] = [e for e in profile["experience"]
                             if e["id"] != target and all(b["id"] != target for b in e["bullets"])]
    profile["projects"] = [p for p in profile["projects"]
                           if p["id"] != target and all(b["id"] != target for b in p["bullets"])]
    out = api.put("/api/v1/profile", json={"profile": profile, "expected_version": 1})
    assert out.status_code == 200, out.text
    assert out.json()["notes"]
    saved = next(s for s in out.json()["profile"]["skills"] if s["id"] == linked["id"])
    assert target not in saved["evidence_ids"]


def test_unknown_evidence_reference_still_rejected(api):
    profile = _sample(api)
    profile["skills"][0]["evidence_ids"] = ["never-existed"]
    resp = api.put("/api/v1/profile", json={"profile": profile, "expected_version": 1})
    assert resp.status_code == 422 and "never-existed" in _error(resp)["message"]


def test_import_preview_and_export(api):
    raw_json = export_profile_json(load_sample_profile())
    preview = api.post("/api/v1/profile/import/preview", content=raw_json)
    assert preview.status_code == 200 and preview.json()["is_sample"] is True
    bad = api.post("/api/v1/profile/import/preview", content=b"{not json")
    assert bad.status_code == 422 and _error(bad)["code"] == "invalid_profile"
    assert api.get("/api/v1/profile/export").status_code == 409  # no profile yet
    _sample(api)
    exported = api.get("/api/v1/profile/export")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]


def test_delete_profile_requires_typed_confirmation(api):
    _sample(api)
    assert api.request("DELETE", "/api/v1/profile", json={"confirm": "yes"}).status_code == 422
    assert api.request("DELETE", "/api/v1/profile", json={"confirm": "DELETE"}).status_code == 204
    assert api.get("/api/v1/profile").json()["profile"] is None


def test_role_profiles_crud(api):
    profile = _sample(api)
    exp_id = profile["experience"][0]["id"]
    role = api.post("/api/v1/role-profiles", json={"name": "ML Engineer", "evidence_ids": [exp_id]})
    assert role.status_code == 201, role.text
    role_id = role.json()["role"]["id"]
    assert _error(api.post("/api/v1/role-profiles", json={"name": "Bad", "evidence_ids": ["nope"]}))["code"] == \
        "invalid_role_profile"
    dup = api.post(f"/api/v1/role-profiles/{role_id}/duplicate", json={"name": "ML Engineer (copy)"})
    assert dup.status_code == 201
    upd = api.put(f"/api/v1/role-profiles/{role_id}", json={"name": "ML Eng", "target_pages": 2})
    assert upd.json()["role"]["target_pages"] == 2
    assert api.delete(f"/api/v1/role-profiles/{role_id}").status_code == 204
    assert [r["role"]["name"] for r in api.get("/api/v1/role-profiles").json()] == ["ML Engineer (copy)"]


# ---- jobs -------------------------------------------------------------------------


def test_empty_paste_rejected_and_short_paste_noted(api):
    resp = api.post("/api/v1/jobs/drafts/text", json={"text": "   "})
    assert resp.status_code == 422 and _error(resp)["code"] == "import_failed"
    short = api.post("/api/v1/jobs/drafts/text", json={"text": "too short"})
    assert short.status_code == 200 and short.json()["text_notes"]


def test_duplicate_detection_and_merge(api):
    first = _job(api)
    draft = api.post("/api/v1/jobs/drafts/text", json={"text": JD}).json()
    body = {"text": draft["text"], "method": "paste", "title": "Data Engineer", "company": "Fictional Corp"}
    dup = api.post("/api/v1/jobs", json=body)
    assert dup.status_code == 409 and _error(dup)["details"]["duplicates"][0]["job"]["id"] == first["id"]
    merged = api.post("/api/v1/jobs", json={**body, "on_duplicate": "merge", "merge_into_id": first["id"]})
    assert merged.status_code == 201 and merged.json()["merged"] is True
    separate = api.post("/api/v1/jobs", json={**body, "on_duplicate": "separate"})
    assert separate.status_code == 201
    assert len(api.get("/api/v1/jobs").json()) == 2


def test_file_draft_checks_type(api):
    resp = api.post("/api/v1/jobs/drafts/file", params={"filename": "jd.exe"}, content=b"MZ")
    assert resp.status_code == 422 and _error(resp)["code"] == "unsupported_file"
    ok = api.post("/api/v1/jobs/drafts/file", params={"filename": "jd.txt"}, content=JD.encode())
    assert ok.status_code == 200 and ok.json()["method"] == "file" and ok.json()["source_label"] == "jd.txt"


def test_url_import_disabled_in_local_only_mode(api, env):
    SettingsStore(env / "data").save({"local_only": True})
    resp = api.post("/api/v1/jobs/drafts/url", json={"url": "https://example.com/job"})
    assert resp.status_code == 409 and "local-only" in _error(resp)["message"]


def test_capture_inbox_draft_and_save_removes_capture(api, env):
    capture = JobStore(env / "data").add_capture(Capture(text=JD, title="Data Engineer", method="selection"))
    assert [c["id"] for c in api.get("/api/v1/captures").json()] == [capture.id]
    draft = api.post(f"/api/v1/jobs/drafts/capture/{capture.id}").json()
    assert draft["method"] == "extension" and draft["capture_id"] == capture.id and draft["source_notes"]
    api.post("/api/v1/jobs", json={"text": draft["text"], "method": "extension", "capture_id": capture.id})
    assert api.get("/api/v1/captures").json() == []


def test_job_patch_and_delete(api):
    job = _job(api)
    patched = api.patch(f"/api/v1/jobs/{job['id']}", json={"notes": "Recruiter is fictional", "location": "Remote"})
    assert patched.json()["notes"] == "Recruiter is fictional" and patched.json()["location"] == "Remote"
    assert api.delete(f"/api/v1/jobs/{job['id']}").status_code == 204
    assert api.get(f"/api/v1/jobs/{job['id']}").status_code == 404


# ---- analysis and match -----------------------------------------------------------


def test_analysis_review_requires_reconfirmation(api):
    job_id = _job(api)["id"]
    assert api.get(f"/api/v1/jobs/{job_id}/analysis").json()["analysis"] is None
    analysis = api.post(f"/api/v1/jobs/{job_id}/analysis", json={}).json()["analysis"]
    assert analysis["requirements"]
    assert _error(api.post(f"/api/v1/jobs/{job_id}/analysis", json={}))["code"] == "analysis_exists"
    api.post(f"/api/v1/jobs/{job_id}/analysis/confirm")
    rows = [{k: r[k] for k in ("id", "category", "importance", "text", "normalized_term", "min_years", "max_years")}
            for r in analysis["requirements"]]
    rows.append({"category": "skill", "importance": "preferred", "text": "Airflow", "normalized_term": "Airflow"})
    view = api.put(f"/api/v1/jobs/{job_id}/analysis", json={
        "title": "Data Engineer", "company": "Fictional Corp", "location": "", "work_arrangement": "remote",
        "requirements": rows}).json()
    assert view["analysis"]["confirmed_at"] is None
    added = [r for r in view["analysis"]["requirements"] if r["text"] == "Airflow"]
    assert added and added[0]["origin"] == "user"


def test_match_blocked_until_analysis_confirmed(api):
    _sample(api)
    job_id = _job(api)["id"]
    api.post(f"/api/v1/jobs/{job_id}/analysis", json={})
    view = api.get(f"/api/v1/jobs/{job_id}/match").json()
    assert view["blockers"] and view["report"] is None
    assert _error(api.post(f"/api/v1/jobs/{job_id}/match"))["code"] == "match_blocked"


def test_match_report_and_overrides(api):
    job_id = _matched_job(api)
    view = api.get(f"/api/v1/jobs/{job_id}/match").json()
    assert view["rows"] and view["summary"]["formula"] and "ATS" in view["summary"]["formula"]
    req_id = view["rows"][0]["requirement"]["id"]
    bad = api.put(f"/api/v1/jobs/{job_id}/match/overrides/{req_id}",
                  json={"status": "supported", "evidence_ids": ["not-real"]})
    assert bad.status_code == 422 and _error(bad)["code"] == "invalid_override"
    ok = api.put(f"/api/v1/jobs/{job_id}/match/overrides/{req_id}",
                 json={"status": "not_documented", "note": "Checked by hand"}).json()
    row = next(r for r in ok["rows"] if r["requirement"]["id"] == req_id)
    assert row["has_override"] and row["status"] == "not_documented"
    cleared = api.delete(f"/api/v1/jobs/{job_id}/match/overrides/{req_id}").json()
    assert not next(r for r in cleared["rows"] if r["requirement"]["id"] == req_id)["has_override"]


# ---- resumes ----------------------------------------------------------------------


def test_full_tailoring_workflow(api):
    job_id = _matched_job(api)
    options = api.get(f"/api/v1/jobs/{job_id}/tailoring").json()
    assert options["blockers"] == [] and options["provider_status"]["available"] is False

    no_consent = api.post(f"/api/v1/jobs/{job_id}/resumes", json={"use_ai": True})
    assert no_consent.status_code == 422 and _error(no_consent)["code"] == "consent_required"
    no_ai = api.post(f"/api/v1/jobs/{job_id}/resumes", json={"use_ai": True, "consent": True})
    assert no_ai.status_code == 409 and _error(no_ai)["code"] == "ai_unavailable"
    assert api.post(f"/api/v1/jobs/{job_id}/resumes/ai-preview", json={}).status_code == 409

    gen = api.post(f"/api/v1/jobs/{job_id}/resumes", json={"target_pages": 1})
    assert gen.status_code == 201, gen.text
    version = gen.json()["version"]
    assert version["generator"] == "deterministic"
    detail = api.get(f"/api/v1/resumes/{version['id']}").json()
    assert detail["validation"]["ok"] is True and detail["changes"] and detail["export"] is None

    entry = version["content"]["experience"][0]
    bullet = entry["bullets"][0]
    unchanged = api.post(f"/api/v1/resumes/{version['id']}/edits", json={"bullets": [
        {"entry_id": entry["evidence_id"], "evidence_id": bullet["evidence_ids"][0], "text": bullet["text"]}]})
    assert unchanged.json()["changed"] is False
    edited = api.post(f"/api/v1/resumes/{version['id']}/edits", json={"bullets": [
        {"entry_id": entry["evidence_id"], "evidence_id": bullet["evidence_ids"][0], "include": False}]}).json()
    assert edited["changed"] is True and edited["version"]["parent_id"] == version["id"]

    assert api.post(f"/api/v1/resumes/{version['id']}/export").status_code == 409  # not approved
    assert api.post(f"/api/v1/resumes/{version['id']}/approve", json={"confirm": False}).status_code == 422
    approved = api.post(f"/api/v1/resumes/{version['id']}/approve", json={"confirm": True, "note": "ok"})
    assert approved.status_code == 200 and approved.json()["version"]["approved_at"]
    assert _error(api.post(f"/api/v1/resumes/{version['id']}/approve", json={"confirm": True}))["code"] == \
        "already_approved"
    assert api.get(f"/api/v1/resumes/{version['id']}/files/pdf").status_code == 404  # not exported yet

    exported = api.post(f"/api/v1/resumes/{version['id']}/export")
    assert exported.status_code == 200, exported.text
    assert exported.json()["pdf_available"] and exported.json()["docx_available"]
    pdf = api.get(f"/api/v1/resumes/{version['id']}/files/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = api.get(f"/api/v1/resumes/{version['id']}/files/docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"

    versions = api.get("/api/v1/resumes").json()
    assert {v["id"] for v in versions} == {version["id"], edited["version"]["id"]}
    assert next(v for v in versions if v["id"] == version["id"])["exported"] is True

    upd = api.patch(f"/api/v1/tracker/{job_id}", json={"status": "applied", "applied_on": "2026-10-01",
                                                       "resume_version_id": version["id"]})
    assert upd.status_code == 200, upd.text
    tracker = api.get("/api/v1/tracker", params={"status": ["applied"]}).json()
    assert tracker["counts"]["applied"] == 1 and tracker["rows"][0]["exported"] is True
    assert api.get("/api/v1/tracker", params={"search": "nothing-matches"}).json()["rows"] == []
    csv = api.get("/api/v1/tracker/export.csv")
    assert csv.status_code == 200 and "Fictional Corp" in csv.text

    dash = api.get("/api/v1/dashboard").json()
    assert dash["jobs_total"] == 1 and dash["applications_tracked"] == 1 and dash["jobs_exported"] == 1
    assert dash["profile"]["state"] == "ok" and dash["recent_versions"]


def test_generation_blocked_when_match_is_stale(api):
    job_id = _matched_job(api)
    profile = api.get("/api/v1/profile").json()["profile"]
    profile["headline"] = "New fictional headline"
    api.put("/api/v1/profile", json={"profile": profile, "expected_version": profile["profile_version"]})
    options = api.get(f"/api/v1/jobs/{job_id}/tailoring").json()
    assert options["blockers"] and options["stale_reasons"]
    assert _error(api.post(f"/api/v1/jobs/{job_id}/resumes", json={}))["code"] == "generation_blocked"


def test_tracker_rejects_invalid_dates(api):
    job_id = _job(api)["id"]
    resp = api.patch(f"/api/v1/tracker/{job_id}", json={"status": "saved", "applied_on": "2099-01-01"})
    assert resp.status_code == 422


# ---- settings and dashboard -------------------------------------------------------


def test_settings_never_expose_keys_and_respect_env_locks(api, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fictional-secret")
    monkeypatch.setenv("RESUME_OPTIMIZER_TEMPLATE", "compact")
    view = api.get("/api/v1/settings")
    assert "sk-fictional-secret" not in view.text
    body = view.json()
    assert body["keys_detected"]["OPENAI_API_KEY"] is True and "template" in body["locked"]
    locked = api.patch("/api/v1/settings", json={"template": "classic"})
    assert locked.status_code == 409 and _error(locked)["code"] == "setting_locked"
    bad = api.patch("/api/v1/settings", json={"page_size": "A3"})
    assert bad.status_code == 422
    ok = api.patch("/api/v1/settings", json={"page_size": "Letter", "local_only": True}).json()
    assert ok["values"]["page_size"] == "Letter" and ok["sources"]["url_import_enabled"] == "local-only"


def test_dashboard_first_run(api):
    dash = api.get("/api/v1/dashboard").json()
    assert dash["profile"]["state"] == "missing" and dash["jobs_total"] == 0 and dash["recent_versions"] == []
