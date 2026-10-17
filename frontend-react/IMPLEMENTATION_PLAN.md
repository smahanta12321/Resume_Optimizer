# React Frontend — Implementation Plan

**Status:** Phases 1–5 complete (2026-10-17). See `README.md` for how to run it and `FRONTEND_INTEGRATION_REPORT.md` §8 for verification results and the open backend issue.

## Guiding constraints

- The Streamlit app (`app.py`, `src/ui/`) and every existing Python module stay untouched.
- The React app talks **only** to the approved local adapter (`src/api/`, new). It has no mock fallbacks, and no Python logic is re-implemented in TypeScript (matching, claim checks, validation, and scoring stay in Python).
- Features missing from the backend (resume parsing, version delete/compare, ATS score, activity log) are left out of the navigation, or shown as an honest "not available" note. They are never faked.
- Truthfulness rules from `CLAUDE.md` carry over. Evidence IDs are shown for every tailored line, and human approval is required before export.

## Phases

| Phase | Scope | Exit criteria |
|---|---|---|
| **1. Inspect & report** ✅ | Integration report, this plan | Docs reviewed by owner |
| **2a. Backend adapter** ✅ (approved) | `src/api/` package, security guards (§6 of report), pytest coverage for every route and failure path, README section, one `requirements.txt` line | `pytest` green; Streamlit smoke test unchanged |
| **2b. Frontend foundation** ✅ | Vite + React + TS strict, Tailwind, shadcn/ui primitives, router, TanStack Query, API client with error normalization, types generated from OpenAPI, app shell (collapsible sidebar, mobile drawer, header, toasts, confirm dialog), light/dark tokens, health/setup screen when the API is unreachable | `typecheck`, `lint`, `test`, `build` pass; shell renders against the live adapter |
| **3. Core workflow (vertical slice)** ✅ | Job import (paste/file/URL with fallback) → JD review → match report → generate → review/edit → approve → export/download | The full workflow done by hand against the real backend with the fictional sample profile; Playwright happy path |
| **4. Remaining screens** ✅ | Master Profile editor, Skills Library, Resume Versions, Evaluation, Tracker, Settings, Dashboard, role profiles | Each screen's loading/empty/error states tested |
| **5. QA & docs** ✅ | Responsive/a11y pass, `README.md` in `frontend-react/`, known-limitations list | All checks green or blockers documented |

## Routes (only features with backend support)

| Path | Screen | Backed by |
|---|---|---|
| `/` | Dashboard | `GET /dashboard` |
| `/profile` | Master Profile (tabs: contact & summary, experience, projects, education, certifications, achievements, import/export, history) | `/profile*` |
| `/skills` | Skills Library (table, search, category filter) | `GET/PUT /profile` (skills edited as part of the profile) |
| `/roles` | Role profiles | `/role-profiles*` |
| `/jobs`, `/jobs/new`, `/jobs/:id` | JD list, import, detail/analysis review | `/jobs*`, `/captures` |
| `/jobs/:id/match` | Match report / evaluation | `/jobs/:id/match*` |
| `/jobs/:id/tailor` | Stepper: select role → generate → review → edit → approve → export | `/jobs/:id/resumes*`, `/resumes/*` |
| `/resumes` | Resume versions across jobs | `/jobs/:id/resumes`, `/resumes/:vid*` |
| `/tracker` | Application tracker | `/tracker*` |
| `/settings` | Settings + connection status | `/settings`, `/health` |

## Source layout (`frontend-react/src/`)

```
app/            router.tsx, providers.tsx, App.tsx
layouts/        AppShell (sidebar, header, mobile drawer)
components/ui/  shadcn primitives actually used (button, input, dialog, table, tabs, toast, …)
components/shared/  EmptyState, ErrorState, ConfirmDialog, FileDrop, StatusBadge, EvidenceChips
services/api/   client.ts (fetch wrapper, base URL, token header, AbortSignal, error normalization), schema.d.ts (generated), per-resource query hooks
features/<area>/  screens + feature-local components and forms (RHF + Zod)
lib/            formatting, query keys
styles/         tokens (CSS variables for light/dark)
```

## Dependencies (all dev-time or bundled; no paid services)

react, react-dom, react-router, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers, tailwindcss, shadcn/ui (copied source; Radix primitives as needed), lucide-react, sonner (toasts), class-variance-authority, clsx/tailwind-merge. Dev: vite, typescript, vitest, @testing-library/react, jsdom, eslint, playwright, openapi-typescript. Not used: Recharts (simple CSS bars are enough), Axios (a typed `fetch` wrapper is enough), Framer Motion (one CSS fade-in with reduced-motion support is enough).

## Testing strategy

- **Unit:** API client (success, HTTP errors, network failure, 409 conflict, abort), formatters, Zod schemas.
- **Component:** forms with field errors, file-drop type/size validation, loading/empty/error states, unsaved-changes guard, route rendering.
- **E2E (Playwright):** run against the **real** adapter with a temporary `RESUME_OPTIMIZER_DATA_DIR` seeded from the fictional sample profile. Mocks appear only in unit/component tests.
- **Backend:** pytest for every adapter route, including Host/Origin/token rejection and the profile version-conflict path.

## Acceptance criteria

The brief's §11 applies. In addition: the Streamlit app and the adapter can run at the same time on the same data without corrupting the profile (verified by the 409 test), and no screen shows a number the backend didn't return.

## Decisions

1. FastAPI adapter (A1): approved and built.
2. `requirements.txt` (fastapi, uvicorn) and a short `README.md` section: done.
3. Ports: API `127.0.0.1:8000`, Vite `localhost:5173`, preview `4173` (configurable).
4. **Open:** the fix for the `JobStore` migration race (report §8) needs owner approval.
