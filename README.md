# AI Resume Optimizer

A local-first assistant that tailors a **truthful**, ATS-readable resume to a job description using only facts from your verified master profile. It never applies to jobs, contacts recruiters, or promises ATS outcomes.

See [SPECIFICATION.md](SPECIFICATION.md) for the full product spec and [CLAUDE.md](CLAUDE.md) for engineering rules.

## Status

| Milestone | Scope | State |
|---|---|---|
| 1 | Schemas, master profile management, role profiles, sample data | **Done** |
| 2 | Job import (paste / file / URL) + SQLite + dedup | **Done** |
| 3 | JD parsing and review | **Done** |
| 4 | Evidence matching + match report | **Done** |
| 5 | LLM provider, drafting, approval | **Done** |
| 6 | DOCX/PDF export + validation | **Done** |
| 7 | Tracker, settings, data export/deletion | **Done** |
| 8 | Optional browser extension (capture → review inbox) | **Done** |

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

## Using Milestone 4: Match Report

After confirming a job's analysis, open **Match Report**, pick the job, and click **Run matching** (`rules-v1`, deterministic, offline). Each requirement gets a status, the IDs of the evidence items behind it, a match type, and a one-line explanation.

### How matching decides

Only **evidence items** count: experiences, projects, bullets, education, certifications, and achievements. Your skills list, headline, and summary are claims, not evidence.

| Requirement | `supported` | `partial` | `not_documented` |
|---|---|---|---|
| Skill | The term appears in evidence text, is tagged on it, or appears under a recorded alias (`exact` / `alias`) | Only in your skills list with no evidence, **or** only a *related* term is evidenced (`related`, e.g. PySpark for Apache Spark) | Neither |
| Overall experience | Dated roles total at least the minimum (overlaps counted once) | Fewer years, or roles lack dates | No roles |
| Years with a specific skill | **Never automatic.** Role dates don't show how long you used a skill | The skill is evidenced; you confirm the years | The skill is not evidenced |
| Education | Degree level meets the requirement (and the named field, if any) | Level meets it but the field differs, or the level is unclear | No such degree |
| Certification | Name matches a recorded certification | Same issuer only | None |
| Domain | The domain term appears in evidence | - | Not mentioned |
| Responsibility / qualification | ≥75% of the requirement's key words appear in one evidence item (`text_overlap`, flagged as a hint) | ≥34% overlap | Less |

Related terms come from an explicit map in [src/services/skill_taxonomy.py](src/services/skill_taxonomy.py) and are never treated as the same skill.

### Your judgements

Under **Correct a result**, you can set a requirement's status yourself. A `supported` or `partial` judgement must cite at least one evidence item from your profile. If the evidence isn't recorded, add it to the master profile first. Your judgements survive re-runs; one whose evidence was deleted is removed, and you're told.

### Coverage numbers

Supported = 1, partial = 0.5, not documented = 0. Required and preferred coverage average within each group. Overall coverage weights required ×3, preferred ×2, and other ×1. These figures describe how much of the JD your recorded evidence addresses. **They are not a hiring probability or an ATS score.** The page shows the formula.

### Staleness, gaps, recommendations

- The report records the profile version and analysis it used. If either changes, the page says so and offers **Re-run matching**. Confirming an analysis alone does not make the report stale.
- **Gaps** lists required and preferred requirements with no evidence. They won't be claimed in a resume.
- **Recommendations** rank your role profiles and projects by how much evidenced requirement weight they cover. You make the final choice when building the resume (Milestone 5).

## Using Milestone 5: Resume Builder

Open **Resume Builder** and pick a job that has a current match report.

1. **Generate a new version.** Choose a base role profile (the best match is preselected and marked *recommended*) and a 1- or 2-page target, then click **Generate draft**. The draft is built by rules, offline:
   - Experience is listed newest first. Titles, employers and dates are copied from your profile, never generated.
   - Bullets are copied **verbatim**, ranked by how many matched requirements cite them (required ×3, preferred ×2). Bullets with numbers that have no verified metric are left out.
   - Skills list only profile skills that some evidence shows, JD-matched skills first. Skills without evidence are left out, with a note.
   - Your profile summary and headline (or the role profile's headline) are used as written.
2. **Optional AI wording** (see below): each rewrite is checked and discarded if it adds facts.
3. **Review** in the tabs:
   - **Preview**: the resume as text.
   - **Changes & evidence**: every bullet's original vs final wording, its source (from profile / AI rewrite / your edit) and evidence; skills with their evidence; and everything left out, with the reason.
   - **Edit**: change wording, untick bullets to drop them, edit the summary. **Save as new version** keeps the old version unchanged.
   - **Validate & approve**: errors block approval; warnings need you to confirm the resume is accurate. Approval is recorded on the version. Content is never changed afterwards.

### What validation checks

| Check | Result |
|---|---|
| A title, employer, date, degree or certification differs from the profile | error |
| A bullet or skill cites evidence that no longer exists | error |
| A rewritten/edited bullet adds a number not in its source or verified metrics | error |
| A rewritten/edited bullet mentions a skill/tool its source doesn't (or that you didn't tag on it) | error |
| A summary claims more years than your dated roles total, or names skills/numbers your evidence doesn't show | error |
| New proper names, or stronger wording than the source ("led", "spearheaded", "significantly") | warning |
| Profile changed since the version was made; estimated length over target; empty sections | warning |
| Required JD items with no evidence | info |

### AI rewriting (optional, off by default)

Set in `.env`:

```env
RESUME_OPTIMIZER_LLM_PROVIDER=anthropic      # or openai, or none (default)
RESUME_OPTIMIZER_LLM_MODEL=                  # Anthropic default: claude-opus-5-5; OpenAI: set a model
ANTHROPIC_API_KEY=...                        # or OPENAI_API_KEY; read only by the provider SDK
```

On **Resume Builder**, tick **Improve wording with AI**. The page shows **exactly what will be sent**, and nothing is sent until you tick the consent box.
- **Sent:** the target job title, JD requirement terms from your confirmed analysis, the selected bullets with their allowed skill terms and verified metrics, role titles and dates, evidenced skill names, and your documented years.
- **Never sent:** your name, email, phone, links, location, employer names, or the raw JD text.

JD text is wrapped and labelled as untrusted data in the prompt. Prompts live in [prompts/](prompts/). The model returns JSON against a fixed schema; malformed output gets one retry, then the app saves the rule-based draft and tells you why. With Anthropic, server-side refusal fallbacks are enabled on models that support them. If the call fails for any reason (key, network, refusal, cut-off), you still get the original-wording draft.

## Using Milestone 6: Export

On **Resume Builder → Export**, an **approved** version can be exported. Unapproved versions can't. **Export DOCX and PDF** writes both files to `output/<job id>/<version id>/` (named like `Your_Name_Company_Role_Resume.pdf`), checks them, and offers download buttons. **Export again** re-renders the same approved content, for example after changing the page size.

### Layout (default "classic" template)

- Single column with standard headings: Summary, Skills, Experience, Projects, Education, Certifications.
- Name and contact details are in the document body, not page headers or footers.
- Real bullet lists. No tables, text boxes, icons, images or columns.
- Arial, 10.5 pt body text. Text is **never shrunk** to fit a page.
- Dates formatted consistently, e.g. `Jul 2022 – Present`.
- A4 by default; set `RESUME_OPTIMIZER_PAGE_SIZE=Letter` for US Letter.
- **PDF**: rendered with reportlab, with selectable text and an embedded TrueType font (Arial, DejaVu Sans or Liberation Sans, whichever is installed, or `RESUME_OPTIMIZER_PDF_FONT`). Without one it falls back to built-in Helvetica, and characters Helvetica can't draw are flagged.
- **DOCX**: built with python-docx using Word's built-in Heading 1 and List Bullet styles, so it stays easy to edit.

Both files are rendered from one shared block list, so they carry the same text.

### Export checks

| File | Check | Fails / warns when |
|---|---|---|
| both | Opens | The file can't be reopened |
| both | All approved content present | Any approved line (name, contact, headings, entries, bullets, skills, education) is missing from the extracted text |
| both | Readable font size | Any text is under 9 pt |
| PDF | No blank pages / Text stays on the page | A page has no text, or characters fall outside the page |
| PDF | Text extracts cleanly | Glyphs extract as unreadable `(cid:…)` codes |
| PDF | Characters supported by font | The fallback font can't draw a character |
| PDF | Fits target length | More pages than the 1- or 2-page target (warning: shorten it in Edit or use the 2-page target) |
| DOCX | No tables / No images or text boxes / Contact details in body | Layout elements some parsers misread |
| both | DOCX and PDF match | The two files' text differs (warning) |

DOCX page count isn't measured (that needs a word processor). The PDF has the same content and is the reference. Passing these checks means the files are readable and complete. It does **not** guarantee any ATS result.

## Using Milestone 7: Tracker and Settings

### Application Tracker

One table of every job: company, role, status, applied and follow-up dates, required coverage, analysis state, resume versions (approved/total), the resume used, and whether it was exported.

- **Filter** by status, platform, free-text search, or *follow-up due*. Due follow-ups also show on the Dashboard; closed statuses (rejected, withdrawn, archived) never nag.
- **Update an application**: status, applied date, follow-up date, the resume version you sent, and notes.
  - Marking a job applied (or later) without a date records today, and tells you so.
  - Future applied dates, and follow-ups before the applied date, are rejected.
  - Download the exact DOCX/PDF you sent.
- **Download CSV** of the filtered jobs, optionally with JD text. Cells that start with `= + - @` are prefixed with `'` so spreadsheet apps don't execute them as formulas.
- **Possible duplicates** lists jobs matching the import duplicate rules. You choose which record to keep. Its blanks are filled from the other, the other's notes are appended, and the page says exactly what the other record's deletion removes before you confirm. Nothing merges automatically.
- **Delete** removes a job with its analysis, match report, resume versions and exported files.

### Settings

| Setting | Options |
|---|---|
| Local-only mode | On = never contact any external service (URL import and AI rewriting are disabled) |
| AI provider / model | None (default), Anthropic (default model `claude-opus-5-5`), OpenAI (model required) |
| Template | Classic, or Compact (tighter spacing and margins, still ≥ 9.5 pt) |
| Paper size | A4 or Letter |
| URL import | On / off |

- Settings are saved to `data/settings.json`.
- A **non-empty environment variable (or `.env` line) overrides the page**. That field is locked, with a note naming the variable. `.env.example` leaves these blank on purpose.
- **API keys are never saved by the app.** They're read only from the environment, and the page shows only whether each is *detected*.

The page also covers your data:
- **What is stored and what is sent**: a privacy notice with your actual data and output folders.
- **Download all my data**: a zip with the profile and every version, role profiles, each job's JD/analysis/match report/resume versions/export records, settings, and (optionally) exported files.
- **Delete everything**: type `DELETE EVERYTHING` to remove the profile, jobs, derived data, exported files, and settings. Unrelated files in the output folder are left alone.

## Using Milestone 8: Browser extension (optional)

A Manifest V3 extension for Chrome/Edge in [browser_extension/](browser_extension/). When **you click it** on a job posting you're viewing, it shows the page's text (your selection, the page's published job data, or the main text) in an editable preview. After you confirm, it sends the text to a **local receiver** on `127.0.0.1`. The capture lands in **Job Import → From browser**, where you review and save it like a paste, including the duplicate check.

Quick start (full steps and security notes: [browser_extension/README.md](browser_extension/README.md)):
1. **Settings → Browser extension**: turn it on and save.
2. Run `python -m src.extension_receiver` in a second terminal.
3. Load `browser_extension/` via **Load unpacked** in `chrome://extensions`.
4. Paste the port and pairing token into the extension's options.

Safeguards:
- **Extension:** activates only when you click it (`activeTab`), with no background or content scripts. It reads only the page in front of you and never navigates, clicks or logs in. Page HTML becomes plain text that is never rendered.
- **Receiver:** bound to 127.0.0.1, off unless enabled, and requires a host check, a browser-extension (or non-browser) origin, the pairing token, JSON and size limits, plus schema validation. Request bodies are never logged.
- **Data handling:** the inbox holds at most 50 items, and an item is removed once you save it as a job or discard it. **Settings → Delete everything** clears the inbox and the pairing token. The token is never included in data exports.

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
  - `data/jobs.sqlite3`: imported jobs (extracted JD text, URL, and your metadata; never raw page HTML), their JD analyses, match reports, and resume versions. The database schema upgrades automatically. Deleting a job deletes its analysis, match report and resume versions.
- Exported resumes go to `output/<job id>/<version id>/` (override with `RESUME_OPTIMIZER_OUTPUT_DIR`). Deleting a job (Job Import or Tracker) also deletes its exported files.
  - `data/settings.json`: settings saved from the Settings page (no secrets)
  - `data/extension_token`: pairing token for the optional browser extension
- `data/` (except the fictional samples) and `output/` are git-ignored.
- Outbound network requests happen only when you trigger them: a **URL import** (that job site and its robots.txt), or **AI rewriting**, which is configured, previewed and consented to per draft (see above). Contact details are never sent to an AI provider.
- Logs record provider, model, counts and request IDs, never resume or profile text.
- Imported JD text is treated as untrusted data. It is stored and displayed, never executed or followed as instructions.
- Logs record events and version numbers only, never profile content or secrets.
- **Import / export → Delete all profile data** permanently removes the profile, all versions, and role profiles. **Settings → Delete everything** removes all app data, including jobs and exported files. **Settings → Download all my data** exports everything first.
- **Local-only mode** (Settings) blocks every outbound request.

## Project layout

```text
app.py                     Streamlit entry point (navigation)
src/config.py              settings: env > settings.json > defaults; local-only; logging
src/schemas/profile.py     Pydantic models: MasterProfile, evidence items, RoleProfile
src/schemas/job.py         Pydantic Job model (source, status, JD text)
src/schemas/analysis.py    Pydantic JDAnalysis / Requirement models
src/schemas/match.py       Pydantic MatchReport / RequirementMatch / MatchOverride models
src/schemas/resume.py      Pydantic ResumeVersion / ResumeContent models (immutable versions)
src/persistence/profile_store.py   versioned JSON storage
src/persistence/job_store.py       SQLite job storage
src/services/profile_service.py    import/export, quality checks, role-profile ops
src/services/jd_import_service.py  JD text cleanup, file extraction, URL canonicalization, dedup
src/services/url_import.py         SSRF-safe, robots-aware single-page fetch + extraction
src/services/skill_taxonomy.py     curated skill/domain vocabulary for term recognition
src/services/jd_parser.py          deterministic JD parser (rules-v1)
src/services/jd_analysis_service.py   analysis workflow: run, edit, staleness, confirmation
src/services/matching_service.py      deterministic evidence matcher (rules-v1)
src/services/match_report_service.py  coverage summary, gaps, overrides, staleness, recommendations
src/services/resume_generator.py      deterministic evidence selection -> draft
src/services/claim_checker.py         numbers / skills / wording checks for rewrites and edits
src/services/resume_rewriter.py       optional LLM rewrite (prompts/), checked before use
src/services/resume_validation.py     pre-approval validation + change summary
src/services/resume_service.py        generate versions, apply user edits
src/services/llm/                     provider abstraction: Anthropic, OpenAI
src/services/render/                  shared blocks, classic style + fonts, DOCX and PDF renderers
src/services/export_service.py        export approved versions (safe paths/file names), delete outputs
src/services/export_validation.py     DOCX/PDF content, layout and font checks
src/schemas/export.py                 ExportRecord / ExportCheck
src/services/tracker_service.py       tracker rows, filters, application updates, CSV, duplicate merge
src/services/data_service.py          export-all zip, delete everything
src/persistence/settings_store.py     settings.json (non-secret settings)
src/persistence/extension_token.py    browser-extension pairing token (data/extension_token)
src/extension_receiver.py             local capture receiver (python -m src.extension_receiver)
src/schemas/capture.py                captured-JD schema (inbox)
browser_extension/                    optional Manifest V3 extension (see its README)
src/ui/                    Streamlit pages and helpers
data/samples/              fictional sample data (safe to commit)
tests/                     pytest suite (fictional data only)
prompts/                   LLM prompt templates
templates/                 reserved for additional resume templates (the default is defined in src/services/render/style.py)
```

## Known limitations (Milestone 8)

- The extension is installed unpacked (developer mode); it isn't published to a browser store. Tested logic: capture helpers (Node tests), receiver (HTTP tests), manifest permissions. The popup itself was not driven in an automated browser, so do one manual capture after installing.
- Chrome and Edge only. Firefox would need manifest tweaks.
- The receiver is a separate process you start yourself; it doesn't start with the Streamlit app.
- Pages that render the JD only after clicking "see more" are captured as shown. Expand it yourself, or select the text, before clicking the extension.

## Known limitations (Milestone 7)

- Changing settings takes effect on the next page action. Changing `.env` requires restarting the app.
- Merging duplicates keeps only the chosen record's analysis, match report and resume versions. The other record's are deleted (you're told exactly what before confirming).
- The data-export zip is for backup and transparency. Only the master profile JSON inside it can be re-imported in the app today. Jobs can't be restored from the zip yet.
- Follow-up reminders show inside the app only. No notifications are sent.

## Known limitations (Milestone 6)

- DOCX page count is not measured. Word may paginate slightly differently from the PDF, depending on installed fonts. If Arial isn't installed where the DOCX is opened, Word substitutes a similar font.
- The PDF title/date line uses separators (`Title | Company | Location | Dates`) rather than right-aligned dates. That keeps text order unambiguous for parsers, at some cost in looks.
- The PDF is checked by extracting its text with pdfplumber. Commercial ATS parsers differ and may read files differently.

## Known limitations (Milestone 5)

- The claim checker is rule-based. It reliably blocks new numbers and recognized skills/tools, and warns on new names and stronger wording. A rewrite can still shift meaning in ways rules can't see (e.g. "assisted with" → "delivered"), which is why approval requires reading every changed line in **Changes & evidence**.
- AI rewriting has been tested with stub clients, not live API calls. The first real call uses your key and account.
- Sections can't be reordered yet, and a bullet can't move between roles (by design: it must stay under the role it came from).
- AI-assisted JD parsing and semantic matching are not added yet. Both stay rule-based and offline.

## Known limitations (Milestone 4)

- Matching is rule-based. A responsibility worded very differently from your bullets shows as not documented or partial even if you did it. Use **Correct a result** and cite the evidence. Semantic (AI-assisted) suggestions are planned with Milestone 5 and will still need your confirmation.
- Text overlap can over-credit a bullet that shares words but not substance. It is labelled as a hint for that reason.
- A parsed requirement like "3+ years of experience in machine learning" may carry a skill term (Machine Learning). That makes it skill-specific, so it can only be `partial`. Set its normalized term to `overall` on JD Analysis if it means total experience.
- Overall experience counts every dated role, including internships, if you listed them.

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
