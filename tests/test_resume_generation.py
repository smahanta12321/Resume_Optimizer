"""Deterministic drafting, claim checks and validation. Fictional data only."""

from __future__ import annotations

from datetime import date

import pytest

from src.schemas.analysis import Importance, JDAnalysis, Requirement, RequirementCategory as Cat
from src.schemas.profile import (
    Bullet,
    Contact,
    Experience,
    MasterProfile,
    Project,
    RoleProfile,
    Skill,
    TargetLength,
    VerifiedMetric,
)
from src.schemas.resume import TextOrigin
from src.services.claim_checker import check_rewrite, check_summary
from src.services.matching_service import build_match_report
from src.services.resume_generator import build_draft, new_version
from src.services.resume_validation import change_summary, validate_resume

TODAY = date(2026, 10, 5)


@pytest.fixture
def profile() -> MasterProfile:
    return MasterProfile(
        contact=Contact(full_name="Fictional Person", email="person@example.com"),
        headline="ML Engineer (fictional)", summary="Fictional engineer who builds ML systems.",
        experience=[
            Experience(id="exp-old", employer="Old Fictional Co", title="Analyst", start_date="2019-01",
                       end_date="2021-12", bullets=[
                           Bullet(id="bul-o1", text="Wrote SQL reports for sales."),
                           Bullet(id="bul-o2", text="Organized team offsites."),
                       ]),
            Experience(id="exp-new", employer="New Fictional Co", title="ML Engineer", start_date="2022-01",
                       bullets=[
                           Bullet(id="bul-n1", text="Deployed PyTorch models with Docker."),
                           Bullet(id="bul-n2", text="Cut inference latency by 40% using batching.",
                                  verified_metrics=[VerifiedMetric(label="latency", value="40%")]),
                           Bullet(id="bul-n3", text="Served 3 million requests a day."),  # unverified number
                           Bullet(id="bul-n4", text="Ran the team book club."),
                       ]),
        ],
        projects=[Project(id="prj-1", name="Fictional RAG Bot", bullets=[
                      Bullet(id="bul-p1", text="Built retrieval with LangChain and FAISS.")]),
                  Project(id="prj-2", name="Fictional Garden App", bullets=[
                      Bullet(id="bul-p2", text="Made a watering timer.")])],
        skills=[Skill(id="skl-py", name="PyTorch"), Skill(id="skl-sql", name="SQL"),
                Skill(id="skl-lc", name="LangChain"), Skill(id="skl-rust", name="Rust")],  # Rust: no evidence
    )


@pytest.fixture
def analysis() -> JDAnalysis:
    def r(text, term, imp=Importance.REQUIRED):
        return Requirement(category=Cat.SKILL, text=text, normalized_term=term, importance=imp)
    return JDAnalysis(job_id="job-1", jd_hash="h", requirements=[
        r("PyTorch", "PyTorch"), r("Docker", "Docker"), r("SQL", "SQL"),
        r("LangChain", "LangChain", Importance.PREFERRED), r("Kubernetes", "Kubernetes"), r("Scala", "Scala")])


@pytest.fixture
def draft(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    content, omitted = build_draft(profile, analysis, report)
    return content, omitted, report


# ---- drafting ---------------------------------------------------------------------


def test_draft_copies_facts_and_orders_roles(draft, profile):
    content, _, _ = draft
    assert [e.evidence_id for e in content.experience] == ["exp-new", "exp-old"]  # current role first
    new = content.experience[0]
    assert (new.title, new.organization, new.start_date, new.end_date) == ("ML Engineer", "New Fictional Co",
                                                                          "2022-01", None)
    assert all(b.origin is TextOrigin.VERBATIM and b.text == b.source_text for b in new.bullets)
    assert content.summary.text == profile.summary and content.headline == profile.headline


def test_draft_prefers_relevant_bullets_and_excludes_unverified_numbers(draft):
    content, omitted, _ = draft
    new_ids = [b.evidence_ids[0] for b in content.experience[0].bullets]
    assert new_ids[0] == "bul-n1"            # supports PyTorch + Docker
    assert "bul-n3" not in new_ids           # "3 million" has no verified metric
    assert "bul-n2" in new_ids               # 40% is verified -> usable as filler context
    assert any("bul-n3" in o and "unverified" in o for o in omitted)
    old_ids = [b.evidence_ids[0] for b in content.experience[1].bullets]
    assert old_ids == ["bul-o1"]             # SQL-relevant bullet; the offsites bullet is left out
    assert any("bul-o2" in o for o in omitted)


def test_draft_skills_only_with_evidence_jd_first(draft):
    content, omitted, _ = draft
    names = [s.name for s in content.skills]
    assert "Rust" not in names and any("Rust" in o for o in omitted)
    assert names[:2] == ["PyTorch", "SQL"] and all(s.evidence_ids for s in content.skills)


def test_draft_projects_by_relevance(draft):
    content, omitted, _ = draft
    assert [p.evidence_id for p in content.projects] == ["prj-1"]
    assert any("Garden" in o for o in omitted)


def test_two_page_target_allows_more(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    one, _ = build_draft(profile, analysis, report, target_pages=TargetLength.ONE_PAGE)
    two, _ = build_draft(profile, analysis, report, target_pages=TargetLength.TWO_PAGES)
    assert sum(len(e.bullets) for e in two.experience) >= sum(len(e.bullets) for e in one.experience)


def test_role_profile_headline_and_bonus(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    role = RoleProfile(name="Org", headline="Fictional Role Headline", evidence_ids=["bul-o2", "prj-2"])
    content, _ = build_draft(profile, analysis, report, role=role)
    assert content.headline == "Fictional Role Headline"
    assert "bul-o2" in [b.evidence_ids[0] for b in content.experience[1].bullets]
    assert "prj-2" in [p.evidence_id for p in content.projects]


# ---- claim checker ----------------------------------------------------------------


def test_rewrite_rejects_new_numbers_and_skills():
    src = "Deployed PyTorch models with Docker."
    assert check_rewrite("Deployed PyTorch models in Docker containers.", src).ok
    bad = check_rewrite("Deployed 12 PyTorch models with Docker and Kubernetes.", src)
    assert any("12" in e for e in bad.errors) and any("Kubernetes" in e for e in bad.errors)
    assert check_rewrite("Cut latency by 40%.", "Cut latency using batching.", verified_values=["40%"]).ok
    assert not check_rewrite("", src).ok
    assert not check_rewrite("x" * 400, src).ok


def test_rewrite_tagged_skill_allowed():
    assert check_rewrite("Built services in Python.", "Built services.", tagged_terms=["Python"]).ok


def test_rewrite_warns_on_new_names_and_stronger_wording():
    res = check_rewrite("Led the Acme migration of PyTorch models.", "Helped migrate PyTorch models.")
    assert res.ok
    assert any("Acme" in w for w in res.warnings) and any("led" in w for w in res.warnings)
    assert check_rewrite("Deployed models.", "deployed models.").warnings == []  # sentence-start capital is fine


def test_summary_checks():
    ok = check_summary("ML engineer with 4+ years of experience using PyTorch.",
                       cited_texts=["Deployed PyTorch models."], evidenced_terms=["PyTorch", "Machine Learning"],
                       total_experience_years=4.7)
    assert ok.ok
    bad = check_summary("ML engineer with 8 years of experience in Kubernetes, 20 launches.",
                        cited_texts=["Deployed PyTorch models."], evidenced_terms=["PyTorch"],
                        total_experience_years=4.7)
    assert len(bad.errors) == 3


# ---- validation -------------------------------------------------------------------


def _version(profile, report, content, omitted):
    return new_version("job-1", profile, report, content, omitted, generator="deterministic", role=None,
                       target_pages=TargetLength.ONE_PAGE)


def test_fresh_draft_validates(draft, profile, analysis):
    content, omitted, report = draft
    v = _version(profile, report, content, omitted)
    res = validate_resume(v, profile, analysis=analysis, report=report, today=TODAY)
    assert res.ok, res.errors
    assert any("Scala" in i for i in res.info)            # required, not documented
    assert not any("Kubernetes" in i for i in res.info)   # partial (related Docker evidence), not missing
    assert res.estimated_lines > 0


def test_validation_catches_tampering(draft, profile):
    content, omitted, report = draft
    c = content.model_copy(deep=True)
    c.experience[0].title = "Head of ML"                                # invented title
    c.experience[0].bullets[0].text = "Deployed 50 PyTorch models."    # verbatim text altered
    c.experience[1].bullets[0] = c.experience[1].bullets[0].model_copy(update={
        "origin": TextOrigin.USER_EDIT, "text": "Wrote SQL and Tableau reports for 9 regions."})
    c.skills[0] = c.skills[0].model_copy(update={"evidence_ids": ["bul-gone"]})
    res = validate_resume(_version(profile, report, c, omitted), profile, today=TODAY)
    joined = " ".join(res.errors)
    assert "differ from your profile" in joined
    assert "marked verbatim differs" in joined
    assert "Tableau" in joined and "9" in joined
    assert "has no evidence" in joined


def test_validation_flags_profile_drift(draft, profile):
    content, omitted, report = draft
    v = _version(profile, report, content, omitted)
    p2 = profile.model_copy(deep=True)
    p2.experience[1].bullets[0].text = "Deployed PyTorch and ONNX models with Docker."
    p2 = MasterProfile.model_validate(p2.model_dump() | {"profile_version": 2})
    res = validate_resume(v, p2, today=TODAY)
    assert any("profile is now v2" in w for w in res.warnings)
    assert any("changed since" in w for w in res.warnings)


def test_change_summary(draft, profile):
    content, omitted, report = draft
    rows = change_summary(_version(profile, report, content, omitted), profile)
    assert rows[0].section == "Summary" and rows[0].change == "unchanged"
    assert all(r.evidence for r in rows[1:])


# ---- workflow service --------------------------------------------------------------


def test_generate_version_falls_back_when_ai_fails(profile, analysis):
    from src.schemas.job import Job
    from src.services.llm.provider import LLMError
    from src.services.resume_service import generate_version

    class Failing:
        name, model = "fake", "m"

        def generate_json(self, **kw):
            raise LLMError("Could not reach the API.")

    report, _ = build_match_report(analysis, profile, today=TODAY)
    out = generate_version(Job(description="Fictional JD"), profile, analysis, report, provider=Failing(), today=TODAY)
    assert out.ai_failed == "Could not reach the API." and out.version.generator == "deterministic"
    assert out.version.content.experience  # still a usable draft


def test_user_edits_create_child_version_and_are_checked(draft, profile):
    from src.services.resume_service import apply_user_edits

    content, omitted, report = draft
    v1 = _version(profile, report, content, omitted)
    assert apply_user_edits(v1) is v1  # nothing changed -> no new version
    first = content.experience[0]
    b0, b1 = first.bullets[0], first.bullets[1]
    v2 = apply_user_edits(v1, summary_text="Fictional ML engineer with 9 years in Kubernetes.", bullets={
        (first.evidence_id, b0.evidence_ids[0]): (True, "Deployed PyTorch models using Docker."),
        (first.evidence_id, b1.evidence_ids[0]): (False, b1.text),
    })
    assert v2.id != v1.id and v2.parent_id == v1.id and v2.generator == "user_edit"
    new_first = v2.content.experience[0]
    assert new_first.bullets[0].origin is TextOrigin.USER_EDIT
    assert b1.evidence_ids[0] not in [b.evidence_ids[0] for b in new_first.bullets]
    assert any("removed by you" in o for o in v2.omitted)
    assert v1.content.experience[0].bullets[0].text == b0.text  # parent unchanged
    res = validate_resume(v2, profile, today=TODAY)
    assert any("9 years" in e for e in res.errors) and any("Kubernetes" in e for e in res.errors)


def test_reverting_edit_to_source_counts_as_verbatim(draft, profile):
    from src.services.resume_service import apply_user_edits

    content, omitted, report = draft
    v1 = _version(profile, report, content, omitted)
    e, b = content.experience[0], content.experience[0].bullets[0]
    v2 = apply_user_edits(v1, bullets={(e.evidence_id, b.evidence_ids[0]): (True, "Something else entirely.")})
    v3 = apply_user_edits(v2, bullets={(e.evidence_id, b.evidence_ids[0]): (True, b.source_text)})
    assert v3.content.experience[0].bullets[0].origin is TextOrigin.VERBATIM
