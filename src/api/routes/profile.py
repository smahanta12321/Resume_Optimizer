"""Master profile and role profiles (mirrors the Master Profile and Resume Library pages)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request, Response
from pydantic import TypeAdapter, ValidationError

from src.api import deps
from src.api.errors import ApiError, not_found
from src.api.models import (
    DeleteConfirmIn,
    DuplicateRoleIn,
    EvidenceItem,
    ProfileImportPreview,
    ProfileSaveIn,
    ProfileSaveOut,
    ProfileVersionInfo,
    ProfileView,
    ProfileWarningView,
    RoleProfileIn,
    RoleProfileView,
    VersionCheckIn,
)
from src.persistence.profile_store import ProfileStore, ProfileStoreError
from src.schemas.profile import MasterProfile
from src.services.matching_service import build_index
from src.services.profile_service import (
    MAX_IMPORT_BYTES,
    ProfileImportError,
    RoleProfileError,
    create_role_profile,
    delete_role_profile,
    duplicate_role_profile,
    export_profile_json,
    load_sample_profile,
    parse_profile_json,
    profile_warnings,
    prune_removed_evidence,
    update_role_profile,
)

router = APIRouter(tags=["profile"])


def evidence_items(profile: MasterProfile) -> list[EvidenceItem]:
    """Every evidence item with the same labels the match report uses."""
    return [EvidenceItem(id=d.id, kind=d.kind, label=d.label, parent_id=d.parent_id)
            for d in build_index(profile).docs]


def _view(profile: Optional[MasterProfile]) -> ProfileView:
    if profile is None:
        return ProfileView(profile=None)
    return ProfileView(profile=profile,
                       warnings=[ProfileWarningView(item_id=w.item_id, message=w.message)
                                 for w in profile_warnings(profile)],
                       evidence=evidence_items(profile))


def _current_or_none(store: ProfileStore) -> Optional[MasterProfile]:
    try:
        return store.load()
    except ProfileStoreError:
        return None  # an unreadable file must not block import/restore (as on the Streamlit page)


def parse_sections(raw: dict[str, Any]) -> MasterProfile:
    """Validate every field of a submitted profile, but not the cross-references between them yet.

    The Streamlit page edits one section at a time and prunes links to deleted evidence before the
    full validation in ``save_new_version``. Validating references first would make deleting a linked
    item impossible, so this keeps the same order.
    """
    unknown = sorted(set(raw) - set(MasterProfile.model_fields))
    if unknown:
        raise ApiError(422, "invalid_data", f"Unknown profile fields: {', '.join(unknown)}.")
    values, errors = {}, []
    for name, field in MasterProfile.model_fields.items():
        if name not in raw:
            continue
        try:
            values[name] = TypeAdapter(field.annotation).validate_python(raw[name])
        except ValidationError as exc:
            errors += [{"loc": [name, *map(str, e["loc"])], "msg": e["msg"]} for e in exc.errors()]
    if "contact" not in raw:
        errors.append({"loc": ["contact"], "msg": "Field required"})
    if errors:
        raise ApiError(422, "invalid_data", "Could not save. Please fix:\n" + "\n".join(
            f"- {'.'.join(e['loc'])}: {e['msg']}" for e in errors[:10]), errors[:20])
    return MasterProfile.model_construct(**values)


def _save(store: ProfileStore, profile: MasterProfile, expected: Optional[int]) -> ProfileSaveOut:
    """Same steps as the Streamlit page's save: version check, prune removed evidence, new immutable version."""
    before = _current_or_none(store)
    deps.check_version(before, expected)
    notes: list[str] = []
    if before is not None:
        profile, notes = prune_removed_evidence(before, profile)
    saved = store.save_new_version(profile)
    changed = before is None or saved.profile_version != before.profile_version
    return ProfileSaveOut(profile=saved, changed=changed, notes=notes)


@router.get("/profile", response_model=ProfileView)
def get_profile() -> ProfileView:
    return _view(deps.profile_store().load())


@router.put("/profile", response_model=ProfileSaveOut)
def save_profile(body: ProfileSaveIn) -> ProfileSaveOut:
    """Save the whole profile as a new version. Any change clears confirmation."""
    return _save(deps.profile_store(), parse_sections(body.profile), body.expected_version)


@router.post("/profile/confirm", response_model=ProfileView)
def confirm_profile(body: VersionCheckIn) -> ProfileView:
    store = deps.profile_store()
    deps.check_version(store.load(), body.expected_version)
    return _view(store.mark_confirmed())


@router.post("/profile/sample", response_model=ProfileSaveOut)
def load_sample() -> ProfileSaveOut:
    """Load the fictional sample profile. Only offered when no profile exists, as in Streamlit."""
    store = deps.profile_store()
    if _current_or_none(store) is not None or store.list_versions():
        raise ApiError(409, "profile_exists", "A profile already exists. The sample is only offered for a fresh start.")
    return _save(store, load_sample_profile(), None)


@router.get("/profile/versions", response_model=list[ProfileVersionInfo])
def list_versions() -> list[ProfileVersionInfo]:
    store = deps.profile_store()
    out = []
    for v in reversed(store.list_versions()):
        try:
            out.append(ProfileVersionInfo(version=v, updated_at=store.load_version(v).updated_at, readable=True))
        except (ProfileStoreError, ValueError):
            out.append(ProfileVersionInfo(version=v, updated_at=None, readable=False))
    return out


@router.get("/profile/versions/{version}", response_model=MasterProfile)
def get_version(version: int) -> MasterProfile:
    try:
        return deps.profile_store().load_version(version)
    except ProfileStoreError as exc:
        raise not_found(f"Profile version {version}") from exc


@router.post("/profile/versions/{version}/restore", response_model=ProfileSaveOut)
def restore_version(version: int, body: VersionCheckIn) -> ProfileSaveOut:
    store = deps.profile_store()
    try:
        snapshot = store.load_version(version)
    except ProfileStoreError as exc:
        raise not_found(f"Profile version {version}") from exc
    return _save(store, snapshot, body.expected_version)


@router.post("/profile/import/preview", response_model=ProfileImportPreview)
async def preview_import(request: Request) -> ProfileImportPreview:
    """Validate an uploaded profile JSON (raw request body). Nothing is saved; PUT /profile saves it."""
    raw = await request.body()
    if len(raw) > MAX_IMPORT_BYTES:
        raise ApiError(413, "too_large", f"File is too large ({len(raw):,} bytes). The limit is "
                                         f"{MAX_IMPORT_BYTES // 1000} KB.")
    try:
        profile = parse_profile_json(raw)
    except ProfileImportError as exc:
        raise ApiError(422, "invalid_profile", str(exc)) from exc
    return ProfileImportPreview(profile=profile, full_name=profile.contact.full_name,
                                experience=len(profile.experience), projects=len(profile.projects),
                                skills=len(profile.skills), is_sample=profile.is_sample)


@router.get("/profile/export", response_class=Response,
            responses={200: {"content": {"application/json": {}}, "description": "Profile JSON file"}})
def export_profile() -> Response:
    profile = deps.require_profile(deps.profile_store())
    return Response(export_profile_json(profile), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="master_profile_v{profile.profile_version}.json"'})


@router.delete("/profile", status_code=204)
def delete_profile(body: DeleteConfirmIn) -> Response:
    """Delete the profile, all its versions and role profiles. The user must type DELETE."""
    if body.confirm != "DELETE":
        raise ApiError(422, "confirmation_required", "Type DELETE to confirm.")
    deps.profile_store().delete_all()
    return Response(status_code=204)


# ---- role profiles ----------------------------------------------------------------


def _role_error(exc: Exception) -> ApiError:
    return ApiError(422, "invalid_role_profile", str(exc))


@router.get("/role-profiles", response_model=list[RoleProfileView], tags=["role profiles"])
def list_roles() -> list[RoleProfileView]:
    store = deps.profile_store()
    profile = store.load()
    roles = store.load_roles().role_profiles
    return [RoleProfileView(role=r, dangling=r.dangling_references(profile) if profile else []) for r in roles]


@router.post("/role-profiles", response_model=RoleProfileView, status_code=201, tags=["role profiles"])
def create_role(body: RoleProfileIn) -> RoleProfileView:
    try:
        role = create_role_profile(deps.profile_store(), body.name, target_role=body.target_role,
                                   evidence_ids=body.evidence_ids, skill_ids=body.skill_ids,
                                   target_pages=body.target_pages)
    except (RoleProfileError, ValueError) as exc:
        raise _role_error(exc) from exc
    return RoleProfileView(role=role, dangling=[])


@router.put("/role-profiles/{role_id}", response_model=RoleProfileView, tags=["role profiles"])
def update_role(role_id: str, body: RoleProfileIn) -> RoleProfileView:
    try:
        role = update_role_profile(deps.profile_store(), role_id, **body.model_dump())
    except (RoleProfileError, ValueError) as exc:
        raise _role_error(exc) from exc
    return RoleProfileView(role=role, dangling=[])


@router.post("/role-profiles/{role_id}/duplicate", response_model=RoleProfileView, status_code=201,
             tags=["role profiles"])
def duplicate_role(role_id: str, body: DuplicateRoleIn) -> RoleProfileView:
    try:
        role = duplicate_role_profile(deps.profile_store(), role_id, body.name)
    except (RoleProfileError, ValueError) as exc:
        raise _role_error(exc) from exc
    return RoleProfileView(role=role, dangling=[])


@router.delete("/role-profiles/{role_id}", status_code=204, tags=["role profiles"])
def delete_role(role_id: str) -> Response:
    try:
        delete_role_profile(deps.profile_store(), role_id)
    except RoleProfileError as exc:
        raise not_found("This role profile") from exc
    return Response(status_code=204)
