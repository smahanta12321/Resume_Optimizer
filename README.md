# AI Resume Optimizer

A local-first assistant that tailors a **truthful**, ATS-readable resume to a job description using only facts from your verified master profile. It never applies to jobs, contacts recruiters, or promises ATS outcomes.

See [SPECIFICATION.md](SPECIFICATION.md) for the full product spec and [CLAUDE.md](CLAUDE.md) for engineering rules.

## Status

| Milestone | Scope | State |
|---|---|---|
| 1 | Schemas, master profile management, role profiles, sample data | **Done** |
| 2 | Job import (paste / file / URL) + SQLite + dedup | Planned |
| 3 | JD parsing and review | Planned |
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
- `data/` (except the fictional samples) and `output/` are git-ignored.
- Nothing is sent to any external service yet. When LLM support arrives (Milestone 5), it will be opt-in and clearly disclosed.
- Logs record events and version numbers only, never profile content or secrets.
- **Import / export → Delete all profile data** permanently removes the profile, all versions, and role profiles.

## Project layout

```text
app.py                     Streamlit entry point (navigation)
src/config.py              env-based settings, logging
src/schemas/profile.py     Pydantic models: MasterProfile, evidence items, RoleProfile
src/persistence/profile_store.py   versioned JSON storage
src/services/profile_service.py    import/export, quality checks, role-profile ops
src/ui/                    Streamlit pages and helpers
data/samples/              fictional sample data (safe to commit)
tests/                     pytest suite (fictional data only)
prompts/, templates/       reserved for later milestones
```

## Known limitations (Milestone 1)

- One master profile per data directory.
- In the bullet tables, verified metrics are entered as text (`label=value; label=value`). A metric's `source_note` can only be edited through Raw JSON.
- Bullet reordering within an entry is done by editing the table. There are no drag handles yet.
- The UI smoke tests cover forms and buttons. Streamlit's test harness cannot simulate table-cell edits, so those are covered through the conversion helpers in `src/ui/table_convert.py`.
