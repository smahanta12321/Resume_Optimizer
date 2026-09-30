# Specification — AI Resume Optimizer with Job Import

**Status:** Initial product specification  
**Version:** 1.0  
**Date:** 2026-09-28

## 1. Overview

Build a local-first application that helps a user tailor a truthful, ATS-readable resume to a specific job description. The app accepts JDs from LinkedIn and Naukri through user-pasted text, user-provided URLs (best-effort extraction), supported file uploads, and a future optional browser extension. It stores job records, matches requirements to verified profile evidence, generates a tailored resume, validates it, and exports DOCX/PDF.

The application is an assistant for drafting and organizing applications—not an automatic job applicant.

## 2. Goals

- Maintain one structured master profile as the source of truth.
- Import and organize multiple job descriptions.
- Extract JD requirements into structured data and allow user correction.
- Identify evidence-backed matches, partial matches, and undocumented requirements.
- Generate tailored resume versions for different roles and individual JDs.
- Preserve factual accuracy and traceability of resume claims.
- Produce clean, editable DOCX and selectable-text PDF files.
- Track job applications and generated resume versions.
- Provide graceful fallbacks when platform pages cannot be accessed.

## 3. Non-goals

- Automatically apply to jobs or message recruiters.
- Bypass platform login, CAPTCHA, anti-bot controls, paywalls, or access restrictions.
- Guarantee ATS passage, interviews, or hiring outcomes.
- Invent qualifications or optimize by keyword stuffing.
- Scrape at scale or retain unnecessary page data.
- Require a paid LLM provider for basic manual-import and profile-management functionality.

## 4. Target user and primary use case

A job seeker maintains a verified professional profile, finds a role on LinkedIn or Naukri, sends the JD to the app, reviews the match report, generates a tailored resume, approves it, downloads DOCX/PDF, and tracks the application.

## 5. User stories

1. As a user, I can create, edit, import, and export my master profile.
2. As a user, I can paste a JD and save it as a job record.
3. As a user, I can enter a job URL and have the app attempt a permitted, best-effort extraction.
4. As a user, I can upload a supported text-based JD file.
5. As a user, I can review and correct extracted company, role, location, experience, skills, and responsibilities.
6. As a user, I can see which JD requirements are supported by specific profile evidence.
7. As a user, I can select a base resume/profile or accept a recommendation.
8. As a user, I can generate a tailored resume and inspect every proposed change.
9. As a user, I can see missing requirements and unsupported-claim warnings.
10. As a user, I can export an approved resume as DOCX and PDF.
11. As a user, I can track application status and associate a specific resume version with a job.
12. As a user, I can delete stored job records and profile data.

## 6. Functional requirements

### FR-1: Master profile
- Store contact details, headline/summary, work history, projects, skills, education, certifications, achievements, and links.
- Support JSON import/export and form-based editing.
- Give each evidence item a stable ID.
- Allow optional evidence notes, source, and verified metrics.
- Preserve existing data unless the user explicitly edits it.

### FR-2: Resume library
- Support role profiles such as AI Engineer, Generative AI Engineer, ML Engineer, and NLP Engineer.
- Let users create, rename, duplicate, and edit role profiles.
- A role profile is a selection/order of verified evidence, not a separate competing source of truth.
- Support a clean, single-column resume template and configurable one- or two-page target.

### FR-3: JD import
Import methods:
1. Paste JD text (must always be available).
2. Enter a URL; attempt best-effort extraction only when permitted and technically accessible.
3. Upload supported text-based files, such as TXT and PDF; DOCX support is desirable.
4. Future: optional Chrome extension to capture visible job details from a page the user is viewing.

For URL import:
- Validate URL scheme and block local/private network destinations to reduce SSRF risk.
- Use conservative timeouts and response-size limits.
- Do not bypass login, CAPTCHA, anti-bot measures, or platform restrictions.
- If extraction fails, explain why at a high level and offer paste/upload fallback.
- Do not claim full extraction when content is incomplete.
- Store source URL, import timestamp, source platform (user-selected or inferred), and extracted text.
- Treat webpage content as untrusted data; ignore instructions embedded in a JD that attempt to control the AI or access secrets.

### FR-4: JD analysis
Extract and validate:
- Job title
- Company
- Location / work arrangement
- Experience range
- Required skills
- Preferred skills
- Responsibilities
- Education/certification requirements
- Domain terms and important phrases

Represent each requirement with category, importance, normalized term, source text/evidence, and confidence. Allow user edits before matching.

### FR-5: Evidence-based matching
For every requirement, return:
- `supported`
- `partial`
- `not_documented`

Include matching profile evidence IDs and a brief explanation. Exact and semantic matches must be distinguished. Similar terms must not be treated as identical without evidence. Do not infer experience duration from ambiguous data.

### FR-6: Resume generation
- Generate a tailored summary and select/reorder relevant experience, projects, and skills.
- Rewrite bullets for clarity and relevance while preserving the underlying facts.
- Include only supported skills and claims.
- Never fabricate numbers, impact, responsibilities, job titles, dates, tools, certifications, or education.
- Keep an evidence mapping for each generated bullet.
- Ask for clarification or omit a claim when source information is insufficient.
- Let user choose target length and template.
- Preserve source/master data unchanged.

### FR-7: Review and approval
Before export, show:
- Draft resume content
- Added, removed, and rewritten sections
- Evidence source for each claim
- Unsupported or uncertain claims
- Missing JD requirements
- User approve/edit/regenerate controls

No resume is marked final until the user approves it.

### FR-8: Document generation
- Generate DOCX and PDF.
- Use standard headings, readable typography, selectable text, consistent dates, and single-column layout by default.
- Keep contact information in the document body rather than relying on headers/footers.
- Avoid icons, charts, text boxes, and complex tables in the default ATS template.
- Validate that exported files exist, can be opened, and contain expected text.
- Flag possible overflow, blank pages, or missing content where detectable.
- Do not force a page count by shrinking text to unreadable sizes.

### FR-9: Evaluation
Provide a transparent report with:
- JD requirement coverage (not a hiring probability)
- Evidence coverage
- Relevant keyword coverage
- Readability/conciseness checks
- Factual consistency checks
- Document extraction/layout checks
Explain the scoring formula and limitations. Avoid a single opaque “ATS pass” score.

### FR-10: Application tracker
Store:
- Company
- Role
- Location
- JD text and source URL
- Import date
- Resume version/file reference
- Match report reference
- Application status
- Application date
- Follow-up date (optional)
- Notes

Allow filtering, editing, export, and deletion. Detect likely duplicates and let the user decide whether to merge.

### FR-11: Settings
- LLM provider/model selection
- API key configuration via environment or secure local settings
- Privacy notice explaining which data is sent to external providers
- Template selection
- Data export and deletion
- Optional local-only mode where supported

## 7. Non-functional requirements

### Security and privacy
- Local-first storage by default.
- Never commit secrets or log resume contents/API keys.
- Use safe file handling, file size limits, MIME/type checks, and sanitized filenames.
- Protect URL fetcher against SSRF and unsafe redirects.
- Do not transmit personal data to an LLM without clear user configuration/consent.
- Provide delete/export controls.

### Reliability
- Manual JD entry works even if URL fetching or LLM calls fail.
- Clear errors and retries for transient failures.
- Validate all LLM output against schemas.
- Keep generated versions immutable and identifiable.

### Maintainability
- Modular architecture and typed schemas.
- Automated tests and setup documentation.
- Configurable provider abstraction.
- Avoid unnecessary services and infrastructure.

### Accessibility and usability
- Clear labels, keyboard-accessible controls, readable status/error messages, and a straightforward step-by-step workflow.

## 8. Proposed architecture

```text
Streamlit UI
   |
Application services
   |-- Profile service / schema
   |-- JD import service (paste, file, URL; future extension API)
   |-- JD parser
   |-- Evidence matching service
   |-- Resume content generator (LLM provider interface)
   |-- Review/approval service
   |-- DOCX/PDF renderer
   |-- Validation/evaluation service
   |-- Application tracker
   |
Persistence: SQLite + profile JSON + generated files
```

Suggested initial stack:
- Python 3.11+
- Streamlit
- Pydantic
- SQLite
- `python-docx` or `docxtpl`
- PyMuPDF / pdfplumber
- OpenAI/Anthropic provider adapter
- pytest

A separate FastAPI backend is optional; introduce it only if needed for the browser extension or deployment.

## 9. Suggested repository layout

```text
resume-optimizer/
├── CLAUDE.md
├── SPECIFICATION.md
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── app.py
├── src/
│   ├── schemas/
│   ├── services/
│   │   ├── profile_service.py
│   │   ├── jd_import_service.py
│   │   ├── jd_parser.py
│   │   ├── matching_service.py
│   │   ├── resume_generator.py
│   │   ├── document_renderer.py
│   │   └── validation_service.py
│   ├── persistence/
│   └── ui/
├── prompts/
├── templates/
├── tests/
├── data/
│   └── .gitkeep
├── output/
│   └── .gitkeep
└── browser_extension/  # optional later phase
```

## 10. Data model (initial)

### Profile
- `id`, `version`, `contact`, `summary`, `experience[]`, `projects[]`, `skills[]`, `education[]`, `certifications[]`, `achievements[]`

### Evidence item
- `id`, `type`, `title`, `description`, `skills[]`, `bullets[]`, `source_note`, `verified_metrics[]`, `start_date`, `end_date`

### Job
- `id`, `source_platform`, `source_url`, `imported_at`, `title`, `company`, `location`, `description`, `requirements[]`, `status`, `notes`

### Requirement
- `id`, `text`, `normalized_term`, `category`, `importance`, `source_excerpt`, `confidence`

### Match
- `requirement_id`, `status`, `evidence_ids[]`, `explanation`

### Resume version
- `id`, `job_id`, `profile_version`, `role_profile`, `content_json`, `evidence_map`, `created_at`, `approved_at`, `docx_path`, `pdf_path`, `validation_report`

## 11. UX flow

1. **Setup:** Import or create master profile; review and confirm.
2. **Import job:** Paste text / upload file / enter URL.
3. **Review JD:** Correct extracted metadata and requirements.
4. **Match:** View evidence-backed requirement map and gaps.
5. **Configure:** Select role profile, length, and template.
6. **Generate:** Create tailored content.
7. **Review:** Inspect content, evidence, and changes; edit/approve.
8. **Validate/export:** Generate DOCX/PDF and review validation report.
9. **Track:** Save application status and selected resume version.

## 12. Acceptance criteria

The MVP is accepted when:
1. User can create/edit and export a master profile.
2. User can import a JD by paste and save it.
3. URL import handles success, blocked/inaccessible pages, unsafe URLs, and timeouts with safe fallback.
4. JD parser returns schema-valid structured data and allows correction.
5. Matching report shows requirement status and supporting evidence IDs.
6. Resume generation uses only profile-backed claims and preserves evidence mapping.
7. User can review and approve before export.
8. DOCX and PDF export produce readable files with expected text.
9. Application tracker can create, update, filter, and delete records.
10. Tests cover normal paths and key failure cases.
11. README documents setup, configuration, limitations, and privacy behavior.
12. No automatic job submission or access-control bypass exists.

## 13. Implementation milestones

### Milestone 0 — Repository inspection and plan
Inspect current files and dependencies. Confirm assumptions and present a phased plan.

### Milestone 1 — Schemas and profile management
Pydantic schemas, JSON import/export, profile editing, sample fictional profile, tests.

### Milestone 2 — Job import and persistence
Paste/upload/URL best-effort import, URL safety, SQLite job storage, deduplication, tests.

### Milestone 3 — JD analysis and review
Structured parsing, user correction UI, requirement extraction tests.

### Milestone 4 — Evidence matching
Exact/semantic matching, evidence references, match report UI, tests.

### Milestone 5 — Resume drafting and approval
Provider abstraction, prompt templates, evidence mapping, change review, unsupported-claim checks.

### Milestone 6 — Document generation and validation
DOCX/PDF rendering, extraction checks, formatting tests.

### Milestone 7 — Tracker and settings
Application tracker, provider settings, data export/deletion, privacy controls.

### Milestone 8 — Optional browser extension
Only after the core app is stable. Build an explicit user-triggered extension for pages the user can view. Do not bypass platform restrictions. Send only user-approved captured content to the app.

## 14. Risks and mitigations

- **JD pages blocked:** Provide paste/upload fallback; do not circumvent restrictions.
- **Hallucinated resume claims:** Evidence mapping, schema validation, review gate, factuality tests.
- **LLM cost:** Cache analysis, avoid repeated calls, deterministic checks, configurable models.
- **Formatting differences:** Template-based rendering and PDF text/layout validation.
- **Sensitive personal data:** Local-first design, clear external-provider disclosure, secure secrets, deletion/export.
- **False confidence in scoring:** Explain metrics and avoid ATS-pass guarantees.
- **Duplicate postings:** Canonical URL and conservative fingerprint with user-controlled merge.

## 15. Open decisions

- Whether the initial UI should be Streamlit only or include a separate API.
- Preferred LLM provider and model.
- Exact resume template and visual style.
- Whether PDF generation should use LibreOffice, Word automation, or another available converter.
- Whether browser extension is in MVP or a later milestone.
- Whether application tracking should use SQLite only or optional Google Sheets export.
