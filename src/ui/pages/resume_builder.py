"""Resume Builder: generate an evidence-backed draft, review changes, edit, validate, approve."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from src.config import get_settings
from src.persistence.job_store import JobStore, JobStoreError
from src.persistence.profile_store import ProfileStoreError
from src.schemas.analysis import JDAnalysis
from src.schemas.job import Job
from src.schemas.match import MatchReport
from src.schemas.profile import MasterProfile, RoleProfile, TargetLength
from src.schemas.export import CheckStatus
from src.schemas.resume import ResumeContent, ResumeVersion, TextOrigin
from src.services.export_service import ExportError, export_version
from src.services.render.style import TEMPLATES
from src.services.llm.provider import get_provider, provider_status
from src.services.match_report_service import recommend_role_profiles, stale_reasons
from src.services.resume_generator import build_draft
from src.services.resume_rewriter import build_request
from src.services.resume_service import apply_user_edits, generate_version
from src.services.resume_validation import change_summary, validate_resume
from src.ui.state import flash, get_job_store, get_store, sample_banner, show_flashes

SELECTED_JOB = "builder_job_id"
ORIGIN_LABEL = {TextOrigin.VERBATIM: "from profile", TextOrigin.REWRITTEN: "AI rewrite (checked)",
                TextOrigin.USER_EDIT: "your edit"}


def _version_key(job_id: str) -> str:
    return f"builder_version_{job_id}"


def _dates(start: Optional[str], end: Optional[str]) -> str:
    if not start and not end:
        return ""
    return f"{start or '?'} – {end or 'Present'}"


def render_markdown(c: ResumeContent) -> str:
    """Plain single-column preview. The exported DOCX/PDF layout comes in the next milestone."""
    contact = " · ".join(x for x in [c.contact.email, c.contact.phone, c.contact.location,
                                     *[l.url for l in c.contact.links]] if x)
    out = [f"## {c.contact.full_name}"]
    if c.headline:
        out.append(f"**{c.headline}**")
    if contact:
        out.append(contact)
    if c.summary.text:
        out += ["#### Summary", c.summary.text]
    if c.skills:
        out += ["#### Skills", ", ".join(s.name for s in c.skills)]
    for heading, entries in (("Experience", c.experience), ("Projects", c.projects)):
        if entries:
            out.append(f"#### {heading}")
            for e in entries:
                org = f", {e.organization}" if e.organization else ""
                when = _dates(e.start_date, e.end_date)
                out.append(f"**{e.title}**{org}" + (f" | {e.location}" if e.location else "") + (f" | {when}" if when else ""))
                out += [f"- {b.text}" for b in e.bullets]
    if c.education:
        out.append("#### Education")
        out += [f"**{e.degree}**" + (f", {e.field_of_study}" if e.field_of_study else "") + f", {e.institution}"
                + (f" | {_dates(e.start_date, e.end_date)}" if e.start_date or e.end_date else "") for e in c.education]
    if c.certifications:
        out.append("#### Certifications")
        out += [f"- {x.name}" + (f", {x.issuer}" if x.issuer else "") + (f" ({x.issue_date})" if x.issue_date else "")
                for x in c.certifications]
    return "\n\n".join(out)


def render() -> None:
    st.title("Resume Builder")
    st.caption("Builds a tailored resume only from your master profile. Every line cites the evidence behind it. "
               "Nothing is exported or sent anywhere until you approve it, and the app never applies to jobs.")
    show_flashes()
    store = get_job_store()
    try:
        profile = get_store().load()
        roles = get_store().load_roles().role_profiles
    except ProfileStoreError as exc:
        st.error(f"Your master profile could not be loaded. {exc}")
        return
    if profile is None:
        st.warning("Create or import a master profile first (Master Profile page).")
        return
    try:
        jobs = store.list()
        reported = store.match_report_ids()
    except JobStoreError as exc:
        st.error(f"Saved jobs could not be loaded. {exc}")
        return
    candidates = [j for j in jobs if j.id in reported]
    if not candidates:
        st.info("No matched jobs yet. Run matching on the **Match Report** page first.")
        return
    sample_banner(profile.is_sample)

    by_id = {j.id: j for j in candidates}
    ids = list(by_id)
    default = st.session_state.get(SELECTED_JOB)
    job_id = st.selectbox("Job", ids, index=ids.index(default) if default in ids else 0,
                          format_func=lambda i: f"{by_id[i].display_name} ({by_id[i].imported_at:%Y-%m-%d})")
    st.session_state[SELECTED_JOB] = job_id
    job = by_id[job_id]
    try:
        analysis = store.get_analysis(job.id)
        report = store.get_match_report(job.id)
        versions = store.list_resume_versions(job.id)
    except JobStoreError as exc:
        st.error(str(exc))
        return
    if analysis is None or report is None:
        st.info("This job needs a confirmed analysis and a match report first.")
        return
    reasons = stale_reasons(report, analysis, profile)
    if reasons:
        st.warning("The match report is out of date: " + " ".join(reasons)
                   + " Re-run matching on the **Match Report** page before generating a new version.")

    _generate_panel(store, job, profile, analysis, report, roles, disabled=bool(reasons))
    if not versions:
        st.info("No resume versions for this job yet.")
        return
    version = _pick_version(job, versions)
    _version_view(store, version, profile, analysis, report)


def _generate_panel(store: JobStore, job: Job, profile: MasterProfile, analysis: JDAnalysis, report: MatchReport,
                    roles: list[RoleProfile], disabled: bool) -> None:
    with st.expander("➕ Generate a new version", expanded=not store.list_resume_versions(job.id)):
        recs = recommend_role_profiles(report, analysis, profile, roles)
        options: list[Optional[str]] = [None] + [r.id for r in roles]
        names = {r.id: r.name for r in roles}
        best = recs[0].id if recs else None
        role_id = st.selectbox(
            "Base role profile", options, index=options.index(best) if best in options else 0,
            format_func=lambda i: "None (rank evidence by this job only)" if i is None
            else names[i] + ("  (recommended)" if i == best else ""), key=f"gen-role-{job.id}")
        pages = st.radio("Target length", list(TargetLength), horizontal=True, key=f"gen-pages-{job.id}",
                         format_func=lambda t: f"{int(t)} page" + ("s" if int(t) > 1 else ""))
        role = next((r for r in roles if r.id == role_id), None)

        status = provider_status(get_settings())
        use_ai = consent = False
        if status.available:
            use_ai = st.checkbox(f"Improve wording with AI ({status.provider}, {status.model})", key=f"gen-ai-{job.id}",
                                 help="Rewrites are checked automatically. Any rewrite that adds numbers, skills or "
                                      "tools is discarded and your original wording is kept.")
            st.caption(status.message)
            if use_ai:
                content, _ = build_draft(profile, analysis, report, role=role, target_pages=pages)
                request = build_request(content, profile, analysis, report, job.title)
                st.warning(f"This sends the text below to **{status.provider}**, an external service. Your name, "
                           "contact details and employer names are not included.")
                with st.expander("Exactly what will be sent"):
                    st.code(request.system + "\n\n---\n\n" + request.user, language="markdown")
                consent = st.checkbox(f"I agree to send this content to {status.provider}.", key=f"gen-consent-{job.id}")
        else:
            st.caption(status.message)

        if st.button("Generate draft", type="primary", disabled=disabled or (use_ai and not consent),
                     key=f"gen-btn-{job.id}"):
            provider = get_provider(get_settings()) if use_ai and consent else None
            with st.spinner("Generating…" if provider is None else f"Generating and asking {status.provider}…"):
                outcome = generate_version(job, profile, analysis, report, role=role, target_pages=pages,
                                           provider=provider)
            try:
                saved = store.add_resume_version(outcome.version)
            except JobStoreError as exc:
                st.error(f"Could not save the draft. {exc}")
                return
            st.session_state[_version_key(job.id)] = saved.id
            if outcome.ai_failed:
                flash("warning", f"AI rewriting failed: {outcome.ai_failed} Saved the draft with your original wording.")
            for note in outcome.notes:
                flash("info", note)
            flash("success", f"Created version `{saved.id}`. Review it below before approving.")
            st.rerun()


def _pick_version(job: Job, versions: list[ResumeVersion]) -> ResumeVersion:
    ids = [v.id for v in versions]
    by_id = {v.id: v for v in versions}
    key = _version_key(job.id)
    default = st.session_state.get(key)
    vid = st.selectbox(
        "Version", ids, index=ids.index(default) if default in ids else 0,
        format_func=lambda i: f"{i} · {by_id[i].created_at:%Y-%m-%d %H:%M} · {by_id[i].generator}"
        + (" · ✅ approved" if by_id[i].approved_at else "") + (f" · edited from {by_id[i].parent_id}"
                                                               if by_id[i].parent_id else ""))
    st.session_state[key] = vid
    return by_id[vid]


def _version_view(store: JobStore, version: ResumeVersion, profile: MasterProfile, analysis: JDAnalysis,
                  report: MatchReport) -> None:
    validation = validate_resume(version, profile, analysis=analysis, report=report)
    preview, changes, edit, approve, export = st.tabs(
        ["Preview", "Changes & evidence", "Edit", "Validate & approve", "Export"])
    with preview:
        if version.approved_at:
            st.success(f"Approved on {version.approved_at:%Y-%m-%d %H:%M} UTC.")
        st.markdown(render_markdown(version.content))
    with changes:
        rows = change_summary(version, profile)
        if rows:
            st.dataframe(pd.DataFrame([vars(r) for r in rows]).rename(columns=str.capitalize), hide_index=True,
                         column_config={"Original": st.column_config.TextColumn(width="large"),
                                        "Final": st.column_config.TextColumn(width="large")})
        notes = [(e.title, b) for e in [*version.content.experience, *version.content.projects] for b in e.bullets
                 if b.notes]
        for title, b in notes:
            st.caption(f"⚠️ {title}: “{b.text[:70]}”: " + " ".join(b.notes))
        if version.content.summary.notes:
            st.caption("Summary: " + " ".join(version.content.summary.notes))
        st.markdown("**Skills and their evidence**")
        st.dataframe(pd.DataFrame([{"Skill": s.name, "Evidence": ", ".join(s.evidence_ids)}
                                   for s in version.content.skills]), hide_index=True)
        if version.omitted:
            st.markdown("**Left out**")
            st.markdown("\n".join(f"- {o}" for o in version.omitted))
    with edit:
        _edit_form(store, version)
    with approve:
        _approval(store, version, validation)
    with export:
        _export(store, version)


def _edit_form(store: JobStore, version: ResumeVersion) -> None:
    st.caption("Saving creates a new version; this one stays unchanged. Titles, employers, dates and education come "
               "from your master profile and are edited there. Edits that add numbers, skills or tools your "
               "evidence doesn't show will fail validation.")
    with st.form(f"edit-{version.id}"):
        summary = st.text_area("Summary", value=version.content.summary.text, height=100)
        frames = {}
        for entry in [*version.content.experience, *version.content.projects]:
            st.markdown(f"**{entry.title}**" + (f", {entry.organization}" if entry.organization else ""))
            df = pd.DataFrame([{"include": True, "text": b.text, "evidence": b.evidence_ids[0],
                                "origin": ORIGIN_LABEL[b.origin]} for b in entry.bullets],
                              columns=["include", "text", "evidence", "origin"])
            frames[entry.evidence_id] = st.data_editor(
                df, key=f"edit-{version.id}-{entry.evidence_id}", hide_index=True, num_rows="fixed",
                column_config={"include": st.column_config.CheckboxColumn("Include"),
                               "text": st.column_config.TextColumn("Bullet", width="large"),
                               "evidence": st.column_config.TextColumn("Evidence", disabled=True),
                               "origin": st.column_config.TextColumn("Source", disabled=True)})
        save = st.form_submit_button("Save as new version", type="primary")
    if not save:
        return
    edits = {}
    for entry_id, df in frames.items():
        for row in df.to_dict("records"):
            edits[(entry_id, row["evidence"])] = (bool(row["include"]), str(row["text"] or ""))
    new = apply_user_edits(version, summary_text=summary, bullets=edits)
    if new is version:
        st.info("No changes to save.")
        return
    try:
        saved = store.add_resume_version(new)
    except JobStoreError as exc:
        st.error(f"Could not save. {exc}")
        return
    st.session_state[_version_key(version.job_id)] = saved.id
    flash("success", f"Saved your edits as version `{saved.id}`. Check **Validate & approve**.")
    st.rerun()


def _approval(store: JobStore, version: ResumeVersion, validation) -> None:
    st.caption(f"Estimated length: about {validation.estimated_lines} lines for a {int(version.target_pages)}-page "
               "target. Exact page count is checked at export.")
    for e in validation.errors:
        st.error(e)
    for w in validation.warnings:
        st.warning(w)
    for i in validation.info:
        st.info(i)
    if validation.ok and not validation.warnings:
        st.success("All checks passed.")
    if version.approved_at:
        st.success(f"Approved on {version.approved_at:%Y-%m-%d %H:%M} UTC"
                   + (f": {version.approval_note}" if version.approval_note else "."))
        return
    if not validation.ok:
        st.markdown("Fix the errors above (edit this version, or update your master profile and generate again) "
                    "before approving.")
        return
    confirm = st.checkbox("I have read this resume and its warnings, and everything in it is accurate.",
                          key=f"approve-chk-{version.id}")
    note = st.text_input("Approval note (optional)", key=f"approve-note-{version.id}")
    if st.button("Approve this version", type="primary", disabled=not confirm, key=f"approve-{version.id}"):
        try:
            store.approve_resume_version(version.id, note)
        except JobStoreError as exc:
            st.error(str(exc))
            return
        flash("success", "Approved. Open the **Export** tab to create the DOCX and PDF.")
        st.rerun()


STATUS_ICON = {CheckStatus.PASS: "✅", CheckStatus.WARN: "⚠️", CheckStatus.FAIL: "❌"}


def _export(store: JobStore, version: ResumeVersion) -> None:
    if not version.approved_at:
        st.info("Approve this version on **Validate & approve** before exporting it.")
        return
    settings = get_settings()
    try:
        record = store.get_export(version.id)
    except JobStoreError as exc:
        st.error(str(exc))
        record = None
    st.caption(f"Single-column, ATS-friendly “{settings.template}” template · {settings.page_size} paper · "
               f"files go to `{settings.output_dir}`. Change template and paper on the **Settings** page.")
    label = "Export DOCX and PDF" if record is None else "Export again"
    if st.button(label, type="primary" if record is None else "secondary", key=f"export-{version.id}"):
        job = store.get(version.job_id)
        try:
            with st.spinner("Rendering and checking files…"):
                record = export_version(version, output_dir=settings.output_dir, page_size=settings.page_size,
                                        style=TEMPLATES[settings.template],
                                        company=job.company if job else "", role=job.title if job else "")
            store.save_export(record)
        except (ExportError, JobStoreError) as exc:
            st.error(str(exc))
            return
        flash("success" if not record.failed else "error",
              "Exported. Review the checks below." if not record.failed
              else "Exported, but some checks failed. See below before using these files.")
        st.rerun()
    if record is None:
        return

    if record.failed:
        st.error(f"{len(record.failed)} check(s) failed. Don't send these files until the problems are resolved.")
    elif record.warnings:
        st.warning(f"{len(record.warnings)} warning(s). Review them before sending.")
    else:
        st.success("All export checks passed.")
    st.dataframe(pd.DataFrame([{"": STATUS_ICON[c.status], "File": c.file.upper(), "Check": c.name,
                                "Detail": c.detail} for c in record.checks]), hide_index=True,
                 column_config={"Detail": st.column_config.TextColumn(width="large")})
    st.caption(f"PDF: {record.pdf_pages} page(s), template {record.renderer}, {record.page_size}, font "
               f"{record.pdf_font}. Exported {record.created_at:%Y-%m-%d %H:%M} UTC.")
    c1, c2 = st.columns(2)
    for col, path, mime, label in (
        (c1, record.docx_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "DOCX"),
        (c2, record.pdf_path, "application/pdf", "PDF"),
    ):
        file = Path(path)
        if file.is_file():
            col.download_button(f"Download {label}", data=file.read_bytes(), file_name=file.name, mime=mime,
                                key=f"dl-{label}-{version.id}")
        else:
            col.warning(f"The {label} file is no longer at {path}. Export again.")
