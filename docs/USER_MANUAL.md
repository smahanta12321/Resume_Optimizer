# AI Resume Optimizer — User Manual

**Covers:** Milestones 1–3 (Master Profile, Resume Library, Job Import and JD Analysis). Matching, resume drafting and export will be added in later versions.

The app keeps one **master profile**, a verified record of your career. Every tailored resume will be built only from facts in it, so accuracy here matters most.

---

## 1. Start the app

1. Open PowerShell in `D:\Resume_Optimizer`.
2. Run:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   streamlit run app.py
   ```
3. Your browser opens at **http://localhost:8501**. Use the sidebar to switch between **Dashboard**, **Master Profile**, **Resume Library**, **Job Import** and **JD Analysis**.
4. To stop the app, press `Ctrl+C` in the terminal.

> Everything stays on your computer in the `data/` folder. The only time the app goes online is when you ask it to fetch a job page by URL, and then it contacts only that site.

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

## 8. Back up, restore and delete

All of these are on the **Import / export** and **History** tabs:

- **Back up:** **Download profile JSON**. Keep it somewhere safe.
- **Restore an old version:** on **History**, choose a version, check **View contents**, then click **Restore vN as a new version**. Old versions are never overwritten.
- **Bulk edit:** on **Raw JSON**, edit the whole profile, then click **Validate and save**. Invalid data is rejected with the field name.
- **Delete everything:** type `DELETE`, then click **Delete all profile data**. This removes the profile, all versions and role profiles, and cannot be undone. Download a backup first.

---

## 9. Troubleshooting

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
