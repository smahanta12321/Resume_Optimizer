# AI Resume Optimizer — User Manual

**Covers:** Milestone 1 (Master Profile and Resume Library). Job import, matching, resume drafting and export will be added in later versions.

The app keeps one **master profile**, a verified record of your career. Every tailored resume will be built only from facts in it, so accuracy here matters most.

---

## 1. Start the app

1. Open PowerShell in `D:\Resume_Optimizer`.
2. Run:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   streamlit run app.py
   ```
3. Your browser opens at **http://localhost:8501**. Use the sidebar to switch between **Dashboard**, **Master Profile** and **Resume Library**.
4. To stop the app, press `Ctrl+C` in the terminal.

> Everything stays on your computer in the `data/` folder. Nothing is sent online.

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

## 6. Back up, restore and delete

All of these are on the **Import / export** and **History** tabs:

- **Back up:** **Download profile JSON**. Keep it somewhere safe.
- **Restore an old version:** on **History**, choose a version, check **View contents**, then click **Restore vN as a new version**. Old versions are never overwritten.
- **Bulk edit:** on **Raw JSON**, edit the whole profile, then click **Validate and save**. Invalid data is rejected with the field name.
- **Delete everything:** type `DELETE`, then click **Delete all profile data**. This removes the profile, all versions and role profiles, and cannot be undone. Download a backup first.

---

## 7. Troubleshooting

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
