"""Profile management: JSON import/export, deterministic quality checks, and role profiles."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from src.persistence.profile_store import ProfileStore, read_json_file
from src.schemas.profile import (
    MasterProfile,
    RoleProfile,
    RoleProfileLibrary,
    TargetLength,
    utc_now,
)

logger = logging.getLogger(__name__)

MAX_IMPORT_BYTES = 1_000_000  # a master profile is a few KB; anything this big is not one
SAMPLE_PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "samples" / "sample_profile.json"

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


class ProfileImportError(ValueError):
    """Raised when imported profile data is not acceptable. Message is user-facing."""


class RoleProfileError(ValueError):
    """Raised for invalid role-profile operations. Message is user-facing."""


def format_validation_error(exc: ValidationError, limit: int = 10) -> str:
    """Render a Pydantic error as short, readable lines (location: message)."""
    lines = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(p) for p in err["loc"]) or "(profile)"
        lines.append(f"- {loc}: {err['msg']}")
    extra = len(exc.errors()) - limit
    if extra > 0:
        lines.append(f"- … and {extra} more")
    return "\n".join(lines)


# ---- import / export ------------------------------------------------------


def parse_profile_json(raw: bytes | str) -> MasterProfile:
    """Parse and validate an uploaded/pasted profile JSON document.

    Missing item IDs are generated; existing IDs are preserved.
    Raises ``ProfileImportError`` with a user-facing message on any problem.
    """
    size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
    if size == 0:
        raise ProfileImportError("The file is empty.")
    if size > MAX_IMPORT_BYTES:
        raise ProfileImportError(f"File is too large ({size:,} bytes; limit {MAX_IMPORT_BYTES:,}).")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProfileImportError(f"Not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileImportError("Profile JSON must be an object at the top level.")
    try:
        return MasterProfile.model_validate(data)
    except ValidationError as exc:
        raise ProfileImportError("Profile failed validation:\n" + format_validation_error(exc)) from exc


def export_profile_json(profile: MasterProfile) -> str:
    """Serialize the profile as pretty JSON suitable for backup or re-import."""
    return profile.model_dump_json(indent=2)


def load_sample_profile(path: Path = SAMPLE_PROFILE_PATH) -> MasterProfile:
    """Load the bundled fictional sample profile."""
    return MasterProfile.model_validate(read_json_file(path))


def prune_removed_evidence(old: MasterProfile, new: MasterProfile) -> tuple[MasterProfile, list[str]]:
    """Drop references to evidence that existed in ``old`` but was deleted in ``new``.

    Only IDs the user actually removed are pruned (from skill evidence links and
    project→experience links); unknown IDs that never existed still fail validation.
    Returns the (unvalidated) updated profile and user-facing notes on what changed.
    """
    old_ids = {i for i, _, _ in old.iter_evidence()}
    new_ids = {i for i, _, _ in new.iter_evidence()}
    removed = old_ids - new_ids
    if not removed:
        return new, []
    notes: list[str] = []
    skills = []
    for s in new.skills:
        kept = [e for e in s.evidence_ids if e not in removed]
        if len(kept) != len(s.evidence_ids):
            notes.append(f"Skill '{s.name}' lost evidence link(s) to deleted item(s).")
        skills.append(s.model_copy(update={"evidence_ids": kept}))
    projects = []
    for p in new.projects:
        if p.related_experience_id in removed:
            notes.append(f"Project '{p.name}' is no longer linked to the deleted experience.")
            p = p.model_copy(update={"related_experience_id": None})
        projects.append(p)
    return new.model_copy(update={"skills": skills, "projects": projects}), notes


# ---- deterministic quality checks -----------------------------------------


@dataclass(frozen=True)
class ProfileWarning:
    item_id: Optional[str]
    message: str


def unverified_numbers(text: str, metric_values: list[str]) -> list[str]:
    """Numbers in ``text`` (other than years) that don't appear in any verified metric value."""
    backed = " ".join(metric_values)
    found = []
    for num in _NUMBER_RE.findall(text):
        if _YEAR_RE.match(num):
            continue
        if num not in backed:
            found.append(num)
    return found


def profile_warnings(profile: MasterProfile) -> list[ProfileWarning]:
    """Non-blocking issues worth the user's attention before relying on the profile."""
    warnings: list[ProfileWarning] = []
    skill_names = {s.name.casefold() for s in profile.skills} | {
        a.casefold() for s in profile.skills for a in s.aliases
    }

    if not profile.contact.email:
        warnings.append(ProfileWarning(None, "Contact email is empty."))
    if not profile.experience and not profile.projects:
        warnings.append(ProfileWarning(None, "Profile has no experience or projects to draw evidence from."))

    for skill in profile.skills:
        if not skill.evidence_ids:
            warnings.append(
                ProfileWarning(skill.id, f"Skill '{skill.name}' has no linked evidence; matching will treat it as weak.")
            )

    containers = [(e.id, f"{e.title} at {e.employer}", e.bullets) for e in profile.experience]
    containers += [(p.id, f"project '{p.name}'", p.bullets) for p in profile.projects]
    for cid, label, bullets in containers:
        if not bullets:
            warnings.append(ProfileWarning(cid, f"{label} has no bullets."))
        for b in bullets:
            nums = unverified_numbers(b.text, [m.value for m in b.verified_metrics])
            if nums:
                warnings.append(
                    ProfileWarning(
                        b.id,
                        f"Bullet in {label} contains number(s) {', '.join(nums)} without a matching "
                        "verified metric. Add a verified metric or reword before it is used.",
                    )
                )
            unknown = [s for s in b.skills if s.casefold() not in skill_names]
            if unknown:
                warnings.append(
                    ProfileWarning(b.id, f"Bullet in {label} tags skills not in your skills list: {', '.join(unknown)}.")
                )
    return warnings


# ---- role profiles ---------------------------------------------------------


def _find_role(library: RoleProfileLibrary, role_id: str) -> RoleProfile:
    for r in library.role_profiles:
        if r.id == role_id:
            return r
    raise RoleProfileError(f"Role profile {role_id!r} not found.")


def _check_name_free(library: RoleProfileLibrary, name: str, ignore_id: Optional[str] = None) -> str:
    name = name.strip()
    if not name:
        raise RoleProfileError("Role profile name cannot be empty.")
    for r in library.role_profiles:
        if r.id != ignore_id and r.name.casefold() == name.casefold():
            raise RoleProfileError(f"A role profile named '{name}' already exists.")
    return name


def _check_references(profile: MasterProfile, role: RoleProfile) -> None:
    dangling = role.dangling_references(profile)
    if dangling:
        raise RoleProfileError(f"Role profile references items not in the master profile: {dangling}")


def create_role_profile(
    store: ProfileStore,
    name: str,
    *,
    target_role: str = "",
    evidence_ids: Optional[list[str]] = None,
    skill_ids: Optional[list[str]] = None,
    target_pages: TargetLength = TargetLength.ONE_PAGE,
) -> RoleProfile:
    """Create a role profile; all referenced IDs must exist in the current master profile."""
    profile = store.load()
    if profile is None:
        raise RoleProfileError("Create a master profile first.")
    library = store.load_roles()
    role = RoleProfile(
        name=_check_name_free(library, name),
        target_role=target_role,
        evidence_ids=list(evidence_ids or []),
        skill_ids=list(skill_ids or []),
        target_pages=target_pages,
    )
    _check_references(profile, role)
    library.role_profiles.append(role)
    store.save_roles(library)
    return role


def update_role_profile(store: ProfileStore, role_id: str, **changes) -> RoleProfile:
    """Update fields of a role profile (name, target_role, evidence_ids, skill_ids, target_pages, headline)."""
    allowed = {"name", "target_role", "evidence_ids", "skill_ids", "target_pages", "headline"}
    bad = set(changes) - allowed
    if bad:
        raise RoleProfileError(f"Cannot update fields: {sorted(bad)}")
    profile = store.load()
    if profile is None:
        raise RoleProfileError("Create a master profile first.")
    library = store.load_roles()
    role = _find_role(library, role_id)
    if "name" in changes:
        changes["name"] = _check_name_free(library, changes["name"], ignore_id=role_id)
    updated = RoleProfile.model_validate({**role.model_dump(), **changes, "updated_at": utc_now()})
    _check_references(profile, updated)
    library.role_profiles = [updated if r.id == role_id else r for r in library.role_profiles]
    store.save_roles(library)
    return updated


def rename_role_profile(store: ProfileStore, role_id: str, new_name: str) -> RoleProfile:
    return update_role_profile(store, role_id, name=new_name)


def duplicate_role_profile(store: ProfileStore, role_id: str, new_name: str) -> RoleProfile:
    library = store.load_roles()
    source = _find_role(library, role_id)
    now = utc_now()
    copy = RoleProfile.model_validate(
        {
            **source.model_dump(exclude={"id"}),
            "name": _check_name_free(library, new_name),
            "created_at": now,
            "updated_at": now,
        }
    )
    library.role_profiles.append(copy)
    store.save_roles(library)
    return copy


def delete_role_profile(store: ProfileStore, role_id: str) -> None:
    library = store.load_roles()
    _find_role(library, role_id)
    library.role_profiles = [r for r in library.role_profiles if r.id != role_id]
    store.save_roles(library)
