# Frontend Integration Report

**Date:** 2026-10-16 · **Branch:** `milestone-2-job-import` (HEAD `d5191f3`) · **Status:** Option A1 (FastAPI adapter) was approved and is implemented: see §8. Sections 1–7 record the reconnaissance as written before approval.

This report records what the existing Resume Optimizer backend can actually do, how each Streamlit workflow reaches it, and what a separate React frontend would need. Every capability below was traced in source; nothing is assumed.

---

## 1. Headline finding: there is no HTTP API to integrate with

The application is a **single-process Streamlit app**. Every Streamlit page imports the service and persistence modules and calls them **in-process** (`src/ui/pages/*.py` → `src/services/*`, `src/persistence/*`). No REST, GraphQL, or RPC layer exists, and no web framework (FastAPI/Flask) is a dependency (`requirements.txt`).

The only HTTP server in the repo is **`src/extension_receiver.py`** (`python -m src.extension_receiver`), and it **can't serve a web frontend**:

| Route | Purpose | Why a React app can't use it |
|---|---|---|
| `GET /health` | Liveness check for the browser extension | Returns only `{ok, app, enabled}` |
| `POST /capture` | Drops a captured JD into the review inbox | Needs the extension pairing token. **It deliberately refuses any request with a web-page `Origin`** (only `chrome-extension://` / `moz-extension://` or no origin are allowed), as protection against hostile web pages. |

The approved Assisted Apply design (`docs/superpowers/specs/2026-10-11-assisted-apply-design.md` §2) adds `/pair/hello` and `/apply/*` routes to that same receiver. They are scoped to the extension too, use the same origin guard, and are **not implemented yet**.

**Consequence.** If I built a React frontend now, it would have two options: call endpoints that don't exist (invented contracts), or re-implement the Python logic in TypeScript (duplicated business logic). The brief forbids both, and so does CLAUDE.md (truthfulness, deterministic Python checks). **A new HTTP adapter layer in the Python backend is a precondition** for any working React feature. That's a backend change, so per the brief I've stopped here for approval. §6 proposes the smallest version of that change.

---

## 2. Repository and runtime facts

| Item | Verified value |
|---|---|
| Entry point | `streamlit run app.py` (9 pages via `st.navigation`) |
| Python | 3.13.1 in `.venv` (project targets 3.11+) |
| Installed web pieces | `starlette 1.7.0`, `uvicorn 0.54.0` (both pulled in transitively by Streamlit 1.64); **FastAPI not installed** |
| Node / npm | v24.13.1 / 11.8.0 (enough for Vite + React) |
| Persistence | `data/profile/master_profile.json` + immutable `history/master_profile_vN.json`; `data/profile/role_profiles.json`; `data/jobs.sqlite3` (jobs, analyses, match reports, resume versions, exports, captures); `data/settings.json`; exported files under `output/` |
| Config | `src/config.py`: env var > `settings.json` > default; `.env.example` present |
| Auth / sessions | **None.** A local single-user app. Streamlit session state is UI-only (`src/ui/state.py`). |
| CORS | Not applicable today; the receiver only allows extension origins. |
| Python tests | `pytest -q`: all pass (baseline run 2026-10-16) |
| Git state | Clean tracked tree. Untracked: `docs/superpowers/plans/`, `docs/superpowers/spikes/` (Assisted Apply work; **left untouched**) |

---

## 3. Feature-by-feature capability map

Legend: **In-process** = a real, tested Python function that Streamlit calls directly; it would need an HTTP route to reach React. **Missing** = the feature doesn't exist in the backend at all.

### 3.1 Master Profile — `ProfileStore`, `profile_service`

| Capability | Backend | Notes |
|---|---|---|
| Load current profile | `ProfileStore.load()` | Returns `MasterProfile` or `None` |
| Save (any edit) | `ProfileStore.save_new_version(profile)` | **Whole-document save.** It creates immutable version N+1 and clears `confirmed_at`. A no-op if content is unchanged. **No optimistic-concurrency check** (last write wins). |
| Confirm reviewed profile | `ProfileStore.mark_confirmed()` | |
| Version history / restore | `list_versions()`, `load_version(n)` → restored by saving as a new version | |
| Import / export JSON | `parse_profile_json(bytes)`, `export_profile_json(profile)` | Strict schema (`extra="forbid"`) |
| Load fictional sample | `load_sample_profile()` | `data/samples/sample_profile.json`, `is_sample=True` |
| Prune dangling evidence on delete | `prune_removed_evidence(old, new)` | Used when entries are removed |
| Warnings (unverified numbers, etc.) | `profile_warnings(profile)` | Drives dashboard "pending review" |
| Delete all profile data | `ProfileStore.delete_all()` | |
| **Resume upload → parsed draft profile (PDF/DOCX)** | **Missing** | `extract_text_from_file` exists, but only for JD import. No resume-to-profile parser exists. |

Sections in the schema (`src/schemas/profile.py`): contact (+links), headline, summary, experience (+bullets with `skills`, `source_note`, `verified_metrics`), projects, skills, education, certifications, achievements. Lists are ordered, so reordering means saving a new order.

### 3.2 Skills Library

Skills aren't a separate store. They live inside `MasterProfile.skills` and are edited by saving a new profile version.

- Fields: `id`, `name`, `category`, `aliases[]`, `evidence_ids[]`.
- `SkillCategory` (exact values): `language`, `framework`, `tool`, `platform`, `concept`, `soft`, `other`.
- Taxonomy and related-term logic: `skill_taxonomy.lookup`, `related_terms`, `profile_terms` (in-process).
- Duplicate detection: not a standalone service function. The schema/model validators enforce ID integrity. Name duplicates would need checking in the adapter (or on the client, as UX only).

### 3.3 Job descriptions — `jd_import_service`, `url_import`, `JobStore`

| Capability | Backend |
|---|---|
| Paste text → validated draft | `check_jd_text`, `build_job(...)` |
| Upload file (`.txt/.md/.pdf/.docx`) → text | `extract_text_from_file(filename, bytes)` |
| URL import (best effort, robots.txt, SSRF guards, no auth bypass) | `fetch_job_from_url(url, timeout=...)` raises `UrlImportError(reason, hint)`. Disabled when `local_only` or `url_import_enabled=false`. |
| Duplicate detection / merge on import | `find_duplicates(candidate, existing)`, `merge_import_into(existing, incoming)` |
| CRUD | `JobStore.add/update/get/list/delete/delete_all` |
| Extension inbox (review captured JDs) | `JobStore.list_captures/delete_capture` |
| Analysis (deterministic parser) | `analyze_job(job, profile)` → `ParseResult`; `update_analysis`, `apply_requirement_edits`, `is_stale`; persisted with `JobStore.save_analysis/get_analysis` |

Requirement enums: category `skill|experience|education|certification|responsibility|qualification|domain`; importance `required|preferred|unspecified`; work arrangement `onsite|hybrid|remote|unspecified`.

### 3.4 Match report / evaluation — `matching_service`, `match_report_service`

| Capability | Backend |
|---|---|
| Build report | `build_match_report(...)`, persisted with `JobStore.save_match_report` |
| Per-requirement status | `supported`, `partial`, or `not_documented`, plus `match_type`, `evidence_ids`, `explanation`, `score` (informational) |
| User override / clear | `set_override`, `clear_override` |
| Summary per group, gaps, staleness | `summarize`, `gaps`, `stale_reasons` |
| Role-profile and project recommendations | `recommend_role_profiles`, `recommend_projects` |
| **ATS score** | **Not computed. Not to be shown.** The only numbers are per-group coverage (`GroupStats.coverage`) and matcher `score`. Both are internal and must be labelled as estimates. |
| Resume validation report | `validate_resume(...)` → `ValidationReport` (claim checks, length estimate); `change_summary(version, profile)` |
| Export validation | `ExportRecord.checks` (text extraction, page count, etc.) |

### 3.5 Resume tailoring and versions — `resume_service`, `JobStore`, `export_service`

| Capability | Backend | Notes |
|---|---|---|
| Generate draft | `generate_version(job, profile, analysis, report, role=, target_pages=, provider=)` | Deterministic by default. An optional LLM rewrite runs only when configured and the user has consented. Falls back to the deterministic draft on AI failure. |
| AI request preview (what will be sent) | `resume_rewriter.build_request(...)` | Needed for the consent UI |
| Edit → new child version | `apply_user_edits(version, summary_text=, bullets=)` | Header facts are not editable. Edits are checked by the claim checker. |
| List / get versions | `JobStore.list_resume_versions(job_id)`, `get_resume_version(id)` | |
| Approve | `JobStore.approve_resume_version(id, note)` | Statuses are **draft** (no `approved_at`) and **approved**; **exported** is derived from `get_export`. |
| Export DOCX + PDF | `export_version(version, output_dir=, page_size=, style=)` → `ExportRecord` with file paths and checks | Approved versions only |
| **Delete a resume version** | **Missing** | Only deleted with its job |
| **Duplicate a version** | **Missing** as a separate operation | The equivalent is "edit → new child version" |
| **Compare two versions** | **Missing** | `change_summary` compares a version to the *profile*, not to another version |

### 3.6 Role profiles (Resume Library)

`create_role_profile`, `update_role_profile`, `rename_role_profile`, `duplicate_role_profile`, `delete_role_profile`, and `ProfileStore.load_roles/save_roles` (all in-process).

### 3.7 Application tracker — `tracker_service`

`build_rows`, `filter_rows`, `update_application(store, job, status=, applied_on=, follow_up_on=, notes=, resume_version_id=)`, `follow_ups_due`, `to_csv`, `duplicate_pairs`, `merge_loss`, `merge_jobs`, `delete_job`. Statuses (exact): `saved`, `applied`, `interviewing`, `offer`, `rejected`, `withdrawn`, `archived`. The app **never submits applications**.

### 3.8 Settings and data

`get_settings()` (with per-setting `sources`: env/file/default/local-only), `SettingsStore.save(changes)`, `provider_status(settings)` (reports whether a key is *detected*, never its value), extension pairing token (`get_or_create_token`, `regenerate_token`), `export_all_data` (zip), `delete_everything`. Settings that come from an environment variable override the file and can't be changed in the UI.

### 3.9 Dashboard data

The Streamlit dashboard derives everything from: profile load + `profile_warnings`, role profiles, `JobStore.list()`, `resume_counts()`, `export_counts()`, and `follow_ups_due`. There's **no activity log**, so "recent activity" can only be built from `updated_at`/`created_at` timestamps on existing records.

---

## 4. Integration gaps summary

| # | Gap | Severity | Resolution |
|---|---|---|---|
| G1 | No HTTP API for any feature | **Blocking** | New local adapter (§6). Needs approval. |
| G2 | No concurrency control on profile save while Streamlit and React run together | High | The adapter requires `expected_profile_version` and returns 409 on mismatch. Implemented in the adapter only; `ProfileStore` is unchanged. |
| G3 | A localhost API is reachable by any web page the user visits (CSRF / DNS rebinding) | High | Bind to 127.0.0.1, enforce `Host`, use an exact `Origin` allowlist, add a per-launch session token. Reuse the receiver's proven pattern. |
| G4 | Resume upload → profile parsing | Feature missing | The React UI won't offer it. Manual entry and JSON import remain. |
| G5 | Resume version delete / duplicate / compare | Feature missing | Not shown. "Edit → new version" is offered instead. |
| G6 | ATS score | Not a real feature | Never shown. Coverage is labelled "match estimate" with its definition. |
| G7 | Activity feed | No backing data | Derived "recently updated" lists from timestamps only |
| G8 | File downloads come from `output/` paths | Medium | The adapter streams files by `version_id` and never accepts a client path |

---

## 5. Options

**Option A — Local HTTP adapter (recommended).** Add a **new** package `src/api/` (e.g. `src/api/app.py`, routers, and response DTOs that reuse existing Pydantic models). It calls existing services exactly as the Streamlit pages do. **No existing Python file is modified.** The only shared-file change is one line in `requirements.txt` (and possibly a doc section in `README.md`). New pytest tests go in `tests/test_api_*.py`. Run with `python -m src.api` on `127.0.0.1:8000`; Streamlit keeps working independently.

- A1: FastAPI (+1 dependency, ~small; gives typed routes and an OpenAPI schema from which the TS types can be **generated**, avoiding hand-copied contracts).
- A2: Starlette only (already installed via Streamlit, so 0 new top-level packages, but it would become a *direct* dependency to pin; more hand-written validation; no OpenAPI).

**Option B — Extend `extension_receiver.py`.** Not recommended. It mixes a hardened, extension-only surface with a broad CRUD API, it conflicts with the approved Assisted Apply route plan, and it requires modifying an existing file.

**Option C — Don't build the React app.** Keep Streamlit as the only UI.

---

## 6. Proposed adapter contract (draft, for approval; nothing implemented)

All routes are under `/api/v1` and return JSON. Errors are `{error: {code, message, details?}}`. Models are the existing Pydantic schemas serialized as-is.

```
GET    /health                                 → {ok, version}
GET    /settings                               → Settings view (no secrets) + provider_status + sources
PATCH  /settings                               → SettingsStore.save (env-locked keys rejected with 409)

GET    /profile                                → MasterProfile | 404
PUT    /profile   {profile, expected_version}  → save_new_version (409 on version mismatch)
POST   /profile/confirm                        → mark_confirmed
GET    /profile/warnings                       → profile_warnings
GET    /profile/versions                       → [int]
POST   /profile/versions/{n}/restore           → save_new_version(load_version(n))
POST   /profile/import (multipart JSON)        → parsed MasterProfile preview (not saved)
GET    /profile/export                         → JSON download
POST   /profile/sample                         → loads the fictional sample (only if no profile exists)

GET/POST/PATCH/DELETE /role-profiles[/{id}]    → role profile service functions; POST /{id}/duplicate

POST   /jobs/draft/text   {text, ...meta}      → build_job preview + find_duplicates
POST   /jobs/draft/file   (multipart)          → extract_text_from_file → same
POST   /jobs/draft/url    {url}                → fetch_job_from_url (422 with reason+hint on failure)
GET    /jobs | POST /jobs | GET/PATCH/DELETE /jobs/{id}
POST   /jobs/{id}/merge-import                 → merge_import_into
GET    /captures | DELETE /captures/{id}

GET    /jobs/{id}/analysis | POST /jobs/{id}/analysis (analyze) | PUT (review edits) | POST .../confirm
GET    /jobs/{id}/match | POST /jobs/{id}/match (run) | PUT/DELETE /jobs/{id}/match/overrides/{req_id}
GET    /jobs/{id}/match/summary                → summarize, gaps, stale_reasons, recommendations

GET    /jobs/{id}/resumes
POST   /jobs/{id}/resumes        {role_profile_id?, target_pages, use_ai, consent}   → generate_version
POST   /jobs/{id}/resumes/ai-preview                                                 → build_request (what would be sent)
GET    /resumes/{vid} | GET /resumes/{vid}/validation | GET /resumes/{vid}/changes
POST   /resumes/{vid}/edits      {summary_text?, bullets[]}   → apply_user_edits (new version)
POST   /resumes/{vid}/approve    {note}
POST   /resumes/{vid}/export     {page_size, template}         → ExportRecord
GET    /resumes/{vid}/download/{docx|pdf}                       → file stream (path resolved server-side)

GET    /tracker?status=&q=&follow_up_due=      → build_rows + filter_rows
PATCH  /tracker/{job_id}                       → update_application
GET    /tracker/export.csv | GET /tracker/duplicates | POST /tracker/merge
GET    /dashboard                              → aggregates listed in §3.9
```

Not included: extension pairing-token display (it stays in Streamlit Settings, where it's shown today), "delete everything", and the full-data zip export. Each is destructive or sensitive, and they can be added later if wanted.

**Security baseline for the adapter:** bind 127.0.0.1 only; `Host` must be `127.0.0.1:<port>`/`localhost:<port>`; CORS limited to the configured frontend origin (dev default `http://localhost:5173`); a random per-launch session token printed to the console and required in a header; request-size limits; logs record event names only, never profile/JD content (matching current logging rules); LLM calls only when `consent=true` is sent with the request.

---

## 7. Risks

- **Two UIs over one data store.** SQLite handles concurrent writers, but whole-profile saves don't, which is why G2 requires version checks.
- **Generation latency.** An LLM rewrite can take up to `llm_timeout_seconds` (≤600 s). The React UI needs a long-running request state and must handle cancellation.
- **Contract drift.** Hand-written TS types will drift from Pydantic. FastAPI's OpenAPI output plus a type generator (`openapi-typescript`, dev-only) avoids it. That's a reason to prefer A1.
- **Scope.** The full feature set across 8+ screens is large. The plan (`IMPLEMENTATION_PLAN.md`) builds the core tailoring workflow end to end first.

---

## 8. Outcome (after approval)

**Built:** `src/api/` (new files only), with 41 routes under `/api/v1` matching §6, plus `tests/test_api.py`. The only edits to existing files are two lines in `requirements.txt` (`fastapi`, and `uvicorn`, already installed through Streamlit) and one section in `README.md`. `python-multipart` wasn't needed: uploads are sent as raw request bodies.

Changes from the §6 draft:
- `PUT /profile` validates each field first, prunes links to deleted evidence, and only then runs the full cross-reference validation. That's the order the Streamlit page uses; otherwise you couldn't delete an item that a skill links to.
- Not added: the extension pairing token, full data export (.zip), "delete everything", and "delete all jobs". These stay in Streamlit.

**Verified:**
- `pytest`: 383 passed (354 existing + 29 API).
- Vitest: 47 passed.
- Playwright: 2 passed against the real API. The workflow runs from the sample profile through import, analysis, match, generate, approve and export (backend export checks: 0 failed), then download, tracker and dashboard.

### Backend issue found: approval needed to fix

`JobStore._connect` (`src/persistence/job_store.py`) applies schema migrations without holding a write lock. When two connections open a **new (or older-schema)** database at once, both run the same `ALTER TABLE` and one fails with `duplicate column name: applied_on`. It reproduced in 20 of 20 trials with 6 threads. This predates the frontend: the extension receiver is also multi-threaded.

- **Mitigation already in the adapter (no backend change):** `src/api/deps.job_store()` runs the first open per database once, under a lock. This is covered by `test_concurrent_first_requests_on_a_new_database`.
- **Remaining risk:** Streamlit and the API (or the extension receiver) opening a brand-new database at the same instant.
- **Proposed fix (not applied):** in `_connect`, take the write lock with `BEGIN IMMEDIATE` before reading `PRAGMA user_version`, re-read the version inside the lock, and apply the migrations in that same transaction (replacing `executescript`, which commits implicitly, with per-statement `execute`).
