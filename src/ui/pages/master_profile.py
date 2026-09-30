"""Master Profile page: create, import, edit, review/confirm, export, history."""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from src.persistence.profile_store import ProfileStore, ProfileStoreError
from src.schemas.profile import (
    Achievement,
    Bullet,
    Certification,
    Contact,
    Education,
    Experience,
    Link,
    MasterProfile,
    Project,
    Skill,
    SkillCategory,
)
from src.services.profile_service import (
    MAX_IMPORT_BYTES,
    ProfileImportError,
    export_profile_json,
    format_validation_error,
    load_sample_profile,
    parse_profile_json,
    profile_warnings,
    prune_removed_evidence,
)
from src.ui.state import flash, get_store, sample_banner, show_flashes
from src.ui.table_convert import join_csv, models_to_rows, rows_to_models, split_csv

BULLET_COLS = ["id", "text", "skills", "source_note", "verified_metrics"]
ID_COL = st.column_config.TextColumn("ID", disabled=True, help="Stable evidence ID (auto-generated)")


# ---- helpers ----------------------------------------------------------------


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts with NaN converted to None."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


def _save(store: ProfileStore, profile: MasterProfile) -> None:
    """Validate and save as a new version, then rerun with a status message."""
    try:
        before = store.load()
    except ProfileStoreError:
        before = None
    notes: list[str] = []
    if before is not None:
        profile, notes = prune_removed_evidence(before, profile)
    try:
        saved = store.save_new_version(profile)
    except ValueError as exc:  # includes pydantic.ValidationError
        _show_error(exc)
        return
    if before is not None and saved.profile_version == before.profile_version:
        flash("info", "No changes to save.")
    else:
        flash("success", f"Saved as profile version {saved.profile_version}. Please review and confirm it.")
    for note in notes:
        flash("warning", note)
    st.rerun()


def _show_error(exc: Exception) -> None:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        st.error("Could not save — please fix:\n" + format_validation_error(exc))  # type: ignore[arg-type]
    else:
        st.error(f"Could not save: {exc}")


def _evidence_label(kind: str, item) -> str:
    if kind == "experience":
        return f"{item.title} @ {item.employer}"
    if kind == "project":
        return f"Project: {item.name}"
    if kind == "bullet":
        return f"• {item.text[:80]}"
    if kind == "education":
        return f"{item.degree}, {item.institution}"
    if kind == "certification":
        return f"Cert: {item.name}"
    return f"Achievement: {getattr(item, 'title', '')}"


# ---- page -------------------------------------------------------------------


def render() -> None:
    st.title("Master Profile")
    st.caption("Your verified source of truth. Resumes may only use facts recorded here.")
    show_flashes()
    store = get_store()

    try:
        profile = store.load()
    except ProfileStoreError as exc:
        st.error(f"The saved profile file is unreadable: {exc}")
        st.markdown("You can import a JSON backup below, or restore an earlier saved version.")
        _import_section(store)
        _history_section(store)
        return

    if profile is None:
        _onboarding(store)
        return

    sample_banner(profile.is_sample)
    _status_section(store, profile)

    tabs = st.tabs(
        ["Contact & summary", "Experience", "Projects", "Skills", "Education & certs",
         "Achievements", "Import / export", "History", "Raw JSON"]
    )
    with tabs[0]:
        _contact_tab(store, profile)
    with tabs[1]:
        _entries_tab(store, profile, "experience")
    with tabs[2]:
        _entries_tab(store, profile, "projects")
    with tabs[3]:
        _skills_tab(store, profile)
    with tabs[4]:
        _education_tab(store, profile)
    with tabs[5]:
        _achievements_tab(store, profile)
    with tabs[6]:
        _export_section(store, profile)
        st.divider()
        _import_section(store)
        st.divider()
        _delete_section(store)
    with tabs[7]:
        _history_section(store)
    with tabs[8]:
        _raw_json_tab(store, profile)


def _onboarding(store: ProfileStore) -> None:
    st.info("No master profile yet. Choose how to start.")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Create from scratch")
        with st.form("create_blank"):
            name = st.text_input("Full name *")
            email = st.text_input("Email")
            if st.form_submit_button("Create profile", type="primary"):
                try:
                    profile = MasterProfile(contact=Contact(full_name=name, email=email))
                except ValueError as exc:
                    _show_error(exc)
                else:
                    _save(store, profile)
        st.subheader("Try the sample")
        st.caption("Loads a clearly fictional profile for exploring the app. Replace it before real use.")
        if st.button("Load fictional sample profile"):
            _save(store, load_sample_profile())
    with c2:
        _import_section(store)


def _status_section(store: ProfileStore, profile: MasterProfile) -> None:
    warnings = profile_warnings(profile)
    c1, c2 = st.columns([3, 1])
    with c1:
        if profile.confirmed_at:
            st.success(
                f"Version {profile.profile_version} reviewed and confirmed on "
                f"{profile.confirmed_at:%Y-%m-%d %H:%M} UTC."
            )
        else:
            st.warning(f"Version {profile.profile_version} is not confirmed. Review it, then confirm.")
    with c2:
        if not profile.confirmed_at and st.button("Confirm profile", type="primary",
                                                  help="Confirms every entry is accurate and yours"):
            store.mark_confirmed()
            flash("success", f"Profile version {profile.profile_version} confirmed.")
            st.rerun()
    if warnings:
        with st.expander(f"Quality notes ({len(warnings)}) — review before relying on this profile"):
            for w in warnings:
                st.markdown(f"- {w.message}" + (f"  `{w.item_id}`" if w.item_id else ""))


# ---- tabs -------------------------------------------------------------------


def _contact_tab(store: ProfileStore, profile: MasterProfile) -> None:
    c = profile.contact
    with st.form("contact_form"):
        col1, col2 = st.columns(2)
        full_name = col1.text_input("Full name *", c.full_name)
        email = col2.text_input("Email", c.email)
        phone = col1.text_input("Phone", c.phone)
        location = col2.text_input("Location", c.location)
        headline = st.text_input("Headline", profile.headline)
        summary = st.text_area("Summary", profile.summary, height=120,
                               help="Only include statements you can support with the entries below.")
        st.markdown("**Links**")
        links_df = st.data_editor(
            _frame(models_to_rows(c.links, ["id", "label", "url"]), ["id", "label", "url"]),
            num_rows="dynamic", key="links_editor",
            column_config={"id": ID_COL},
        )
        if st.form_submit_button("Save contact & summary", type="primary"):
            try:
                links = rows_to_models(_records(links_df), Link, c.links)
                contact = Contact(full_name=full_name, email=email, phone=phone, location=location, links=links)
            except ValueError as exc:
                _show_error(exc)
                return
            _save(store, profile.model_copy(update={"contact": contact, "headline": headline, "summary": summary}))


def _entries_tab(store: ProfileStore, profile: MasterProfile, section: str) -> None:
    """Shared editor for experience and projects (each with bullets)."""
    items = getattr(profile, section)
    is_exp = section == "experience"
    if not items:
        st.caption(f"No {section} entries yet.")
    for item in items:
        label = (f"{item.title} — {item.employer}" if is_exp else item.name)
        dates = f"{item.start_date or '?'} – {item.end_date or 'present'}"
        with st.expander(f"{label}  ({dates})  ·  {item.id}"):
            _entry_form(store, profile, section, item)
            if st.checkbox("I want to delete this entry", key=f"del-chk-{item.id}"):
                if st.button("Delete entry", key=f"del-{item.id}"):
                    remaining = [i for i in items if i.id != item.id]
                    _save(store, profile.model_copy(update={section: remaining}))
    with st.expander(f"➕ Add {'experience' if is_exp else 'project'}"):
        _entry_form(store, profile, section, None)


def _entry_form(store: ProfileStore, profile: MasterProfile, section: str, item) -> None:
    is_exp = section == "experience"
    key = item.id if item else f"new-{section}"
    with st.form(f"form-{key}"):
        col1, col2 = st.columns(2)
        values: dict = {}
        if is_exp:
            values["employer"] = col1.text_input("Employer *", item.employer if item else "")
            values["title"] = col2.text_input("Job title *", item.title if item else "")
            values["location"] = col1.text_input("Location", item.location if item else "")
            values["employment_type"] = col2.text_input("Employment type", item.employment_type if item else "")
        else:
            values["name"] = col1.text_input("Project name *", item.name if item else "")
            values["role"] = col2.text_input("Your role", item.role if item else "")
            values["url"] = col1.text_input("URL", item.url if item else "")
            exp_opts: list[Optional[str]] = [None] + [e.id for e in profile.experience]
            exp_names = {e.id: f"{e.title} @ {e.employer}" for e in profile.experience}
            current = item.related_experience_id if item else None
            values["related_experience_id"] = col2.selectbox(
                "Related experience", exp_opts,
                index=exp_opts.index(current) if current in exp_opts else 0,
                format_func=lambda i: "— none —" if i is None else exp_names[i],
            )
        values["start_date"] = col1.text_input("Start (YYYY-MM)", (item.start_date or "") if item else "")
        values["end_date"] = col2.text_input("End (YYYY-MM, blank = current)", (item.end_date or "") if item else "")
        values["description"] = st.text_area("Description", item.description if item else "", height=80)
        skills_text = st.text_input("Skills (comma-separated)", join_csv(item.skills) if item else "")
        values["source_note"] = st.text_input("Source note (where this can be verified)",
                                              item.source_note if item else "")
        st.markdown("**Bullets** — one factual statement per row. Metrics: `label=value; label=value` "
                    "(only numbers you can verify).")
        bullets = item.bullets if item else []
        bullets_df = st.data_editor(
            _frame(models_to_rows(bullets, BULLET_COLS, list_fields=("skills",),
                                  metric_fields=("verified_metrics",)), BULLET_COLS),
            num_rows="dynamic", key=f"bullets-{key}",
            column_config={
                "id": ID_COL,
                "text": st.column_config.TextColumn("Bullet text", width="large"),
                "skills": st.column_config.TextColumn("Skills (comma-sep.)"),
                "source_note": st.column_config.TextColumn("Source note"),
                "verified_metrics": st.column_config.TextColumn("Verified metrics"),
            },
        )
        if st.form_submit_button("Save" if item else "Add", type="primary"):
            try:
                values["skills"] = split_csv(skills_text)
                values["bullets"] = rows_to_models(
                    _records(bullets_df), Bullet, bullets,
                    list_fields=("skills",), metric_fields=("verified_metrics",),
                )
                model_cls = Experience if is_exp else Project
                base = item.model_dump() if item else {}
                new_item = model_cls.model_validate({**base, **values})
            except ValueError as exc:
                _show_error(exc)
                return
            items = getattr(profile, section)
            updated = [new_item if i.id == new_item.id else i for i in items] if item else [*items, new_item]
            _save(store, profile.model_copy(update={section: updated}))


def _skills_tab(store: ProfileStore, profile: MasterProfile) -> None:
    st.caption(
        "Aliases are exact alternative names (e.g. 'k8s' for Kubernetes), not related concepts. "
        "Link each skill to the evidence IDs that demonstrate it."
    )
    cols = ["id", "name", "category", "aliases", "evidence_ids"]
    with st.form("skills_form"):
        df = st.data_editor(
            _frame(models_to_rows(profile.skills, cols, list_fields=("aliases", "evidence_ids")), cols),
            num_rows="dynamic", key="skills_editor",
            column_config={
                "id": ID_COL,
                "name": st.column_config.TextColumn("Skill", required=True),
                "category": st.column_config.SelectboxColumn(
                    "Category", options=[c.value for c in SkillCategory], default="other"),
                "aliases": st.column_config.TextColumn("Aliases (comma-sep.)"),
                "evidence_ids": st.column_config.TextColumn("Evidence IDs (comma-sep.)"),
            },
        )
        if st.form_submit_button("Save skills", type="primary"):
            try:
                skills = rows_to_models(_records(df), Skill, profile.skills,
                                        list_fields=("aliases", "evidence_ids"))
            except ValueError as exc:
                _show_error(exc)
                return
            _save(store, profile.model_copy(update={"skills": skills}))
    with st.expander("Evidence ID reference"):
        st.dataframe(
            pd.DataFrame(
                [{"id": i, "type": k, "item": _evidence_label(k, obj)} for i, k, obj in profile.iter_evidence()]
            ),
            hide_index=True,
        )


def _table_section(store, profile, *, field: str, model_cls, cols: list[str], form_key: str,
                   metric_fields: tuple[str, ...] = (), label: str) -> None:
    items = getattr(profile, field)
    with st.form(form_key):
        st.markdown(f"**{label}** — dates as YYYY-MM")
        df = st.data_editor(
            _frame(models_to_rows(items, cols, metric_fields=metric_fields), cols),
            num_rows="dynamic", key=f"{form_key}_editor",
            column_config={"id": ID_COL},
        )
        if st.form_submit_button(f"Save {label.lower()}", type="primary"):
            try:
                new_items = rows_to_models(_records(df), model_cls, items, metric_fields=metric_fields)
            except ValueError as exc:
                _show_error(exc)
                return
            _save(store, profile.model_copy(update={field: new_items}))


def _education_tab(store: ProfileStore, profile: MasterProfile) -> None:
    _table_section(store, profile, field="education", model_cls=Education, form_key="edu_form", label="Education",
                   cols=["id", "institution", "degree", "field_of_study", "location", "grade",
                         "start_date", "end_date", "source_note"])
    _table_section(store, profile, field="certifications", model_cls=Certification, form_key="cert_form",
                   label="Certifications",
                   cols=["id", "name", "issuer", "issue_date", "expiry_date", "credential_url", "source_note"])


def _achievements_tab(store: ProfileStore, profile: MasterProfile) -> None:
    _table_section(store, profile, field="achievements", model_cls=Achievement, form_key="ach_form",
                   label="Achievements", metric_fields=("verified_metrics",),
                   cols=["id", "title", "description", "date", "source_note", "verified_metrics"])


# ---- import / export / history / delete ----------------------------------------


def _export_section(store: ProfileStore, profile: MasterProfile) -> None:
    st.subheader("Export")
    st.download_button(
        "Download profile JSON", export_profile_json(profile),
        file_name=f"master_profile_v{profile.profile_version}.json", mime="application/json",
    )


def _import_section(store: ProfileStore) -> None:
    st.subheader("Import profile JSON")
    st.caption(f"JSON only, up to {MAX_IMPORT_BYTES // 1000} KB. Importing saves a new version; "
               "earlier versions are kept in History.")
    upload = st.file_uploader("Profile JSON file", type=["json"], key="profile_import")
    if upload is None:
        return
    if upload.size > MAX_IMPORT_BYTES:
        st.error(f"File is too large ({upload.size:,} bytes).")
        return
    try:
        imported = parse_profile_json(upload.getvalue())
    except ProfileImportError as exc:
        st.error(str(exc))
        return
    st.success(
        f"Valid profile for **{imported.contact.full_name}**: {len(imported.experience)} experience, "
        f"{len(imported.projects)} projects, {len(imported.skills)} skills."
    )
    if imported.is_sample:
        st.info("This file is marked as fictional sample data.")
    if st.button("Save imported profile as new version", type="primary"):
        _save(store, imported)


def _history_section(store: ProfileStore) -> None:
    st.subheader("Version history")
    versions = store.list_versions()
    if not versions:
        st.caption("No saved versions.")
        return
    st.caption("Every save creates an immutable snapshot. Restoring copies a snapshot into a new version.")
    v = st.selectbox("Version", list(reversed(versions)), format_func=lambda n: f"v{n}")
    try:
        snap = store.load_version(v)
    except (ProfileStoreError, ValueError) as exc:
        st.error(f"Version {v} could not be read: {exc}")
        return
    st.caption(f"Saved {snap.updated_at:%Y-%m-%d %H:%M} UTC")
    with st.expander("View contents"):
        st.json(snap.model_dump(mode="json"), expanded=False)
    if st.button(f"Restore v{v} as a new version"):
        _save(store, snap)


def _delete_section(store: ProfileStore) -> None:
    st.subheader("Delete profile data")
    st.caption("Permanently removes the master profile, all versions, and role profiles from this computer.")
    typed = st.text_input("Type DELETE to confirm", key="delete_confirm")
    if st.button("Delete all profile data", disabled=typed != "DELETE"):
        store.delete_all()
        flash("success", "All profile data deleted.")
        st.rerun()


def _raw_json_tab(store: ProfileStore, profile: MasterProfile) -> None:
    st.caption("Advanced: edit the whole profile as JSON. It is fully validated before saving.")
    with st.form("raw_json"):
        text = st.text_area("Profile JSON", export_profile_json(profile), height=500)
        if st.form_submit_button("Validate and save"):
            try:
                edited = parse_profile_json(text)
            except ProfileImportError as exc:
                st.error(str(exc))
                return
            _save(store, edited)
