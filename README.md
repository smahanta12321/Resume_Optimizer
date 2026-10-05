# AI Resume Optimizer

A local-first assistant that tailors a **truthful**, ATS-readable resume to a job description using only facts from your verified master profile. It never applies to jobs, contacts recruiters, or promises ATS outcomes.

See [SPECIFICATION.md](SPECIFICATION.md) for the full product spec and [CLAUDE.md](CLAUDE.md) for engineering rules.

## Status

| Milestone | Scope | State |
|---|---|---|
| 1 | Schemas, master profile management, role profiles, sample data | **Done** |
| 2 | Job import (paste / file / URL) + SQLite + dedup | **Done** |
| 3 | JD parsing and review | **Done** |
| 4 | Evidence matching + match report | Planned |
| 5 | LLM provider, drafting, approval | Planned |
| 6 | DOCX/PDF export + validation | Planned |
| 7 | Tracker, settings, data export/deletion | Planned |

## Setup

Requires Python 3.11+ (developed on 3.13). Use a virtual environment. Do not install into a shared global Python.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # optional; defaults work without it
streamlit run app.py
```

Run the tests:

```bash
python -m pytest
```

## Using Milestone 1

For a full step-by-step guide, see the [User Manual](docs/USER_MANUAL.md).

1. **Master Profile**: create a profile from scratch, import a JSON file, or load the **fictional sample** ([data/samples/sample_profile.json](data/samples/sample_profile.json)) to explore.
2. Edit contact, experience, projects (with bullets), skills, education, certifications, and achievements. Every item gets a stable evidence ID (for example `exp-…` or `bul-…`).
3. Review the **quality notes**, then click **Confirm profile**. Any later edit creates a new version and clears the confirmation.
4. **Resume Library**: create role profiles such as "ML Engineer". Each is an ordered selection of existing evidence plus a 1- or 2-page target. Role profiles never add facts.

## Using Milestone 2: Job Import

Open **Job Import** in the sidebar.

1. **Bring in a JD** using one of three tabs:
   - **Paste text**: always available, and the most reliable route.
   - **Upload file**: text-based `.txt`, `.md`, `.pdf`, or `.docx`, up to 5 MB. Scanned PDFs contain no selectable text, so paste those instead.
   - **From URL**: a best-effort fetch of one public page (see the rules below). When it fails, the app says why and asks you to paste.
2. **Review**: check or fill in title, company, location, platform, and source URL. Trim any unrelated page text from the description, then **Save job**.
3. **Duplicates**: if the job matches one you already saved, choose **Update** (new text and source; your status and notes are kept), **Save as a separate job**, or go back.
4. **Saved jobs**: filter by status, edit details and notes, or delete one job or all of them.

### URL import rules

- Only `http`/`https` URLs on ports 80/443. Each host, including every redirect hop, must resolve to public IP addresses only. Local and private-network addresses are refused.
- 10 s timeout (`RESUME_OPTIMIZER_URL_TIMEOUT`), 2 MB response cap, at most 3 redirects.
- The site's **robots.txt is honoured**. Sign-in pages, CAPTCHAs, rate limits, and bot checks are never bypassed. No cookies, credentials, or browser impersonation are used.
- Pages that publish schema.org `JobPosting` data are extracted cleanly. Other pages fall back to visible page text, flagged for you to trim.
- **In practice, LinkedIn's robots.txt disallows automated access and Naukri refuses non-browser clients, so for those two sites, paste the JD.** Company career pages often work.
- Set `RESUME_OPTIMIZER_URL_IMPORT=off` to disable URL import entirely.

### Duplicate detection

A new job is flagged as a likely duplicate when any one of these holds:
- **Same canonical URL.** LinkedIn and Naukri URLs reduce to their job ID. Tracking parameters and fragments are ignored.
- **Identical description text**, ignoring case and punctuation.
- **Same company, title, and location**, with at least 85% similar text.

You always decide what happens. Nothing is merged automatically.

## Using Milestone 3: JD Analysis

Open **JD Analysis**, pick a saved job, and click **Analyze job description**. A deterministic parser (`rules-v1`, no AI service, no network) produces a draft with:

- **Job details**: title, company and location (blank fields are prefilled from the JD when possible; your entries are never overwritten), work arrangement, and the overall experience range.
- **Requirements**, each with a category (skill, experience, education, certification, responsibility, qualification, domain), an importance (required, preferred, unspecified), a normalized term, the JD excerpt it came from, a confidence score, and an origin (parser or user).

Correct anything in the form and table, click **Save review**, then **Confirm analysis**. Any later edit clears the confirmation. If the job's JD text changes, the page flags the analysis as out of date and blocks confirmation until you re-analyze.

How the parser works:
- It recognizes section headings used by LinkedIn, Naukri and common career sites (responsibilities, requirements, nice to have, education, key skills). "About the company" text is used only for domain terms. Benefits, equal-opportunity and "how to apply" text is ignored.
- Importance comes from the section, refined per sentence by cues such as "must" or "is a plus".
- Skills are recognized from a curated vocabulary ([src/services/skill_taxonomy.py](src/services/skill_taxonomy.py)) plus your profile's skill names and aliases. Recognizing a term **only** describes the job. It never marks a skill as yours. Related terms (e.g. Spark vs PySpark, Agile vs Scrum) are kept separate, and ambiguous names (Go, R, C, React, Excel) only match in clear list contexts.
- The overall experience range is set only from an explicit statement. If several different ranges appear, it is left blank with a warning. Skill-specific experience ("4+ years of Python") is never used as the overall range.
- Text that looks like instructions to an AI ("ignore previous instructions…") is flagged and treated as plain text.

### Profile rules enforced by the app

- IDs are unique across the profile. Skills may only link to evidence IDs that exist.
- Dates use `YYYY-MM`. An empty end date means current. End dates cannot precede start dates.
- Unknown JSON fields are rejected, so typos surface instead of being silently dropped.
- A bullet that contains a number without a matching **verified metric** is flagged, which helps keep unverified numbers out of resumes.
- Skill **aliases** are exact alternate names only (for example `k8s` for Kubernetes), not related concepts.
- Deleting an item removes skill links to it and tells you which skills lost evidence.

## Data and privacy

- All data is stored locally under `data/` (override with `RESUME_OPTIMIZER_DATA_DIR`):
  - `data/profile/master_profile.json`: the current version
  - `data/profile/history/master_profile_vN.json`: write-once snapshot of every version
  - `data/profile/role_profiles.json`: the role-profile library
  - `data/jobs.sqlite3`: imported jobs (extracted JD text, URL, and your metadata; never raw page HTML) and their JD analyses. The database schema upgrades automatically. Deleting a job deletes its analysis.
- `data/` (except the fictional samples) and `output/` are git-ignored.
- The only outbound network request is a **URL import you trigger**, which contacts that job site (plus its robots.txt) and nothing else. No profile data is sent. When LLM support arrives (Milestone 5), it will be opt-in and clearly disclosed.
- Imported JD text is treated as untrusted data. It is stored and displayed, never executed or followed as instructions.
- Logs record events and version numbers only, never profile content or secrets.
- **Import / export → Delete all profile data** permanently removes the profile, all versions, and role profiles.

## Project layout

```text
app.py                     Streamlit entry point (navigation)
src/config.py              env-based settings, logging
src/schemas/profile.py     Pydantic models: MasterProfile, evidence items, RoleProfile
src/schemas/job.py         Pydantic Job model (source, status, JD text)
src/schemas/analysis.py    Pydantic JDAnalysis / Requirement models
src/persistence/profile_store.py   versioned JSON storage
src/persistence/job_store.py       SQLite job storage
src/services/profile_service.py    import/export, quality checks, role-profile ops
src/services/jd_import_service.py  JD text cleanup, file extraction, URL canonicalization, dedup
src/services/url_import.py         SSRF-safe, robots-aware single-page fetch + extraction
src/services/skill_taxonomy.py     curated skill/domain vocabulary for term recognition
src/services/jd_parser.py          deterministic JD parser (rules-v1)
src/services/jd_analysis_service.py   analysis workflow: run, edit, staleness, confirmation
src/ui/                    Streamlit pages and helpers
data/samples/              fictional sample data (safe to commit)
tests/                     pytest suite (fictional data only)
prompts/, templates/       reserved for later milestones
```

## Known limitations (Milestone 3)

- The rule-based parser is a first draft. Unusual layouts, headings it doesn't know, or skills missing from the vocabulary need manual correction. Unknown skills are still captured from Naukri-style "Key Skills" lists, at lower confidence.
- Skills mentioned only in free text are recognized only if they're in the vocabulary or your profile. Add missing ones in the requirements table.
- Re-analyzing replaces your edits (the page asks you to confirm first). Requirement IDs change on re-analysis.
- An optional AI-assisted parser is planned with the provider abstraction in Milestone 5. The rule-based parser will stay as the offline default.

## Known limitations (Milestone 2)

- Title, company, and location are prefilled only when a page publishes structured job data. Otherwise, enter them yourself. Requirement extraction arrives in Milestone 3.
- URL import cannot read pages that need sign-in or JavaScript. That includes LinkedIn and Naukri in practice, which are covered by paste.
- The SSRF check and the actual connection resolve DNS separately, so a hostile DNS server could in theory race them (DNS rebinding). This is acceptable for a single-user local tool. Proxy environment variables are ignored during URL import.
- "Update existing" on a duplicate updates the first matching job only.

## Known limitations (Milestone 1)

- One master profile per data directory.
- In the bullet tables, verified metrics are entered as text (`label=value; label=value`). A metric's `source_note` can only be edited through Raw JSON.
- Bullet reordering within an entry is done by editing the table. There are no drag handles yet.
- The UI smoke tests cover forms and buttons. Streamlit's test harness cannot simulate table-cell edits, so those are covered through the conversion helpers in `src/ui/table_convert.py`.
