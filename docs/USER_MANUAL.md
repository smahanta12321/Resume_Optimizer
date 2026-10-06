# AI Resume Optimizer — User Manual

**Covers:** Milestones 1–8: Master Profile, Resume Library, Job Import, JD Analysis, Match Report, Resume Builder with DOCX/PDF export, Application Tracker, Settings, and the optional browser extension.

The app keeps one **master profile**, a verified record of your career. Every tailored resume will be built only from facts in it, so accuracy here matters most.

---

## 1. Start the app

1. Open PowerShell in `D:\Resume_Optimizer`.
2. Run:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   streamlit run app.py
   ```
3. Your browser opens at **http://localhost:8501**. Use the sidebar to switch between **Dashboard**, **Master Profile**, **Resume Library**, **Job Import**, **JD Analysis**, **Match Report**, **Resume Builder**, **Application Tracker** and **Settings**.
4. To stop the app, press `Ctrl+C` in the terminal.

> Everything stays on your computer in the `data/` folder. The app goes online only when you ask it to: to fetch a job page by URL, or (if you set it up) to improve resume wording with AI after you've seen and agreed to what is sent.

---

## 2. Create your master profile

Open **Master Profile**. If no profile exists, choose one of:

| Option | When to use |
|---|---|
| **Create from scratch**: enter your full name (and email), then click **Create profile** | Starting fresh |
| **Import profile JSON**: choose a `.json` file (up to 1 MB), check the summary, then click **Save imported profile as new version** | Restoring a backup |
| **Load fictional sample profile** | Just exploring. A 🧪 banner reminds you the data is fake. Replace it before real use. |

---

## 3. Fill in each section

Each tab has its own **Save** button. Saving creates a new profile version.

### Contact & summary
Enter name, email, phone, location, headline and summary. Add links (GitHub, LinkedIn, portfolio) in the **Links** table, then click **Save contact & summary**.

> Only write summary statements you can back up with entries in the other tabs.

### Experience
1. Open **➕ Add experience**.
2. Fill in **Employer**, **Job title**, **Start (YYYY-MM)**, **End** (leave blank if you're still there), plus location, description and **Skills** (comma-separated).
3. Add **Bullets**, one factual achievement per row:
   - **Bullet text**: what you did.
   - **Skills**: skills this bullet shows, e.g. `Python, Docker`.
   - **Source note**: where this can be verified, e.g. "appraisal 2023".
   - **Verified metrics**: numbers you can prove, written as `label=value; label=value`, e.g. `queues=12; latency cut=35%`.
4. Click **Add**. To change an entry later, expand it, edit, and click **Save**.

**Tables tip:** click the **+** row at the bottom of a table to add a row. To remove a row, tick its row checkbox and click the 🗑 icon, then save.

### Projects
Same as Experience. You can also link a project to a job with **Related experience**.

### Skills
Add one row per skill:
- **Category**: language, framework, tool, platform, concept, soft or other.
- **Aliases**: *exact* alternate names only, e.g. `k8s` for Kubernetes. Don't list related technologies.
- **Evidence IDs**: the bullets, jobs or projects that prove this skill, e.g. `bul-3f2a9c1b, prj-77aa01cd`. Expand **Evidence ID reference** below the table to look up IDs.

Click **Save skills**.

### Education & certs / Achievements
Edit the tables and click the matching **Save** button. Dates use `YYYY-MM`.

---

## 4. Review and confirm

At the top of Master Profile:

1. Expand **Quality notes** and fix what it lists:
   - *"contains number(s) … without a matching verified metric"*: add the metric, or remove the number from the bullet.
   - *"has no linked evidence"*: add evidence IDs to that skill.
   - *"tags skills not in your skills list"*: add the skill, or fix the spelling.
2. When everything is accurate, click **Confirm profile**.

Any later edit creates a new version and asks you to confirm again.

---

## 5. Create role profiles (Resume Library)

A role profile, such as "ML Engineer" or "NLP Engineer", selects and orders your existing evidence for one kind of job. It never adds new facts.

1. Open **Resume Library** → **➕ New role profile**.
2. Enter a **Name** and an optional **Target job title**.
3. In **Evidence to include (in order)**, pick jobs, projects and bullets in the order you want them to appear.
4. In **Skills to emphasise (in order)**, pick the skills to highlight.
5. Choose a **Target length** of 1 or 2 pages, then click **Create**.

To manage an existing role profile, expand it:
- **Edit:** make changes and click **Save**.
- **Duplicate:** type a new name in **Duplicate as**, then click **Duplicate**.
- **Delete:** tick the confirmation checkbox, then click **Delete**.

If you delete something from the master profile, affected role profiles show a warning, and the missing items are dropped the next time you save them.

---

## 6. Import job descriptions

Open **Job Import**.

### Step 1: bring in the JD

| Tab | How |
|---|---|
| **Paste text** | Copy the whole posting from LinkedIn, Naukri or anywhere else, paste it, then click **Review pasted text**. This always works. |
| **Upload file** | Choose a `.txt`, `.md`, `.pdf` or `.docx` file (up to 5 MB), then click **Extract text**. |
| **From URL** | Enter the job page address, then click **Fetch page**. |

About **From URL**:
- The app fetches that one page, follows the site's robots.txt, and stops at sign-in pages or "are you human" checks. It never logs in or works around them.
- **LinkedIn and Naukri normally refuse automated access, so paste the JD for those.** Company career pages often work.
- If the fetch fails, a red message explains why. Switch to **Paste text**.

### Step 2: review and save

1. Check or fill in **Job title**, **Company**, **Location**, **Platform** and **Source URL**. Pages that publish structured job data prefill these.
2. Read any yellow notes. "General page text" means menus or footers may be mixed in, so delete anything that isn't part of the job posting.
3. Click **Save job**, or **Discard draft** to start over.

### Step 3: handle duplicates

If the job matches one you already saved (same job link, same text, or same company/title/location with nearly the same text), you choose:
- **Update "…" with this import**: replaces the description and source, and keeps your status and notes.
- **Save as a separate job**
- **Back to review**

### Saved jobs

Below the import area, every saved job is listed, newest first. Use **Filter by status** to narrow the list. Expand a job to:
- **Edit** its title, company, location, status, notes or description, then click **Save changes**.
- **Delete** it: tick **Confirm delete**, then click **Delete job**.

To remove every job, open **Delete all job records**, type `DELETE`, and confirm.

> Job text is stored as plain text and is never followed as instructions, even if a posting contains text like "ignore previous instructions".

---

## 7. Analyze a job description

Open **JD Analysis** and choose a job from the list. Each job shows its state: *not analyzed*, 📝 *draft*, or ✅ *confirmed*.

1. Click **Analyze job description**. The app reads the JD on your computer using fixed rules. No AI service is used and nothing is sent online.
2. Check the **Job details**: title, company, location, work arrangement, and minimum/maximum years of experience. Blank title/company/location fields may have been filled in from the JD; check them.
3. Check the **Requirements** table:
   - **Category**: skill, experience, education, certification, responsibility, qualification, or domain.
   - **Importance**: required, preferred, or unspecified. Fix any the parser got wrong.
   - **Requirement** and **Normalized term**: the standard name used for matching (e.g. "Kubernetes" for "k8s").
   - **JD excerpt**, **Confidence** and **Origin** are filled in automatically. Low confidence means "check this one". Rows you add or change are marked *user*.
   - Add a missing requirement in the empty row at the bottom. Delete a wrong one by selecting its row and pressing the delete (trash) icon.
4. Click **Save review**, then **Confirm analysis**.

Good to know:
- The analysis describes **the job only**. A skill appearing here does not mean the app thinks you have it. That comparison comes in the match report.
- If you edit the JD text on **Job Import** later, this page warns that the analysis is out of date. Use **Re-analyze from the JD text** (tick the box first; your edits will be replaced).
- If the JD contains text addressed to an AI, such as "ignore previous instructions", a warning appears. That text is never followed.

---

## 8. Match a job against your profile

Open **Match Report** and choose a job. You need a master profile and a **confirmed** JD analysis.

1. Click **Run matching**. It runs on your computer with fixed rules.
2. Read the summary:
   - **Required / Preferred coverage**: how much of each group your recorded evidence addresses. Open **How these numbers are calculated** for the exact formula. This is *not* a chance of getting hired or an ATS score.
   - **Your judgements**: how many results you have corrected.
3. Read the **Requirements** table. Filter by status or category if it's long.
   - ✅ **supported**: your evidence shows it. **Evidence** lists the items.
   - 🟡 **partial**: something related is there, but not exactly this. For example, you list the skill but no job or project shows it, or you used a *related* tool. **Why** explains which.
   - ⬜ **not documented**: nothing in your profile shows it.
   - **Match** shows how it was found: *exact*, *alias* (another name you recorded, like k8s), *related*, *text_overlap* (similar wording, so check it), or *computed* (from dates or degree level).
4. **Correct a result** if the matcher got something wrong. Pick the requirement, choose a status, select the evidence items that prove it, add a note, and click **Save my judgement**. "Supported" and "partial" need at least one evidence item. If the proof isn't in your profile yet, add it there first. **Clear my judgement** undoes it.
5. Check **Gaps**: required or preferred items with no evidence. If you really have that experience, add it to your master profile and re-run. If you don't, it stays off your resume.
6. **Recommendations** suggest which role profile and projects cover the most matched requirements.

If you edit your profile or the JD analysis afterwards, the page says the report is out of date. Click **Re-run matching**. Your judgements are kept.

---

## 9. Build and approve a tailored resume

Open **Resume Builder** and choose a job. It needs an up-to-date match report.

### Generate a draft
1. Open **➕ Generate a new version**.
2. **Base role profile**: the best fit is preselected and marked *recommended*. You can pick another, or *None*.
3. **Target length**: 1 or 2 pages.
4. Click **Generate draft**. The app picks your most relevant bullets for this job and copies them **word for word** from your profile. Job titles, employers and dates always come from your profile.

### Optional: improve the wording with AI
This appears only if AI rewriting is set up (see the README).
1. Tick **Improve wording with AI**.
2. Open **Exactly what will be sent** and read it. Your name, contact details and employer names are never included.
3. Tick **I agree to send this content…**, then **Generate draft**.

Every AI rewrite is checked. Any that adds a number, skill or tool your profile doesn't show is thrown away and your original wording is kept; **Changes & evidence** tells you which. If the AI service fails, you still get a draft with your original wording.

### Review
- **Preview**: the resume text.
- **Changes & evidence**: for every line, the original, the final wording, where it came from (*from profile*, *AI rewrite (checked)*, *your edit*) and its evidence. **Left out** explains everything that was dropped and why, for example "contains unverified number(s)".

### Edit
On **Edit**, change bullet wording, untick **Include** to drop a bullet, or rewrite the summary. Click **Save as new version**. The previous version is kept unchanged. To change a title, date or degree, edit your master profile and generate again.

### Validate and approve
On **Validate & approve**:
- Red **errors** must be fixed first. Examples: a number or skill your profile doesn't show, or more years of experience than your dated roles add up to.
- Yellow **warnings** need a careful read, for example new names or stronger wording than your profile uses.
- When you're satisfied, tick **I have read this resume… everything in it is accurate**, optionally add a note, and click **Approve this version**.

Approved versions can't be changed. Edit to make a new version instead.

### Export DOCX and PDF
1. Open the **Export** tab of an approved version.
2. Click **Export DOCX and PDF**. The app creates both files and checks them.
3. Read the checks:
   - ✅ passed.
   - ⚠️ review before sending. For example, "Fits target length" means the PDF is longer than your 1- or 2-page target. The app never shrinks text to fit; remove a bullet on **Edit**, or generate with the 2-page target.
   - ❌ don't send these files. For example, content missing from the file, or text too small.
4. Click **Download DOCX** or **Download PDF**. The files are also saved in the `output` folder, under the job's ID.

Use the PDF when an application accepts it (layout is fixed). Use the DOCX when a site asks for Word, or if you want to make your own final tweaks. Changes you make in Word aren't tracked by the app.

To change the paper size (A4/Letter) or template (Classic/Compact), use the **Settings** page, then click **Export again**.

---

## 10. Track your applications

Open **Application Tracker**.

1. The counters show how many jobs are *saved*, *applied*, *interviewing*, at *offer*, or *rejected*. A yellow banner lists follow-ups that are due.
2. Narrow the table with **Status**, **Platform**, **Search** or **Follow-up due**.
3. Under **Update an application**, pick a job and set:
   - **Status**. If you mark it *applied* without a date, today's date is filled in; change it if you applied earlier.
   - **Applied on** and **Follow up on**. The follow-up can't be before the applied date.
   - **Resume used**: the version you actually sent. Approved versions are listed first.
   - **Notes**, then click **Save**.
4. **Download DOCX/PDF used** gets the exact files you sent for that job.
5. **Download CSV of these jobs** saves the filtered table for a spreadsheet. Tick **Include JD text** to add the descriptions.
6. **Possible duplicates** appears if two jobs look like the same posting. Choose which to **Keep**, read what the other record's deletion will remove, tick **Merge these two**, and click **Merge**.
7. **Delete this job** removes the job and everything made from it, including exported files.

---

## 11. Settings, privacy and your data

Open **Settings**.

- **Local-only mode**: when on, the app never goes online. URL import and AI rewriting are switched off.
- **AI rewriting**: choose *None*, *Anthropic* or *OpenAI*, and optionally a model. API keys are never typed into the app. Put them in your `.env` file (`ANTHROPIC_API_KEY=…` or `OPENAI_API_KEY=…`) and restart. The page only says whether a key is *detected*.
- **Template** (*Classic* or *Compact*) and **Paper size** (*A4* or *Letter*) apply to your next export.
- **Allow best-effort import from a job URL** turns URL import on or off.
- Click **Save settings**. A greyed-out field is set in your `.env` file. Change it there and restart.

**What is stored and what is sent** lists exactly where your data lives and when anything leaves your computer.

**Your data**:
- **Prepare data export**, then **Download all my data (.zip)**: everything, optionally with exported files. The archive contains personal data, so keep it private.
- **Delete everything**: type `DELETE EVERYTHING` and click **Delete all my data**. This removes your profile and all its versions, role profiles, jobs, resumes, exported files and settings. It can't be undone.

---

## 12. Optional: capture JDs with the browser extension

Instead of copy-pasting, you can send a job description from Chrome or Edge with one click. It only reads the page you're looking at, only when you click it, and only after you confirm.

**Set up once**
1. **Settings → Browser extension**: turn on **Accept job descriptions from the browser extension** and click **Save settings**.
2. Open a second PowerShell window in `D:\Resume_Optimizer` and run:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m src.extension_receiver
   ```
   Leave it running while you capture. Close it with `Ctrl+C`.
3. In Chrome, go to `chrome://extensions` (Edge: `edge://extensions`), switch on **Developer mode**, click **Load unpacked**, and pick the `browser_extension` folder.
4. Back in **Settings**, tick **Show pairing token** and copy it. In the extension's **Pairing settings**, paste the token, check the port (default 8765), click **Save**, then **Test connection**.

**Capture a job**
1. Open the job posting. Expand "see more" if there is one, and select the job description text. Selecting gives the cleanest result.
2. Click the extension. Check **Source**, fix the title, company or location, and delete anything that isn't part of the posting.
3. Tick **I reviewed this text…** and click **Send for review**.
4. In the app, open **Job Import → From browser**, then **Review and save** (or **Discard**).

If the extension says it **couldn't reach Resume Optimizer**, the receiver isn't running, the port differs, or the extension is switched off in Settings. **Generate a new token** in Settings un-pairs the extension; paste the new token into it.

---

## 13. Back up, restore and delete

All of these are on the **Import / export** and **History** tabs:

- **Back up:** **Download profile JSON**. Keep it somewhere safe.
- **Restore an old version:** on **History**, choose a version, check **View contents**, then click **Restore vN as a new version**. Old versions are never overwritten.
- **Bulk edit:** on **Raw JSON**, edit the whole profile, then click **Validate and save**. Invalid data is rejected with the field name.
- **Delete everything:** type `DELETE`, then click **Delete all profile data**. This removes the profile, all versions and role profiles, and cannot be undone. Download a backup first.

---

## 14. Troubleshooting

| Problem | Fix |
|---|---|
| "date must be in YYYY-MM format" | Use `2023-07`, not `July 2023` or `2023`. |
| "end_date … is before start_date" | Check the order of the dates. |
| "references unknown evidence IDs" | A skill lists an ID that doesn't exist. Copy it from **Evidence ID reference**. |
| "duplicate skill names" | The same skill is listed twice (case doesn't matter). |
| "No changes to save." | Nothing changed, so no new version was created. |
| "Saved profile file is unreadable" | Import your backup JSON, or restore a version from **History**. |
| App crashes with a numpy/pandas error | You started it without the `.venv`. Activate it first (step 1). |
| `Activate.ps1` is blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. |
| "This site does not permit automated access…" or "refuses automated access" | Expected for LinkedIn and Naukri. Paste the JD text instead. |
| "No selectable text found in this PDF" | The PDF is a scanned image. Copy the text from the original posting and paste it. |
| "Too little text was found on the page" | The site loads the job with JavaScript. Paste the JD text instead. |
| "That address points to a local or private network" | Only public web pages can be imported. |
| "No clear requirements section was found" | The JD has no headings the parser knows. Check each requirement's importance by hand. |
| "Several different experience ranges were found" | Enter the overall minimum/maximum years yourself. |
| A skill is missing from the requirements | Add a row at the bottom of the table, or add the skill to your master profile so it is recognized next time. |
| "Input should be a valid number" when saving | A Min/Max yrs cell contains text. Enter a number or clear the cell. |
| "Confirm this job's analysis…" on Match Report | Open **JD Analysis**, review the job, and click **Confirm analysis**. |
| "must cite at least one evidence item" | Select the evidence that proves it, or add that evidence to your master profile first. |
| A skill you have shows "partial: in your skills list, but no evidence" | On **Master Profile → Skills**, link the skill to the jobs, projects or bullets that show it, or mention it in a bullet. |
| "This report is out of date" | Your profile or the JD analysis changed. Click **Re-run matching**. |
| "AI rewriting is off" on Resume Builder | Choose a provider on **Settings** and add its API key to `.env` (then restart). Check that local-only mode is off. Drafts work without AI. |
| "AI rewriting failed: … rejected the API key" | Check `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. The draft was saved with your original wording. |
| A bullet you expected is missing | See **Changes & evidence → Left out**. A common reason is a number without a verified metric; add one on the Master Profile page. |
| "Adds number(s) not in the source" | Remove the number, or add it as a verified metric in your master profile and generate again. |
| **Generate draft** is greyed out | The match report is out of date, or AI is ticked but consent isn't. Re-run matching or tick the consent box. |
| Export says "Approve this version…" | Approve it on **Validate & approve** first. Only approved versions can be exported. |
| "Fits target length" warning | Remove bullets on **Edit** (new version, approve, export), or generate with the 2-page target. |
| "Could not write the files" | A previous export is open in Word or a PDF viewer. Close it and click **Export again**. |
| "The fallback font can't draw: …" | No Arial/DejaVu/Liberation font was found. Set `RESUME_OPTIMIZER_PDF_FONT` (and `_BOLD`) in `.env` to a `.ttf` file. |
| A Settings field is greyed out | It's set in your `.env` file, which takes priority. Edit or blank that line, then restart the app. |
| "The follow-up date is before the applied date" | Pick a follow-up date on or after the applied date. |
| URL import tab says it's unavailable | URL import is switched off, or local-only mode is on. Change it on **Settings**. |
| Extension: "Couldn't reach Resume Optimizer" | Start `python -m src.extension_receiver`, check the port matches, and that the extension is turned on in **Settings**. |
| Extension: "Pairing token missing or wrong" | Copy the token again from **Settings** (tick **Show pairing token**) into the extension's Pairing settings. |
| Extension: "This page can't be captured" | It only works on normal http/https pages, not on browser pages like the new-tab page or PDFs. |
