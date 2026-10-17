# Resume Optimizer: React frontend

An optional web interface for the Resume Optimizer. It works on the **same local data** as the Streamlit app, through a small local API (`python -m src.api`). The Streamlit app is unchanged and can run alongside it.

Everything stays on your computer. The frontend never calls an external service. The backend does so only when you ask: for URL import, or for AI wording after you've approved exactly what will be sent.

## Run it

Prerequisites: the project's Python environment (see the root [README](../README.md)) and Node.js 20+.

```bash
# Terminal 1, project root, virtual environment active
pip install -r requirements.txt     # adds fastapi + uvicorn
python -m src.api                   # API on http://127.0.0.1:8000

# Terminal 2
cd frontend-react
npm install
npm run dev                         # http://localhost:5173
```

The API prints a link like `http://localhost:5173/#token=…`. Open it, and the tab connects. The token changes every time the API starts. If a tab loses its connection, it shows a **Connect this tab** screen where you can paste the new token.

Production build: `npm run build`, then `npm run preview` (http://localhost:4173, already an allowed origin).

### Configuration

| Where | Variable | Default | Purpose |
|---|---|---|---|
| frontend `.env.local` | `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Where the API runs. Compiled into the bundle, so never put secrets here. |
| API environment | `RESUME_OPTIMIZER_API_PORT` | `8000` | API port (1024–65535) |
| API environment | `RESUME_OPTIMIZER_API_ORIGINS` | ports 5173 and 4173 on `localhost` / `127.0.0.1` | Comma-separated exact browser origins allowed to call the API (no `*`) |
| API environment | `RESUME_OPTIMIZER_API_TOKEN` | random per launch | Fixed session token, for scripted use. Avoid it for everyday use. |

All other settings (data folder, AI provider, template, local-only mode…) are the app's usual ones, shared with Streamlit.

## How it connects

```
React (Vite, :5173)  ──fetch + session header──►  src/api (FastAPI, 127.0.0.1:8000)  ──►  existing src/services, src/persistence
                                                                                            ▲
Streamlit (app.py)  ─────────────────────── in-process calls ──────────────────────────────┘   same data/ folder
```

- **One client** ([src/services/api/client.ts](src/services/api/client.ts)) adds the token, normalizes errors into `ApiError {status, code, message, details}`, and never turns a failure into fake data.
- **Types are generated** from the API's OpenAPI schema (`npm run gen:api` → [schema.d.ts](src/services/api/schema.d.ts)). Rerun it after changing `src/api/`.
- **Server state** uses TanStack Query ([queries.ts](src/services/api/queries.ts)). Window focus refetches data, so edits made in Streamlit show up here.
- **The API's guard** ([src/api/security.py](../src/api/security.py)) requires a localhost Host header (which blocks DNS rebinding), an allowed Origin, and the session token. The custom header also forces a CORS preflight, so other websites can't send requests that skip it.
- **Profile saves carry the version they were based on.** If the profile changed in another window or in Streamlit, the save is refused (409) and you're asked to reload. Nothing is overwritten.

## What you can do

| Screen | Backed by |
|---|---|
| **Dashboard**: counts, pipeline, recent jobs and versions, follow-ups, first-run guide | `GET /dashboard` (stored records only; no activity log exists) |
| **Master Profile**: contact and summary, experience and projects (with bullets, skills, verified metrics), education, certifications, achievements; add, edit, reorder, delete; confirm; JSON import/export; version history and restore; delete | `/profile*` |
| **Skills Library**: search, category filter, aliases, evidence links, duplicate-name check | skills are part of the profile (`PUT /profile`) |
| **Role Profiles**: ordered evidence and skill selections; create, edit, duplicate, delete | `/role-profiles*` |
| **Job Descriptions**: paste, upload (.txt/.md/.pdf/.docx), URL (best effort, with a paste fallback), browser-extension inbox; review before saving; duplicate decision; edit; delete | `/jobs*`, `/captures*` |
| **Requirements review**: run the deterministic parser, edit requirements, confirm | `/jobs/{id}/analysis*` |
| **Match report (evaluation)**: supported / partial / not documented with evidence, your judgements, gaps, recommendations | `/jobs/{id}/match*` |
| **Tailoring workflow**: confirm requirements → match → generate → review, approve and export | `/jobs/{id}/tailoring`, `/jobs/{id}/resumes*` |
| **Resume versions**: preview, changes against the profile with evidence, edit (as a new version), checks and approval, DOCX/PDF export with file checks, download | `/resumes*` |
| **Application Tracker**: status, dates, resume used, notes, filters, CSV export, duplicate merge | `/tracker*` |
| **Settings**: AI provider and model, template, paper size, URL import, local-only mode, extension toggle; key *detection* only | `/settings` |

### Truthfulness rules in the UI

- **Generation, matching and checks all run in Python.** The UI only shows their results.
- **Coverage figures are labelled as match estimates**, with the formula one click away. No ATS score is shown or computed.
- **AI wording is off unless configured.** When it's on, the exact request is shown first, and generation stays disabled until you tick consent.
- **Approval needs your confirmation**, and the backend blocks it when validation fails. Only approved versions can be exported.
- **Unsaved edits are protected:** leaving a page or tab with unsaved changes asks first.

## Not available here (by design or backend support)

- **Resume upload that fills in the profile from a PDF or DOCX.** The backend has no resume parser, so the profile is entered by hand or imported as JSON.
- **Deleting, duplicating or comparing resume versions.** The backend doesn't support them. Editing creates a new version instead.
- **ATS scores** and an **activity feed.** Neither exists in the backend.
- **Extension pairing token, full data export (.zip) and "delete everything"** remain on the Streamlit Settings page. They're sensitive or destructive, and weren't added to the API.

## Develop and test

```bash
npm run typecheck     # strict TypeScript
npm run lint          # ESLint (react-hooks, typescript-eslint)
npm test              # Vitest + Testing Library (mocked fetch, isolated tests only)
npm run test:e2e      # Playwright against the REAL API with a throwaway data folder
npm run gen:api       # regenerate API types from src/api
```

- **End-to-end tests** start `python -m src.api` (port 8010, local-only, fresh `e2e/.data/`) and Vite (port 5180), then run the whole workflow using the app's fictional sample profile. Run `npx playwright install chromium` once first.
- **API tests** are part of the Python suite: `pytest tests/test_api.py`.

### Layout

```
src/app/            router (code-split per screen), providers, error boundary
src/layouts/        app shell (collapsible sidebar, mobile drawer), connection gate
src/components/ui/  buttons, form controls, dialog/sheet, tabs, table, alerts (shadcn-style, Radix)
src/components/shared/  page header, empty/error/loading states, confirm dialog, file drop, badges, unsaved-changes guard
src/features/       dashboard, profile, skills, roles, jobs (import, requirements, match), resumes (tailor, versions), tracker, settings
src/services/api/   client, typed endpoints, query hooks, generated schema
```

## Known limitations

- **Single user, local machine.** No accounts. The API is not meant to be exposed on a network.
- **AI wording hasn't been exercised against a live provider from this UI.** The consent flow is tested with mocks, and the backend's own AI tests use stub clients.
- **Concurrent first open of a new job database.** `JobStore` can race its schema migration when two connections open a new database at once. The API avoids this by migrating once, under a lock, at first use. Streamlit and the API opening a brand-new database at the same instant could still race; a proper fix in `src/persistence/job_store.py` is proposed in [FRONTEND_INTEGRATION_REPORT.md](FRONTEND_INTEGRATION_REPORT.md).
- **Seven lint warnings remain** (`react-refresh/only-export-components`). Some files export small helpers next to components; this affects only hot-reload granularity in development.
