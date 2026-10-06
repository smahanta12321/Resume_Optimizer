"""Deterministic evidence matcher (``rules-v1``): JD requirements -> master-profile evidence.

Rules (see README "How matching decides"):

* Only evidence items (experience, project, bullet, education, certification,
  achievement) can support a requirement. The skills list, headline and summary
  are claims, not evidence.
* Same term (or a recorded alias) in evidence -> ``supported``. A *related*
  term -> at most ``partial``. A skill listed without linked evidence -> ``partial``.
* Overall experience is computed from dated roles, with overlapping periods
  counted once. Years with a *specific* skill are never inferred from role
  dates, so that is at most ``partial``.
* Free-text requirements use word overlap, which is a hint, labelled as such.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from src.schemas.analysis import JDAnalysis, Requirement, RequirementCategory
from src.schemas.match import MatchReport, MatchStatus, MatchType, RequirementMatch
from src.schemas.profile import MasterProfile
from src.services.jd_analysis_service import vocabulary_from_profile
from src.services.jd_parser import education_level
from src.services.skill_taxonomy import DOMAIN_TERMS, SkillTerm, find_terms, lookup, related_terms

logger = logging.getLogger(__name__)

MATCHER_NAME = "rules-v1"

# Text-overlap thresholds (share of the requirement's content words found in one evidence item).
TEXT_SUPPORTED_COVERAGE = 0.75
TEXT_PARTIAL_COVERAGE = 0.34
MAX_TEXT_EVIDENCE = 3

_EDU_RANK = {"Diploma": 1, "Bachelor's": 2, "Degree": 2, "Master's": 3, "PhD": 4}
_FIELDS = ("computer science", "computer engineering", "information technology", "software engineering",
           "data science", "statistics", "mathematics", "physics", "electrical", "electronics", "economics",
           "business", "engineering")
_ANY_FIELD = re.compile(r"\bany (?:specialization|discipline|stream|field)\b|\bany graduate\b", re.I)

_STOPWORDS = frozenset("""
a an and are as at be been by can etc for from has have in including into is it its of on or our such that the
their this to we who will with within you your across able ability strong excellent good great solid proven
work working team teams use using used experience experienced knowledge understanding proficiency proficient
hands skills skill years year plus related relevant must should would preferred required requirements
role candidate ideal familiarity familiar demonstrated track record environment environments high quality new
various multiple other well least minimum similar equivalent level levels
""".split())
_IRREGULAR = {"built": "build", "led": "lead", "wrote": "write", "written": "write", "ran": "run", "made": "make",
              "taught": "teach", "drove": "drive", "driven": "drive", "grew": "grow", "grown": "grow"}
_WORD_RE = re.compile(r"[a-z][a-z0-9+#]*")


# ---- evidence index -------------------------------------------------------------


@dataclass
class EvidenceDoc:
    id: str
    kind: str
    label: str
    text: str
    terms: set[str] = field(default_factory=set)   # canonical skill names, casefolded
    linked: set[str] = field(default_factory=set)  # subset of terms the user tagged explicitly (skills fields/links)
    tokens: set[str] = field(default_factory=set)  # stemmed content words
    parent_id: Optional[str] = None                # experience/project that owns a bullet


def _stem(word: str) -> str:
    """Very light, consistent stemming: deploys/deployed/deploying -> deploy; service/services -> servic."""
    w = _IRREGULAR.get(word, word)
    for suf in ("ations", "ation", "ments", "ment"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    if w.endswith("ies") and len(w) > 5:
        w = w[:-3] + "y"
    elif w.endswith("ing") and len(w) - 3 >= 4:
        w = w[:-3]
    elif w.endswith("ed") and len(w) - 2 >= 4:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) - 1 >= 4:
        w = w[:-1]
    if w.endswith("e") and len(w) >= 5:
        w = w[:-1]
    return w


def content_tokens(text: str) -> set[str]:
    return {_stem(w) for w in _WORD_RE.findall(text.casefold()) if len(w) > 2 and w not in _STOPWORDS}


def canonical(name: str, extra: list[SkillTerm]) -> str:
    term = lookup(name, extra)
    return term.name if term else name.strip()


@dataclass
class ProfileIndex:
    profile: MasterProfile
    extra: list[SkillTerm]
    docs: list[EvidenceDoc]
    skills_by_canon: dict[str, str]  # canonical casefold -> profile skill name

    @property
    def by_id(self) -> dict[str, EvidenceDoc]:
        return {d.id: d for d in self.docs}

    def with_term(self, key: str) -> list[EvidenceDoc]:
        k = key.casefold()
        hits = [d for d in self.docs if k in d.terms]
        if not hits and lookup(key, self.extra) is None:
            # Term outside the vocabulary (e.g. a user-added requirement): plain whole-word search.
            rx = re.compile(r"(?<![\w+#])" + re.escape(key) + r"(?![\w+#])", re.I)
            hits = [d for d in self.docs if rx.search(d.text)]
        return hits


def build_index(profile: MasterProfile) -> ProfileIndex:
    """Index every evidence item with its recognized skill terms and content words."""
    extra = vocabulary_from_profile(profile)
    docs: list[EvidenceDoc] = []

    def add(item_id: str, kind: str, label: str, text: str, skills: list[str] = (), parent: Optional[str] = None):
        linked = {canonical(s, extra).casefold() for s in skills}
        terms = {h.term.name.casefold() for h in find_terms(text, extra)} | linked
        docs.append(EvidenceDoc(item_id, kind, label, text, terms, linked, content_tokens(text), parent))

    for exp in profile.experience:
        add(exp.id, "experience", f"{exp.title} @ {exp.employer}",
            " ".join([exp.title, exp.employer, exp.description, exp.employment_type]), exp.skills)
        for b in exp.bullets:
            add(b.id, "bullet", f"• {b.text[:80]}", b.text, b.skills, exp.id)
    for prj in profile.projects:
        add(prj.id, "project", f"Project: {prj.name}", " ".join([prj.name, prj.role, prj.description]), prj.skills)
        for b in prj.bullets:
            add(b.id, "bullet", f"• {b.text[:80]}", b.text, b.skills, prj.id)
    for edu in profile.education:
        add(edu.id, "education", f"{edu.degree}, {edu.institution}",
            " ".join([edu.degree, edu.field_of_study, edu.institution]))
    for crt in profile.certifications:
        add(crt.id, "certification", f"Cert: {crt.name}", " ".join([crt.name, crt.issuer]))
    for ach in profile.achievements:
        add(ach.id, "achievement", f"Achievement: {ach.title}", " ".join([ach.title, ach.description]))

    # Skills the user explicitly linked to evidence count as present in that evidence.
    by_id = {d.id: d for d in docs}
    skills_by_canon: dict[str, str] = {}
    for skill in profile.skills:
        key = canonical(skill.name, extra).casefold()
        skills_by_canon[key] = skill.name
        for alias in skill.aliases:
            skills_by_canon.setdefault(canonical(alias, extra).casefold(), skill.name)
        for eid in skill.evidence_ids:
            if eid in by_id:
                by_id[eid].terms.add(key)
                by_id[eid].linked.add(key)
    return ProfileIndex(profile, extra, docs, skills_by_canon)


# ---- helpers ----------------------------------------------------------------------


def _labels(docs: list[EvidenceDoc], limit: int = 3) -> str:
    shown = "; ".join(d.label for d in docs[:limit])
    return shown + (f"; and {len(docs) - limit} more" if len(docs) > limit else "")


def _result(req: Requirement, status: MatchStatus, mtype: MatchType, docs: list[EvidenceDoc],
            explanation: str, score: float) -> RequirementMatch:
    ids = list(dict.fromkeys(d.id for d in docs))
    return RequirementMatch(requirement_id=req.id, status=status, match_type=mtype, evidence_ids=ids,
                            explanation=explanation, score=round(max(0.0, min(score, 1.0)), 2))


def _month_index(ym: str) -> int:
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def _merged_months(intervals: list[tuple[int, int]]) -> int:
    total, cur_start, cur_end = 0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def _years(months: int) -> str:
    return f"{months / 12:.1f}".rstrip("0").rstrip(".")


# ---- per-category matchers --------------------------------------------------------


def _match_skill(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    wording = (req.normalized_term or req.text).strip()
    key = canonical(wording, idx.extra)
    docs = idx.with_term(key)
    listed = idx.skills_by_canon.get(key.casefold())
    if docs:
        # "exact": the evidence uses this wording, or the user tagged the skill on it.
        # "alias": found only under a recorded alternative name (e.g. JD "Kubernetes", evidence "k8s").
        word_rx = re.compile(r"(?<![\w+#])" + re.escape(wording) + r"(?![\w+#])", re.I)
        literal = any(word_rx.search(d.text) or key.casefold() in d.linked for d in docs)
        mtype = MatchType.EXACT if literal else MatchType.ALIAS
        note = "" if listed else " It is not in your skills list yet; consider adding it."
        alias_note = ""
        if not literal:
            forms = _surface_forms(key, docs, idx)
            alias_note = (f" as “{'”, “'.join(forms)}” (a recorded alternative name)" if forms
                          else " under a recorded alternative name")
        return _result(req, MatchStatus.SUPPORTED, mtype, docs,
                       f"{key} appears{alias_note} in {len(docs)} evidence item(s): {_labels(docs)}.{note}", 1.0)
    if listed:
        return _result(req, MatchStatus.PARTIAL, MatchType.EXACT, [],
                       f"“{listed}” is in your skills list, but no experience, project or other evidence shows it. "
                       "Link evidence to it on the Master Profile page.", 0.5)
    rel = related_terms(key)
    rel_docs = [d for d in idx.docs if {r.casefold() for r in rel} & d.terms]
    if rel_docs:
        found = sorted({r for r in rel if any(r.casefold() in d.terms for d in rel_docs)})
        return _result(req, MatchStatus.PARTIAL, MatchType.RELATED, rel_docs,
                       f"Your evidence shows {', '.join(found)}: related to, but not the same as, {key}. "
                       f"Only claim {key} if you have actually used it.", 0.4)
    return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [], f"No evidence of {key} in your profile.", 0.0)


def _surface_forms(key: str, docs: list[EvidenceDoc], idx: ProfileIndex) -> list[str]:
    """The exact wordings under which ``key`` appears in the evidence text (for explanations)."""
    term = lookup(key, idx.extra)
    if term is None:
        return []
    rx = term.regex()
    return sorted({m.group(0) for d in docs for m in rx.finditer(d.text)}, key=str.casefold)[:3]


def _role_intervals(idx: ProfileIndex, today: date) -> tuple[list[tuple[int, int, str]], list[str]]:
    now = today.year * 12 + today.month - 1
    dated, undated = [], []
    for exp in idx.profile.experience:
        if not exp.start_date:
            undated.append(exp.id)
            continue
        end = _month_index(exp.end_date) + 1 if exp.end_date else now + 1
        dated.append((_month_index(exp.start_date), max(end, _month_index(exp.start_date) + 1), exp.id))
    return dated, undated


def _match_experience(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    term = (req.normalized_term or "").strip()
    dated, undated = _role_intervals(idx, today)
    if term and term.casefold() != "overall":
        key = canonical(term, idx.extra)
        docs = idx.with_term(key)
        if not docs:
            return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [],
                           f"No evidence of {key} in your profile.", 0.0)
        owners = {d.parent_id or d.id for d in docs}
        months = _merged_months([(s, e) for s, e, i in dated if i in owners])
        span = f" Roles showing it span about {_years(months)} years," if months else ""
        return _result(req, MatchStatus.PARTIAL, MatchType.EXACT, docs,
                       f"{key} appears in your evidence.{span} but the profile does not record how long you used "
                       f"{key} itself. Confirm the years yourself before claiming them.", 0.5)

    if not dated:
        status = MatchStatus.PARTIAL if undated else MatchStatus.NOT_DOCUMENTED
        msg = ("Your roles have no start dates, so experience can't be computed. Add dates on the Master Profile page."
               if undated else "No work experience is recorded in your profile.")
        return _result(req, status, MatchType.COMPUTED, [], msg, 0.0)
    months = _merged_months([(s, e) for s, e, _ in dated])
    docs = [idx.by_id[i] for _, _, i in dated]
    summary = f"Your dated roles total about {_years(months)} years (overlapping periods counted once)."
    if undated:
        summary += f" {len(undated)} role(s) without dates were not counted."
    lo, hi = req.min_years, req.max_years
    if lo is None or months >= lo * 12:
        if hi is not None and months > hi * 12:
            summary += f" That is above the stated {hi:g}-year maximum; whether that matters is your call."
        return _result(req, MatchStatus.SUPPORTED, MatchType.COMPUTED, docs, summary, 1.0)
    return _result(req, MatchStatus.PARTIAL, MatchType.COMPUTED, docs,
                   f"{summary} The JD asks for {lo:g}+ years.", months / (lo * 12))


def _match_education(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    level = req.normalized_term if req.normalized_term in _EDU_RANK else education_level(req.text)
    if not level:
        return _match_text(req, idx, today)
    edu_docs = [d for d in idx.docs if d.kind == "education"]
    meeting = [d for d in edu_docs if _EDU_RANK.get(education_level(d.text), 0) >= _EDU_RANK[level]
               and education_level(d.text) != "Degree"]
    equivalent = bool(re.search(r"\bor equivalent\b", req.text, re.I))
    if not meeting:
        msg = f"No {level} recorded in your education."
        if equivalent:
            msg += " The JD accepts equivalent experience; judge whether yours qualifies."
        unclear = [d for d in edu_docs if education_level(d.text) in ("", "Degree")]
        if unclear:
            return _result(req, MatchStatus.PARTIAL, MatchType.COMPUTED, unclear,
                           msg + " Some entries don't state a level clearly.", 0.3)
        return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [], msg, 0.0)
    wanted = [] if _ANY_FIELD.search(req.text) else [f for f in _FIELDS if f in req.text.casefold()]
    if wanted:
        in_field = [d for d in meeting if any(f in d.text.casefold() for f in wanted)]
        if not in_field:
            return _result(req, MatchStatus.PARTIAL, MatchType.COMPUTED, meeting,
                           f"Your degree meets the {level} level ({_labels(meeting)}), but the JD names "
                           f"{', '.join(wanted)} and your recorded field differs.", 0.6)
        meeting = in_field
    return _result(req, MatchStatus.SUPPORTED, MatchType.COMPUTED, meeting,
                   f"Meets the {level} level: {_labels(meeting)}.", 1.0)


def _match_certification(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    req_tokens = content_tokens(req.text) - {"certif", "certification", "certified", "certificate"}
    best, best_cov, issuer_docs = None, 0.0, []
    for crt in idx.profile.certifications:
        name_tokens = content_tokens(crt.name) - {"certif", "certification", "certified", "certificate"}
        if not name_tokens:
            continue
        cov = len(name_tokens & req_tokens) / len(name_tokens)
        if cov > best_cov:
            best, best_cov = crt, cov
        if crt.issuer and content_tokens(crt.issuer) & req_tokens:
            issuer_docs.append(idx.by_id[crt.id])
    if best is not None and best_cov >= 0.6:
        mtype = MatchType.EXACT if best.name.casefold() in req.text.casefold() else MatchType.TEXT
        return _result(req, MatchStatus.SUPPORTED, mtype, [idx.by_id[best.id]],
                       f"Matches your certification “{best.name}”.", best_cov)
    if issuer_docs:
        return _result(req, MatchStatus.PARTIAL, MatchType.TEXT, issuer_docs,
                       f"You hold a certification from the same issuer ({_labels(issuer_docs)}), "
                       "but not clearly the one named.", 0.3)
    return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [], "No matching certification recorded.", 0.0)


def _match_domain(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    key = (req.normalized_term or req.text).strip()
    terms = [t for t in DOMAIN_TERMS if t.name.casefold() == key.casefold()]
    docs = ([d for d in idx.docs if find_terms(d.text, terms=terms)] if terms else idx.with_term(key))
    if docs:
        return _result(req, MatchStatus.SUPPORTED, MatchType.EXACT, docs,
                       f"{key} appears in: {_labels(docs)}.", 1.0)
    return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [],
                   f"No {key} work is mentioned in your evidence. Domain fit can also be shown in the summary "
                   "only if it is true.", 0.0)


def _match_text(req: Requirement, idx: ProfileIndex, today: date) -> RequirementMatch:
    req_tokens = content_tokens(req.text)
    if not req_tokens:
        return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [], "Nothing specific to compare.", 0.0)
    scored = []
    for d in idx.docs:
        shared = req_tokens & d.tokens
        if len(shared) >= 2:
            scored.append((len(shared) / len(req_tokens), d, shared))
    scored.sort(key=lambda t: -t[0])
    top = [t for t in scored if t[0] >= TEXT_PARTIAL_COVERAGE][:MAX_TEXT_EVIDENCE]
    if not top:
        return _result(req, MatchStatus.NOT_DOCUMENTED, MatchType.NONE, [],
                       "No evidence uses similar wording.", scored[0][0] if scored else 0.0)
    cov, best, shared = top[0]
    words = ", ".join(sorted(shared)[:6])
    if cov >= TEXT_SUPPORTED_COVERAGE and len(req_tokens) >= 3 and len(shared) >= 3:
        return _result(req, MatchStatus.SUPPORTED, MatchType.TEXT, [t[1] for t in top],
                       f"Closely matches the wording of {best.label} (shared: {words}). "
                       "Wording overlap is a strong hint, not proof; check it.", cov)
    return _result(req, MatchStatus.PARTIAL, MatchType.TEXT, [t[1] for t in top],
                   f"Some overlap with {best.label} (shared: {words}). Check whether it really covers this.", cov)


_MATCHERS: dict[RequirementCategory, Callable[[Requirement, ProfileIndex, date], RequirementMatch]] = {
    RequirementCategory.SKILL: _match_skill,
    RequirementCategory.EXPERIENCE: _match_experience,
    RequirementCategory.EDUCATION: _match_education,
    RequirementCategory.CERTIFICATION: _match_certification,
    RequirementCategory.DOMAIN: _match_domain,
    RequirementCategory.RESPONSIBILITY: _match_text,
    RequirementCategory.QUALIFICATION: _match_text,
}


# ---- report -----------------------------------------------------------------------


def analysis_fingerprint(analysis: JDAnalysis) -> str:
    """Hash of the analysis content that matching depends on (not timestamps or confirmation)."""
    payload = analysis.model_dump_json(include={"requirements", "experience_min_years", "experience_max_years",
                                                "work_arrangement"})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def match_requirement(req: Requirement, idx: ProfileIndex, today: Optional[date] = None) -> RequirementMatch:
    return _MATCHERS[req.category](req, idx, today or date.today())


def build_match_report(
    analysis: JDAnalysis,
    profile: MasterProfile,
    *,
    previous: Optional[MatchReport] = None,
    today: Optional[date] = None,
) -> tuple[MatchReport, list[str]]:
    """Match every requirement. Returns ``(report, notes)``.

    User overrides from ``previous`` are kept for requirements that still exist;
    evidence IDs no longer in the profile are dropped, and an override left
    without required evidence is discarded (reported in ``notes``).
    """
    idx = build_index(profile)
    today = today or date.today()
    matches = [match_requirement(r, idx, today) for r in analysis.requirements]
    notes: list[str] = []
    if previous is not None:
        old = previous.by_requirement()
        known = set(idx.by_id)
        for i, m in enumerate(matches):
            prev = old.get(m.requirement_id)
            if prev is None or prev.override is None:
                continue
            ov = prev.override
            kept = [e for e in ov.evidence_ids if e in known]
            if ov.status is not MatchStatus.NOT_DOCUMENTED and not kept:
                notes.append(f"Your override for requirement {m.requirement_id} was removed because its "
                             "evidence no longer exists in the profile.")
                continue
            matches[i] = m.model_copy(update={"override": ov.model_copy(update={"evidence_ids": kept})})
    report = MatchReport(job_id=analysis.job_id, matcher=MATCHER_NAME, profile_version=profile.profile_version,
                         analysis_fingerprint=analysis_fingerprint(analysis), matches=matches)
    logger.info("event=match_built job_id=%s requirements=%d supported=%d", analysis.job_id, len(matches),
                sum(m.status is MatchStatus.SUPPORTED for m in matches))
    return report, notes


def documented_experience_years(profile: MasterProfile, today: Optional[date] = None) -> float:
    """Total years across dated roles, overlaps counted once (same rule as overall-experience matching)."""
    idx = ProfileIndex(profile, [], [], {})
    dated, _ = _role_intervals(idx, today or date.today())
    return _merged_months([(s, e) for s, e, _ in dated]) / 12
