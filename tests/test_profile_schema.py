"""Schema validation for the master profile (fictional data only)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.profile import (
    Bullet,
    Contact,
    Experience,
    MasterProfile,
    RoleProfile,
    RoleProfileLibrary,
    Skill,
)


def _minimal(**overrides) -> dict:
    data = {"contact": {"full_name": "Test Person (fictional)"}}
    data.update(overrides)
    return data


def test_sample_profile_is_valid_and_marked_fictional(sample_profile):
    assert sample_profile.is_sample
    assert "FICTIONAL" in sample_profile.contact.full_name
    assert len(sample_profile.experience) == 2


def test_minimal_profile_generates_ids():
    p = MasterProfile.model_validate(
        _minimal(experience=[{"employer": "E (fictional)", "title": "Dev", "bullets": [{"text": "Did a thing"}]}])
    )
    assert p.experience[0].id.startswith("exp-")
    assert p.experience[0].bullets[0].id.startswith("bul-")


def test_existing_ids_are_preserved():
    p = MasterProfile.model_validate(_minimal(experience=[{"id": "exp-keepme", "employer": "E", "title": "T"}]))
    assert p.experience[0].id == "exp-keepme"


@pytest.mark.parametrize("bad", ["2020", "2020-13", "01-2020", "2020/01", "last year"])
def test_invalid_dates_rejected(bad):
    with pytest.raises(ValidationError, match="YYYY-MM"):
        Experience(employer="E", title="T", start_date=bad)


def test_blank_end_date_means_current():
    e = Experience(employer="E", title="T", start_date="2021-01", end_date="  ")
    assert e.end_date is None
    assert e.is_current


def test_end_before_start_rejected():
    with pytest.raises(ValidationError, match="before start_date"):
        Experience(employer="E", title="T", start_date="2022-05", end_date="2021-01")


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        MasterProfile.model_validate(_minimal(favourite_colour="blue"))


def test_missing_name_rejected():
    with pytest.raises(ValidationError):
        MasterProfile.model_validate({"contact": {"full_name": ""}})


def test_invalid_email_rejected():
    with pytest.raises(ValidationError, match="email"):
        Contact(full_name="X", email="not-an-email")


def test_duplicate_ids_rejected():
    exp = {"id": "exp-dup", "employer": "E", "title": "T"}
    with pytest.raises(ValidationError, match="duplicate IDs"):
        MasterProfile.model_validate(_minimal(experience=[exp, dict(exp)]))


def test_bullet_id_colliding_with_experience_rejected():
    exp = {"id": "exp-1", "employer": "E", "title": "T", "bullets": [{"id": "exp-1", "text": "x"}]}
    with pytest.raises(ValidationError, match="duplicate IDs"):
        MasterProfile.model_validate(_minimal(experience=[exp]))


def test_skill_with_unknown_evidence_rejected():
    with pytest.raises(ValidationError, match="unknown evidence"):
        MasterProfile.model_validate(_minimal(skills=[{"name": "Go", "evidence_ids": ["bul-missing"]}]))


def test_duplicate_skill_names_rejected_case_insensitively():
    with pytest.raises(ValidationError, match="duplicate skill names"):
        MasterProfile.model_validate(_minimal(skills=[{"name": "Python"}, {"name": "python"}]))


def test_project_with_unknown_experience_rejected():
    with pytest.raises(ValidationError, match="unknown experience"):
        MasterProfile.model_validate(
            _minimal(projects=[{"name": "P", "related_experience_id": "exp-nope"}])
        )


def test_evidence_index_covers_bullets(sample_profile):
    idx = sample_profile.evidence_index()
    assert idx["bul-sample01"][0] == "bullet"
    assert idx["exp-sample01"][0] == "experience"
    assert idx["prj-sample01"][0] == "project"
    assert idx["edu-sample01"][0] == "education"


def test_role_profile_dangling_references(sample_profile):
    role = RoleProfile(name="ML", evidence_ids=["exp-sample01", "bul-gone"], skill_ids=["skl-python", "skl-gone"])
    assert role.dangling_references(sample_profile) == ["bul-gone", "skl-gone"]


def test_role_library_rejects_duplicate_names():
    with pytest.raises(ValidationError, match="unique"):
        RoleProfileLibrary(role_profiles=[RoleProfile(name="ML"), RoleProfile(name="ml")])


def test_skill_and_bullet_defaults():
    assert Skill(name="Go").category.value == "other"
    assert Bullet(text="x").verified_metrics == []

