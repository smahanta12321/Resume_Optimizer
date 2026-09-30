"""Resume Library: role profiles as ordered selections of master-profile evidence."""

from __future__ import annotations

import streamlit as st

from src.persistence.profile_store import ProfileStore, ProfileStoreError
from src.schemas.profile import MasterProfile, RoleProfile, TargetLength
from src.services.profile_service import (
    RoleProfileError,
    create_role_profile,
    delete_role_profile,
    duplicate_role_profile,
    update_role_profile,
)
from src.ui.state import flash, get_store, sample_banner, show_flashes

SUGGESTED_ROLES = ["AI Engineer", "Generative AI Engineer", "ML Engineer", "NLP Engineer"]


def _evidence_options(profile: MasterProfile) -> dict[str, str]:
    """Selectable evidence (experience, projects, bullets) -> display label."""
    opts: dict[str, str] = {}
    for exp in profile.experience:
        opts[exp.id] = f"[Experience] {exp.title} @ {exp.employer}"
        for b in exp.bullets:
            opts[b.id] = f"    • {b.text[:90]}"
    for prj in profile.projects:
        opts[prj.id] = f"[Project] {prj.name}"
        for b in prj.bullets:
            opts[b.id] = f"    • {b.text[:90]}"
    return opts


def render() -> None:
    st.title("Resume Library")
    st.caption(
        "A role profile is a named selection and ordering of your verified evidence — "
        "it never adds new facts. Selection order is used as the default ordering."
    )
    show_flashes()
    store = get_store()
    try:
        profile = store.load()
        library = store.load_roles()
    except ProfileStoreError as exc:
        st.error(str(exc))
        return
    if profile is None:
        st.warning("Create or import a master profile first (Master Profile page).")
        return

    sample_banner(profile.is_sample)
    evidence = _evidence_options(profile)
    skills = {s.id: s.name for s in profile.skills}

    if not library.role_profiles:
        st.info("No role profiles yet. Suggested starting points: " + ", ".join(SUGGESTED_ROLES) + ".")

    for role in library.role_profiles:
        dangling = role.dangling_references(profile)
        title = f"{role.name}" + (f" — {role.target_role}" if role.target_role else "")
        with st.expander(f"{title}  ·  {len(role.evidence_ids)} evidence, {len(role.skill_ids)} skills"):
            if dangling:
                st.warning(
                    "Some selected items were removed from the master profile and will be dropped on save: "
                    + ", ".join(dangling)
                )
            _role_form(store, role, evidence, skills)
            _role_actions(store, role)

    with st.expander("➕ New role profile", expanded=not library.role_profiles):
        _role_form(store, None, evidence, skills)


def _role_form(store: ProfileStore, role: RoleProfile | None, evidence: dict[str, str],
               skills: dict[str, str]) -> None:
    key = role.id if role else "new-role"
    with st.form(f"role-{key}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name *", role.name if role else "", placeholder="e.g. ML Engineer")
        target_role = c2.text_input("Target job title", role.target_role if role else "")
        sel_evidence = st.multiselect(
            "Evidence to include (in order)", list(evidence),
            default=[i for i in (role.evidence_ids if role else []) if i in evidence],
            format_func=lambda i: evidence[i],
        )
        sel_skills = st.multiselect(
            "Skills to emphasise (in order)", list(skills),
            default=[i for i in (role.skill_ids if role else []) if i in skills],
            format_func=lambda i: skills[i],
        )
        pages = st.radio(
            "Target length", [TargetLength.ONE_PAGE, TargetLength.TWO_PAGES], horizontal=True,
            index=0 if not role or role.target_pages == TargetLength.ONE_PAGE else 1,
            format_func=lambda t: "1 page" if t == TargetLength.ONE_PAGE else "2 pages",
        )
        if st.form_submit_button("Save" if role else "Create", type="primary"):
            try:
                if role:
                    update_role_profile(store, role.id, name=name, target_role=target_role,
                                        evidence_ids=sel_evidence, skill_ids=sel_skills, target_pages=pages)
                    flash("success", f"Saved role profile '{name}'.")
                else:
                    create_role_profile(store, name, target_role=target_role, evidence_ids=sel_evidence,
                                        skill_ids=sel_skills, target_pages=pages)
                    flash("success", f"Created role profile '{name}'.")
            except (RoleProfileError, ValueError) as exc:
                st.error(str(exc))
                return
            st.rerun()


def _role_actions(store: ProfileStore, role: RoleProfile) -> None:
    c1, c2 = st.columns(2)
    with c1:
        copy_name = st.text_input("Duplicate as", f"{role.name} (copy)", key=f"dup-name-{role.id}")
        if st.button("Duplicate", key=f"dup-{role.id}"):
            try:
                duplicate_role_profile(store, role.id, copy_name)
            except (RoleProfileError, ValueError) as exc:
                st.error(str(exc))
            else:
                flash("success", f"Duplicated as '{copy_name}'.")
                st.rerun()
    with c2:
        confirm = st.checkbox("I want to delete this role profile", key=f"del-chk-{role.id}")
        if st.button("Delete", key=f"del-{role.id}", disabled=not confirm):
            delete_role_profile(store, role.id)
            flash("success", f"Deleted role profile '{role.name}'.")
            st.rerun()
