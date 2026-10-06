"""Evidence matching and match-report tests. Profiles and JDs are fictional."""

from __future__ import annotations

from datetime import date

import pytest

from src.schemas.analysis import Importance, JDAnalysis, Requirement, RequirementCategory as Cat
from src.schemas.match import MatchStatus, MatchType
from src.schemas.profile import (
    Bullet,
    Certification,
    Contact,
    Education,
    Experience,
    MasterProfile,
    Project,
    RoleProfile,
    Skill,
)
from src.services.match_report_service import (
    OverrideError,
    clear_override,
    gaps,
    recommend_projects,
    recommend_role_profiles,
    set_override,
    stale_reasons,
    summarize,
)
from src.services.matching_service import build_index, build_match_report, content_tokens, match_requirement

TODAY = date(2026, 10, 5)


@pytest.fixture
def profile() -> MasterProfile:
    return MasterProfile(
        contact=Contact(full_name="Fictional Person"),
        experience=[
            Experience(id="exp-a", employer="Fictional Fintech Ltd", title="ML Engineer", start_date="2022-01",
                       description="Payments fraud models for a fictional fintech company.",
                       bullets=[
                           Bullet(id="bul-a1", text="Deployed PyTorch models on k8s clusters.", skills=["PyTorch"]),
                           Bullet(id="bul-a2", text="Built PySpark feature pipelines for fraud detection."),
                       ]),
            Experience(id="exp-b", employer="Fictional Analytics", title="Analyst", start_date="2020-01",
                       end_date="2022-06",  # overlaps exp-a by 6 months
                       bullets=[Bullet(id="bul-b1", text="Wrote SQL dashboards for weekly sales reviews.")]),
        ],
        projects=[Project(id="prj-x", name="Fictional RAG Bot", skills=["LangChain"],
                          bullets=[Bullet(id="bul-x1", text="Indexed documents in a vector store with FAISS.")])],
        skills=[Skill(id="skl-py", name="Python"), Skill(id="skl-tf", name="TensorFlow"),
                Skill(id="skl-k8s", name="Kubernetes", aliases=["k8s"])],
        education=[Education(id="edu-1", institution="Fictional Institute", degree="B.Tech",
                             field_of_study="Electronics")],
        certifications=[Certification(id="crt-1", name="Fictional Cloud Practitioner", issuer="FictionalCloud")],
    )


def _req(category: Cat, text: str, term: str = "", importance=Importance.REQUIRED, **kw) -> Requirement:
    return Requirement(category=category, text=text, normalized_term=term, importance=importance, **kw)


def _match(profile, req):
    return match_requirement(req, build_index(profile), TODAY)


# ---- skills -----------------------------------------------------------------------


def test_skill_in_evidence_is_supported_even_if_not_listed(profile):
    m = _match(profile, _req(Cat.SKILL, "PyTorch", "PyTorch"))
    assert (m.status, m.match_type) == (MatchStatus.SUPPORTED, MatchType.EXACT)
    assert "bul-a1" in m.evidence_ids


def test_skill_via_alias_names_the_wording(profile):
    m = _match(profile, _req(Cat.SKILL, "Kubernetes", "Kubernetes"))
    assert (m.status, m.match_type) == (MatchStatus.SUPPORTED, MatchType.ALIAS)
    assert m.evidence_ids == ["bul-a1"] and "“k8s”" in m.explanation


def test_listed_skill_without_evidence_is_partial(profile):
    m = _match(profile, _req(Cat.SKILL, "TensorFlow", "TensorFlow"))
    assert m.status is MatchStatus.PARTIAL and m.evidence_ids == []
    assert "no experience" in m.explanation


def test_related_term_is_partial_never_supported(profile):
    m = _match(profile, _req(Cat.SKILL, "Apache Spark", "Apache Spark"))
    assert (m.status, m.match_type) == (MatchStatus.PARTIAL, MatchType.RELATED)
    assert m.evidence_ids == ["bul-a2"] and "not the same as" in m.explanation


def test_spokes_of_same_hub_are_not_related(profile):
    # TensorFlow and PyTorch are both "related" to Deep Learning, but not to each other.
    p = profile.model_copy(update={"skills": [s for s in profile.skills if s.name != "TensorFlow"]})
    m = _match(p, _req(Cat.SKILL, "TensorFlow", "TensorFlow"))
    assert m.status is MatchStatus.NOT_DOCUMENTED


def test_unknown_skill_not_documented(profile):
    assert _match(profile, _req(Cat.SKILL, "Rust", "Rust")).status is MatchStatus.NOT_DOCUMENTED


def test_out_of_vocabulary_term_found_by_plain_text(profile):
    m = _match(profile, _req(Cat.SKILL, "fraud detection", "fraud detection"))
    assert m.status is MatchStatus.SUPPORTED and m.evidence_ids == ["bul-a2"]


def test_summary_and_skills_list_are_not_evidence():
    p = MasterProfile(contact=Contact(full_name="F"), summary="Expert in Rust.", skills=[Skill(name="Go")])
    assert _match(p, _req(Cat.SKILL, "Rust", "Rust")).status is MatchStatus.NOT_DOCUMENTED
    assert _match(p, _req(Cat.SKILL, "Go", "Go")).status is MatchStatus.PARTIAL


def test_user_linked_skill_evidence_counts():
    p = MasterProfile(
        contact=Contact(full_name="F"),
        experience=[Experience(id="exp-1", employer="E", title="T", bullets=[Bullet(id="bul-1", text="Did things.")])],
        skills=[Skill(name="Fictional Tool", evidence_ids=["bul-1"])])
    m = _match(p, _req(Cat.SKILL, "Fictional Tool", "Fictional Tool"))
    assert m.status is MatchStatus.SUPPORTED and m.evidence_ids == ["bul-1"]


# ---- experience -------------------------------------------------------------------


def test_overall_experience_merges_overlaps(profile):
    # 2020-01..2022-06 and 2022-01..2026-10 merge to 2020-01..2026-10 = 82 months (~6.8 yrs).
    m = _match(profile, _req(Cat.EXPERIENCE, "5+ years", "overall", min_years=5))
    assert (m.status, m.match_type) == (MatchStatus.SUPPORTED, MatchType.COMPUTED)
    assert "6.8 years" in m.explanation and set(m.evidence_ids) == {"exp-a", "exp-b"}


def test_overall_experience_short_is_partial(profile):
    m = _match(profile, _req(Cat.EXPERIENCE, "10+ years", "overall", min_years=10))
    assert m.status is MatchStatus.PARTIAL and "10+ years" in m.explanation


def test_overall_experience_above_max_notes_it(profile):
    m = _match(profile, _req(Cat.EXPERIENCE, "2-4 years", "overall", min_years=2, max_years=4))
    assert m.status is MatchStatus.SUPPORTED and "above the stated 4-year maximum" in m.explanation


def test_undated_roles_are_not_guessed():
    p = MasterProfile(contact=Contact(full_name="F"), experience=[Experience(employer="E", title="T")])
    m = _match(p, _req(Cat.EXPERIENCE, "3+ years", "overall", min_years=3))
    assert m.status is MatchStatus.PARTIAL and "no start dates" in m.explanation
    empty = MasterProfile(contact=Contact(full_name="F"))
    assert _match(empty, _req(Cat.EXPERIENCE, "3+ years", "overall", min_years=3)).status is MatchStatus.NOT_DOCUMENTED


def test_skill_specific_years_never_auto_supported(profile):
    m = _match(profile, _req(Cat.EXPERIENCE, "4+ years of PyTorch", "PyTorch", min_years=4))
    assert m.status is MatchStatus.PARTIAL and "Confirm the years yourself" in m.explanation
    assert _match(profile, _req(Cat.EXPERIENCE, "3+ years Rust", "Rust", min_years=3)).status \
        is MatchStatus.NOT_DOCUMENTED


# ---- education / certification / domain / text -----------------------------------


def test_education_level_and_field(profile):
    assert _match(profile, _req(Cat.EDUCATION, "Bachelor's degree", "Bachelor's")).status is MatchStatus.SUPPORTED
    cs = _match(profile, _req(Cat.EDUCATION, "Bachelor's in Computer Science", "Bachelor's"))
    assert cs.status is MatchStatus.PARTIAL and "computer science" in cs.explanation
    assert _match(profile, _req(Cat.EDUCATION, "B.Tech in any specialization", "Bachelor's")).status \
        is MatchStatus.SUPPORTED
    assert _match(profile, _req(Cat.EDUCATION, "Master's degree", "Master's")).status is MatchStatus.NOT_DOCUMENTED


def test_certification(profile):
    assert _match(profile, _req(Cat.CERTIFICATION, "Fictional Cloud Practitioner certification")).status \
        is MatchStatus.SUPPORTED
    issuer = _match(profile, _req(Cat.CERTIFICATION, "FictionalCloud Solutions Architect certification"))
    assert issuer.status is MatchStatus.PARTIAL
    assert _match(profile, _req(Cat.CERTIFICATION, "PMP certification")).status is MatchStatus.NOT_DOCUMENTED


def test_domain(profile):
    assert _match(profile, _req(Cat.DOMAIN, "FinTech", "FinTech")).evidence_ids == ["exp-a"]
    assert _match(profile, _req(Cat.DOMAIN, "Healthcare", "Healthcare")).status is MatchStatus.NOT_DOCUMENTED


def test_text_overlap_levels(profile):
    strong = _match(profile, _req(Cat.RESPONSIBILITY, "Deploy PyTorch models on Kubernetes clusters"))
    assert (strong.status, strong.match_type) == (MatchStatus.SUPPORTED, MatchType.TEXT)
    assert strong.evidence_ids[0] == "bul-a1" and "not proof" in strong.explanation
    weak = _match(profile, _req(Cat.RESPONSIBILITY, "Create SQL dashboards for executive stakeholders"))
    assert weak.status is MatchStatus.PARTIAL
    none = _match(profile, _req(Cat.QUALIFICATION, "Excellent written communication"))
    assert none.status is MatchStatus.NOT_DOCUMENTED


def test_stemming_is_consistent():
    assert content_tokens("deploys deployed deploying") == {"deploy"}
    assert content_tokens("service services") == content_tokens("service")
    assert content_tokens("built") == content_tokens("build")


# ---- report -------------------------------------------------------------------------


@pytest.fixture
def analysis() -> JDAnalysis:
    return JDAnalysis(job_id="job-1", jd_hash="h", requirements=[
        _req(Cat.SKILL, "PyTorch", "PyTorch"),
        _req(Cat.SKILL, "Apache Spark", "Apache Spark"),
        _req(Cat.SKILL, "Rust", "Rust"),
        _req(Cat.SKILL, "Go", "Go", importance=Importance.PREFERRED),
        _req(Cat.SKILL, "LangChain", "LangChain", importance=Importance.PREFERRED),
    ])


def test_report_summary_formula(profile, analysis):
    report, notes = build_match_report(analysis, profile, today=TODAY)
    assert notes == [] and report.profile_version == profile.profile_version
    s = summarize(report, analysis)
    req = s.groups[Importance.REQUIRED]
    assert (req.supported, req.partial, req.not_documented) == (1, 1, 1)
    assert req.coverage == pytest.approx(0.5)
    assert s.groups[Importance.PREFERRED].coverage == pytest.approx(0.5)  # LangChain 1 + Go 0
    assert s.overall == pytest.approx((3 * 1.5 + 2 * 1) / 13)
    assert s.groups[Importance.UNSPECIFIED].coverage is None
    assert [r.normalized_term for r in gaps(report, analysis)] == ["Rust", "Go"]  # required first


def test_overrides_validate_and_survive_rerun(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    rust = analysis.requirements[2]
    with pytest.raises(OverrideError, match="at least one evidence"):
        set_override(report, rust.id, MatchStatus.SUPPORTED, [], "", profile)
    with pytest.raises(OverrideError, match="Unknown evidence"):
        set_override(report, rust.id, MatchStatus.SUPPORTED, ["bul-nope"], "", profile)
    with pytest.raises(OverrideError, match="cannot cite"):
        set_override(report, rust.id, MatchStatus.NOT_DOCUMENTED, ["bul-a1"], "", profile)

    report = set_override(report, rust.id, MatchStatus.PARTIAL, ["bul-a2"], "Used Rust UDFs", profile)
    assert report.by_requirement()[rust.id].effective_status is MatchStatus.PARTIAL
    assert summarize(report, analysis).overrides == 1

    rerun, notes = build_match_report(analysis, profile, previous=report, today=TODAY)
    assert rerun.by_requirement()[rust.id].override.note == "Used Rust UDFs" and notes == []

    # If the cited evidence disappears, the override is dropped with a note.
    p2 = profile.model_copy(deep=True)
    p2.experience[0].bullets = p2.experience[0].bullets[:1]
    rerun2, notes2 = build_match_report(analysis, MasterProfile.model_validate(p2.model_dump()),
                                        previous=report, today=TODAY)
    assert rerun2.by_requirement()[rust.id].override is None and notes2

    cleared = clear_override(report, rust.id)
    assert cleared.by_requirement()[rust.id].override is None


def test_stale_reasons(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    assert stale_reasons(report, analysis, profile) == []
    newer = profile.model_copy(update={"profile_version": profile.profile_version + 1})
    assert "profile changed" in stale_reasons(report, analysis, newer)[0]
    edited = analysis.model_copy(update={"requirements": analysis.requirements[:-1]})
    assert stale_reasons(report, edited, profile) == ["The JD analysis changed."]
    # Confirming the analysis does not make the report stale.
    confirmed = analysis.model_copy(update={"confirmed_at": TODAY})
    assert stale_reasons(report, confirmed, profile) == []


def test_recommendations(profile, analysis):
    report, _ = build_match_report(analysis, profile, today=TODAY)
    roles = [RoleProfile(id="role-ml", name="ML", evidence_ids=["exp-a"]),
             RoleProfile(id="role-gen", name="GenAI", evidence_ids=["prj-x"]),
             RoleProfile(id="role-none", name="Analyst", evidence_ids=["exp-b"])]
    recs = recommend_role_profiles(report, analysis, profile, roles)
    assert [r.id for r in recs] == ["role-ml", "role-gen"]  # role-none covers nothing evidenced
    assert set(recs[0].covered) == {"PyTorch", "Apache Spark"}  # bullets of exp-a count
    [proj] = recommend_projects(report, analysis, profile)
    assert proj.id == "prj-x" and proj.covered == ["LangChain"]


def test_end_to_end_with_sample_profile(sample_profile):
    from src.schemas.job import Job
    from src.services.jd_parser import parse_jd

    jd = "Requirements\n• Strong Python and SQL\n• Experience with Kubernetes\nNice to have\n• LlamaIndex"
    analysis = parse_jd(Job(description=jd)).analysis
    report, _ = build_match_report(analysis, sample_profile, today=TODAY)
    status = {r.normalized_term: report.by_requirement()[r.id].status for r in analysis.requirements}
    assert status["Python"] is MatchStatus.SUPPORTED and status["SQL"] is MatchStatus.SUPPORTED
    assert status["Kubernetes"] is MatchStatus.PARTIAL  # only Docker (related) is evidenced
    assert status["LlamaIndex"] is MatchStatus.PARTIAL  # related to RAG/LLMs, not claimed
