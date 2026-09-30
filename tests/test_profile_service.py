"""Profile import/export, quality warnings, and role-profile operations."""

from __future__ import annotations

import json

import pytest

from src.schemas.profile import Bullet, TargetLength, VerifiedMetric
from src.services import profile_service as svc
from src.services.profile_service import ProfileImportError, RoleProfileError


# ---- import / export ----


def test_export_then_import_round_trips(sample_profile):
    text = svc.export_profile_json(sample_profile)
    assert svc.parse_profile_json(text) == sample_profile
    assert svc.parse_profile_json(text.encode("utf-8")) == sample_profile


@pytest.mark.parametrize(
    "raw, message",
    [
        ("", "empty"),
        ("{oops", "Not valid JSON"),
        ("[1, 2]", "object at the top level"),
        ('{"contact": {"full_name": "X"}, "unknown": 1}', "failed validation"),
        (b"\xff\xfe\x00", "Not valid JSON"),
    ],
)
def test_import_rejects_bad_input(raw, message):
    with pytest.raises(ProfileImportError, match=message):
        svc.parse_profile_json(raw)


def test_import_rejects_oversized_file():
    raw = json.dumps({"contact": {"full_name": "X"}, "summary": "a" * (svc.MAX_IMPORT_BYTES + 1)})
    with pytest.raises(ProfileImportError, match="too large"):
        svc.parse_profile_json(raw)


def test_validation_error_message_names_the_field():
    raw = json.dumps({"contact": {"full_name": "X"}, "experience": [{"employer": "E", "title": "T", "start_date": "2020"}]})
    with pytest.raises(ProfileImportError, match=r"experience\.0\.start_date"):
        svc.parse_profile_json(raw)


# ---- warnings ----


def test_sample_profile_has_no_unverified_number_warnings(sample_profile):
    msgs = [w.message for w in svc.profile_warnings(sample_profile)]
    assert not any("without a matching verified metric" in m for m in msgs)


def test_unverified_metric_is_flagged(sample_profile):
    exp = sample_profile.experience[1]
    exp.bullets.append(Bullet(id="bul-extra", text="Cut report runtime by 40% for 3 teams in 2021."))
    warnings = [w for w in svc.profile_warnings(sample_profile) if w.item_id == "bul-extra"]
    assert any("40" in w.message and "3" in w.message for w in warnings)
    assert not any("2021" in w.message for w in warnings)


def test_verified_metric_suppresses_warning(sample_profile):
    exp = sample_profile.experience[1]
    exp.bullets.append(
        Bullet(id="bul-extra", text="Cut runtime by 40%.", verified_metrics=[VerifiedMetric(label="runtime", value="40%")])
    )
    assert not [w for w in svc.profile_warnings(sample_profile) if w.item_id == "bul-extra"]


def test_unknown_bullet_skill_and_evidence_free_skill_flagged(sample_profile):
    sample_profile.experience[1].bullets[0].skills.append("Kubernetes")
    sample_profile.skills[0].evidence_ids.clear()
    msgs = [w.message for w in svc.profile_warnings(sample_profile)]
    assert any("Kubernetes" in m for m in msgs)
    assert any("'Python' has no linked evidence" in m for m in msgs)


def test_alias_counts_as_known_skill(sample_profile):
    sample_profile.experience[1].bullets[0].skills.append("natural language processing")
    msgs = [w.message for w in svc.profile_warnings(sample_profile)]
    assert not any("natural language processing" in m for m in msgs)


# ---- role profiles ----


def test_role_profile_requires_master_profile(store):
    with pytest.raises(RoleProfileError, match="master profile first"):
        svc.create_role_profile(store, "ML Engineer")


def test_role_profile_crud(saved_store):
    role = svc.create_role_profile(
        saved_store, "ML Engineer", evidence_ids=["exp-sample01", "bul-sample01"], skill_ids=["skl-pytorch"]
    )
    assert saved_store.load_roles().role_profiles == [role]

    renamed = svc.rename_role_profile(saved_store, role.id, "Machine Learning Engineer")
    assert renamed.name == "Machine Learning Engineer"
    assert renamed.evidence_ids == role.evidence_ids

    dup = svc.duplicate_role_profile(saved_store, role.id, "NLP Engineer")
    assert dup.id != role.id and dup.evidence_ids == role.evidence_ids

    updated = svc.update_role_profile(saved_store, dup.id, target_pages=TargetLength.TWO_PAGES)
    assert updated.target_pages == TargetLength.TWO_PAGES

    svc.delete_role_profile(saved_store, role.id)
    assert [r.name for r in saved_store.load_roles().role_profiles] == ["NLP Engineer"]


def test_role_profile_rejects_unknown_evidence(saved_store):
    with pytest.raises(RoleProfileError, match="not in the master profile"):
        svc.create_role_profile(saved_store, "X", evidence_ids=["bul-invented"])


def test_role_profile_rejects_duplicate_and_empty_names(saved_store):
    svc.create_role_profile(saved_store, "AI Engineer")
    with pytest.raises(RoleProfileError, match="already exists"):
        svc.create_role_profile(saved_store, "ai engineer")
    with pytest.raises(RoleProfileError, match="empty"):
        svc.create_role_profile(saved_store, "   ")


def test_update_rejects_unknown_fields_and_missing_role(saved_store):
    role = svc.create_role_profile(saved_store, "AI Engineer")
    with pytest.raises(RoleProfileError, match="Cannot update"):
        svc.update_role_profile(saved_store, role.id, id="role-hijack")
    with pytest.raises(RoleProfileError, match="not found"):
        svc.delete_role_profile(saved_store, "role-missing")


def test_role_profiles_do_not_modify_master_profile(saved_store):
    before = saved_store.load()
    svc.create_role_profile(saved_store, "AI Engineer", evidence_ids=["bul-sample04"])
    assert saved_store.load() == before
    assert saved_store.list_versions() == [1]


# ---- pruning references to deleted evidence ----


def test_prune_removed_evidence(sample_profile):
    new = sample_profile.model_copy(
        update={"experience": [e for e in sample_profile.experience if e.id != "exp-sample01"]}
    )
    pruned, notes = svc.prune_removed_evidence(sample_profile, new)
    pruned = type(pruned).model_validate(pruned.model_dump())  # now valid
    assert "bul-sample01" not in next(s for s in pruned.skills if s.name == "PyTorch").evidence_ids
    assert pruned.projects[0].related_experience_id is None
    assert any("PyTorch" in n for n in notes) and any("Document Q&A" in n for n in notes)


def test_prune_does_not_hide_invented_ids(sample_profile):
    skills = [s.model_copy(update={"evidence_ids": [*s.evidence_ids, "bul-never-existed"]}) if s.name == "SQL" else s
              for s in sample_profile.skills]
    new = sample_profile.model_copy(update={"skills": skills})
    pruned, notes = svc.prune_removed_evidence(sample_profile, new)
    assert notes == []
    with pytest.raises(ValueError, match="unknown evidence"):
        type(pruned).model_validate(pruned.model_dump())


def test_prune_noop_when_nothing_removed(sample_profile):
    same, notes = svc.prune_removed_evidence(sample_profile, sample_profile)
    assert same is sample_profile and notes == []
