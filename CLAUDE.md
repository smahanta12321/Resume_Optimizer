# CLAUDE.md — AI Resume Optimizer

## Project purpose
Build a local-first AI Resume Optimizer that imports job descriptions from LinkedIn and Naukri (via user-provided URL, pasted text, and eventually an optional browser extension), compares them with a verified master profile, and generates tailored, ATS-readable resumes in DOCX/PDF.

## Core principles
1. **Truthfulness first:** The master profile is the single source of truth. Never invent skills, employers, dates, responsibilities, education, certifications, outcomes, or metrics.
2. **Human approval:** Show extracted JD details and generated resume content for review before final export. Do not apply to jobs or submit resumes automatically.
3. **Respect access restrictions:** Do not bypass authentication, CAPTCHAs, paywalls, anti-bot controls, or platform restrictions. URL import must gracefully fall back to paste/upload. Use only content the user is authorized to access.
4. **Privacy and security:** Keep profile data local by default. Store API keys in environment variables or a secrets manager; never commit secrets or log sensitive profile data. Make external LLM transmission explicit and configurable.
5. **ATS-friendly output:** Prefer clean, single-column layouts, standard headings, selectable text, and reliable DOCX/PDF output. No keyword stuffing or guarantees of ATS success.
6. **Traceability:** Preserve source evidence for claims and show which master-profile entries support each tailored bullet.
7. **Cost control:** Use deterministic code for parsing, normalization, validation, and scoring where practical. Minimize LLM calls and allow model/provider configuration.

## Suggested stack
- Python 3.11+
- Streamlit UI
- FastAPI only if/when a separate backend is useful
- Pydantic for schemas and validation
- SQLite for job/application records; JSON for import/export of master profile
- `python-docx` or `docxtpl` for DOCX generation
- PyMuPDF and/or pdfplumber for PDF text extraction/validation
- Provider abstraction for OpenAI and Anthropic APIs
- pytest for automated tests
- Optional Chrome extension (Manifest V3) in a separate `browser_extension/` directory

Do not add dependencies without explaining why. Check the existing repository and reuse its conventions before creating or restructuring files.

## Product workflow
1. User creates/imports and reviews a master profile.
2. User imports a JD by pasting text, uploading a supported file, or entering a URL.
3. URL extraction is best-effort only; if inaccessible or incomplete, ask the user to paste the JD.
4. Parse JD into structured fields: role, company, location, experience, required/preferred skills, responsibilities, qualifications, and source URL.
5. User reviews and confirms extracted JD.
6. Match requirements against profile evidence: `supported`, `partial`, or `not_documented`.
7. Recommend a base role profile and relevant projects, with manual override.
8. Generate tailored resume content using only supported facts.
9. Display changes, evidence mapping, gaps, and warnings for approval.
10. Generate DOCX and PDF; validate text extraction, page count, empty sections, overflow indicators where feasible, and layout.
11. Save job, resume version, report, and user-selected application status.

## Required application areas
- Dashboard
- Master Profile (create/edit/import/export)
- Resume Library / role profiles
- Job Import and JD review
- Match Report
- Resume Builder / preview / approval
- Evaluation and validation report
- Application Tracker
- Settings (provider, model, privacy, template)

## Data and content rules
- Store master profile in a versioned, validated schema.
- Each experience/project bullet should ideally have an evidence ID, source note, and optional verified metrics.
- Distinguish exact skills from related concepts; do not claim equivalence automatically.
- Do not mark a skill as present merely because it appears in a JD.
- Do not fabricate missing details. Ask a concise clarification question or omit the claim.
- Keep original profile and base resumes immutable during generation; create versioned outputs.
- Avoid storing full job-page HTML unless necessary and permitted. Store extracted JD text, URL, import time, and user-provided source label.
- Deduplicate jobs using canonical URL when available, otherwise a cautious fingerprint of company/title/location/JD text.

## Engineering standards
- Use modular code with clear boundaries: UI, schemas, profile repository, JD import/parsing, matching, LLM provider, content generation, document rendering, validation, persistence.
- Use type hints, docstrings for public functions, structured logging, and clear errors.
- Validate all model output against schemas; retry only for bounded, recoverable schema errors.
- Never place API keys in frontend code, source control, or logs.
- Add tests for parsing, evidence matching, unsupported claims, deduplication, document generation, and error/fallback paths.
- Include `.env.example`, `.gitignore`, setup instructions, and sample synthetic data clearly marked as fictional.
- Keep user data out of test fixtures unless explicitly sanitized.
- Ensure the app remains usable without URL extraction or an LLM provider: manual JD input and deterministic checks must still work.

## Definition of done for a feature
- Implementation and tests are complete.
- Failure and fallback states are handled.
- User-facing labels and errors are clear.
- Documentation is updated.
- No unrelated files are modified.
- The feature is manually smoke-tested or the limitation is documented.

## Working method for Claude Code
1. Inspect the repository, current branch, files, and existing architecture before editing.
2. Read this file and `SPECIFICATION.md`.
3. Summarize the plan and identify assumptions/risks.
4. Implement in small phases; do not attempt a huge one-shot rewrite.
5. Run relevant tests after each phase and report actual results.
6. Preserve existing user changes. Never run destructive Git commands or overwrite files without explicit approval.
7. At the end, report files changed, features implemented, tests run, known limitations, and the next recommended phase.
