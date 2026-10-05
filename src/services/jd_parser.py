"""Deterministic JD parser (``rules-v1``): JD text -> draft ``JDAnalysis``.

The output is a first draft for the user to correct, not ground truth. The JD
text is untrusted: it is only pattern-matched, never executed or followed, and
text that looks like instructions to an AI is reported as a warning.

Pipeline: split into lines -> detect section headings (LinkedIn/Naukri/common
wording) -> split sections into items -> extract skills, experience,
education, certifications, responsibilities, qualifications and domain terms
-> merge duplicates -> order for review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from src.schemas.analysis import (
    Importance,
    JDAnalysis,
    Requirement,
    RequirementCategory,
    WorkArrangement,
)
from src.schemas.job import Job
from src.services.jd_import_service import description_hash
from src.services.skill_taxonomy import DOMAIN_TERMS, SkillTerm, find_terms, lookup

PARSER_NAME = "rules-v1"


class Section(str, Enum):
    INTRO = "intro"  # text before the first recognized heading
    OTHER = "other"  # under a heading we don't classify (e.g. "Job Description", "About the role")
    RESPONSIBILITIES = "responsibilities"
    REQUIRED = "required"
    PREFERRED = "preferred"
    EDUCATION = "education"
    KEY_SKILLS = "key_skills"
    ABOUT_COMPANY = "about_company"  # used only for domain terms
    IGNORE = "ignore"  # benefits, EEO, how to apply


# Checked in order: more specific patterns first ("preferred qualifications" before "qualifications").
_HEADINGS: list[tuple[Section, str]] = [
    (Section.ABOUT_COMPANY, r"about (?:us|the company|the team|our company)|who we are"
                            r"|our (?:company|story|mission|culture|values)|company (?:overview|description|profile)"),
    (Section.IGNORE, r"benefits|perks|what we offer|why (?:join|work)|compensation|salary"
                     r"|equal (?:employment )?opportunit|eeo|diversity|how to apply|application process|life at"
                     r"|our benefits"),
    (Section.PREFERRED, r"preferred|nice[- ]to[- ]haves?|good[- ]to[- ]haves?|bonus(?: points)?|pluses|desired skills"
                        r"|desirable|additional (?:qualifications|skills)|it would be (?:great|nice)"),
    (Section.EDUCATION, r"education(?: ug| pg)?|educational qualifications?|academic qualifications?|ug|pg|doctorate"),
    (Section.KEY_SKILLS, r"key ?skills|skills|top skills|tech(?:nology)? stack|tools (?:and|&) technologies"),
    (Section.RESPONSIBILITIES, r"(?:key |job |main |primary )?responsibilities|roles? (?:and|&) responsibilities"
                               r"|what you(?:'|’)?ll do|what you will do|your role|the role|duties|day[- ]to[- ]day"
                               r"|in this role|your impact|what you(?:'|’)?ll be doing|responsibilities include"),
    (Section.REQUIRED, r"(?:minimum |basic |required |key |essential )?(?:qualifications|requirements)"
                       r"|required skills|skills required|must[- ]haves?|what we(?:'|’)?re looking for"
                       r"|what we are looking for|who you are|what you bring|what you(?:'|’)?ll need"
                       r"|(?:desired )?candidate profile|eligibility(?: criteria)?|about you|you have"
                       r"|skills (?:and|&) (?:experience|qualifications)|technical skills|requirements (?:and|&) qualifications"),
    (Section.OTHER, r"job description|about (?:the|this) (?:role|job|position|opportunity)|overview|summary"
                    r"|role overview|job summary|position summary|description"),
]
_HEADING_RES = [(sec, re.compile(rf"^(?:{pat})\b", re.I)) for sec, pat in _HEADINGS]

# "Key: value" lines that carry job metadata (Naukri and many career sites).
_META_KEYS = {
    "role": "title", "job title": "title", "title": "title", "position": "title", "designation": "title",
    "company": "company", "company name": "company", "organization": "company",
    "location": "location", "locations": "location", "job location": "location",
    "work mode": "arrangement", "workplace type": "arrangement", "work type": "arrangement",
    "experience": "experience", "experience required": "experience", "work experience": "experience",
    "education ug": "education", "education pg": "education", "ug": "education", "pg": "education",
    "doctorate": "education", "education": "education",
    "industry type": "domain", "industry": "domain",
    # Naukri/LinkedIn listing fields with no requirement content
    "department": "skip", "employment type": "skip", "role category": "skip", "functional area": "skip",
    "salary": "skip", "ctc": "skip", "openings": "skip", "applicants": "skip", "posted": "skip",
    "job type": "skip", "seniority level": "skip", "job function": "skip", "notice period": "skip",
}
_META_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z /&]{1,30}?)\s*[:\-–]\s+(?P<value>\S.{0,200})$")

_BULLET_RE = re.compile(r"^\s*(?:[•●▪■◦‣∙·\-–—*+>]|\(?\d{1,2}[.)]|\(?[a-z][.)](?=\s))\s*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z(\"'])")

_YEARS = r"(\d{1,2}(?:\.\d)?)"
_EXPERIENCE_RES = [
    # "3-5 years", "3 to 5 yrs", "3 - 8 Yrs"
    (re.compile(rf"{_YEARS}\s*\+?\s*(?:-|–|—|to)\s*{_YEARS}\s*\+?\s*(?:years?|yrs?)\b", re.I), "range"),
    # "minimum 3 years", "at least 5 yrs", "min. of 2 years"
    (re.compile(rf"(?:minimum|min\.?|at least|atleast)\s*(?:of\s*)?{_YEARS}\s*\+?\s*(?:years?|yrs?)\b", re.I), "min"),
    # "up to 3 years", "maximum 4 yrs"
    (re.compile(rf"(?:up ?to|maximum|max\.?)\s*(?:of\s*)?{_YEARS}\s*(?:years?|yrs?)\b", re.I), "max"),
    # "5+ years", "5 years"
    (re.compile(rf"{_YEARS}\s*(\+|plus)?\s*(?:years?|yrs?)\b", re.I), "min"),
]
_EXPERIENCE_CONTEXT = re.compile(r"\bexp(?:erience[ds]?)?\b|\bhands[- ]on\b|\bworking (?:with|in|on)\b", re.I)

_EDU_RE = re.compile(
    r"\b(?:ph\.?\s?d|doctorate|master'?s?|m\.?\s?tech|m\.?\s?sc|mca|mba|post[- ]?graduat\w*|bachelor'?s?"
    r"|b\.?\s?tech|b\.?\s?sc|bca|undergraduate|any graduate|graduate degree|degree|diploma)\b"
    r"|(?<![\w.])B\.E\.?(?=[\s/,)]|$)|(?<![\w.])M\.E\.(?=[\s/,)]|$)",
    re.I,
)
_EDU_LEVELS = [
    (re.compile(r"ph\.?\s?d|doctorate", re.I), "PhD"),
    (re.compile(r"master|m\.?\s?tech|m\.?\s?sc|mca|mba|post[- ]?graduat|\bM\.E\.", re.I), "Master's"),
    (re.compile(r"bachelor|b\.?\s?tech|b\.?\s?sc|bca|\bB\.E\b|undergraduate|graduate", re.I), "Bachelor's"),
    (re.compile(r"diploma", re.I), "Diploma"),
    (re.compile(r"degree", re.I), "Degree"),
]
_CERT_RE = re.compile(r"\bcertifi(?:ed|cation|cations)\b|\bcertificate\b", re.I)

_PREFERRED_CUE = re.compile(
    r"\bnice[- ]to[- ]have\b|\bpreferred\b|\bpreferably\b|\b(?:is |are |would be )?a (?:big )?plus\b|\bbonus\b"
    r"|\bgood[- ]to[- ]have\b|\bdesirable\b|\badvantageous\b|\bideally\b|\boptional\b", re.I)
_REQUIRED_CUE = re.compile(r"\bmust\b|\brequired\b|\bmandatory\b|\bessential\b|\bminimum\b|\bat least\b", re.I)

_RESPONSIBILITY_START = re.compile(
    r"^(?:you(?:'|’)?ll|you will|responsible for|own|design|develop|build|lead|manage|collaborate|implement"
    r"|deploy|maintain|work|drive|create|write|analy[sz]e|partner|mentor|optimi[sz]e|architect|define|ensure"
    r"|support|conduct|translate|contribute|participate|research|evaluate|monitor|deliver|establish|improve)\b",
    re.I,
)

_REMOTE_RE = re.compile(r"\b(?:fully remote|remote[- ]first|100% remote|work from home|wfh|remote)\b", re.I)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
_ONSITE_RE = re.compile(r"\b(?:on-?site|in[- ]office|work from office|wfo)\b", re.I)

_TITLE_WORDS = re.compile(
    r"\b(?:engineer|developer|scientist|analyst|manager|lead|architect|designer|consultant|intern|specialist"
    r"|researcher|administrator|director|head|officer|associate|programmer)\b", re.I)

_INJECTION_RES = [
    re.compile(p, re.I) for p in (
        r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)",
        r"disregard (?:all |any )?(?:the )?(?:previous|prior|above|earlier)",
        r"\bsystem prompt\b",
        r"\byou are (?:now )?(?:an? )?(?:ai|assistant|language model|chatbot|chatgpt|claude|gpt)\b",
        r"\bas an ai\b",
        r"\b(?:reveal|print|output|show|send)\b.{0,40}\b(?:api key|password|secret|system prompt|credentials)\b",
        r"<\|im_start\|>|\[/?INST\]",
        r"\b(?:rate|score|rank) (?:this|the) (?:candidate|resume|applicant) (?:as|at) ",
    )
]

_IMPORTANCE_RANK = {Importance.REQUIRED: 2, Importance.PREFERRED: 1, Importance.UNSPECIFIED: 0}
_CATEGORY_ORDER = [
    RequirementCategory.EXPERIENCE, RequirementCategory.SKILL, RequirementCategory.EDUCATION,
    RequirementCategory.CERTIFICATION, RequirementCategory.QUALIFICATION, RequirementCategory.RESPONSIBILITY,
    RequirementCategory.DOMAIN,
]


@dataclass
class ParseResult:
    analysis: JDAnalysis
    suggested_title: str = ""
    suggested_company: str = ""
    suggested_location: str = ""


@dataclass
class _Item:
    text: str
    section: Section
    is_bullet: bool = False


@dataclass
class _State:
    reqs: list[Requirement] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    experience_meta: Optional[tuple[Optional[float], Optional[float]]] = None


# ---- text structure ---------------------------------------------------------------


def _clean_line(line: str) -> str:
    line = re.sub(r"^#{1,6}\s*", "", line.strip())        # markdown headings
    line = re.sub(r"^\*\*(.+?)\*\*:?\s*$", r"\1", line)   # **Heading**
    return line.strip()


def _classify_heading(text: str) -> Optional[Section]:
    """Section for a heading-like line, or None if the line is not a heading."""
    t = text.strip().rstrip(":").strip().strip("*").strip()
    if not t or len(t) > 60 or t.endswith((".", ",")) or ":" in t:  # "Heading: content" is handled inline
        return None
    for section, rx in _HEADING_RES:
        if rx.match(t):
            # Long lines only count as headings if they end with ':' (a real heading, not a sentence).
            if len(t.split()) > 6 and not text.rstrip().endswith(":"):
                return None
            return section
    return None


def _split_items(lines: list[str], section: Section) -> list[_Item]:
    items: list[_Item] = []
    for line in lines:
        bullet = bool(_BULLET_RE.match(line)) and not re.match(r"^\s*\d+(?:\.\d+)?\s*(?:\+|-|to)", line)
        text = _BULLET_RE.sub("", line, count=1).strip() if bullet else line.strip()
        if not text:
            continue
        # One item per sentence, so cues like "is a plus" apply only to their own sentence.
        items.extend(_Item(s.strip(), section, bullet) for s in _SENTENCE_SPLIT.split(text) if s.strip())
    return items


def segment(text: str) -> tuple[list[_Item], dict[str, str]]:
    """Split JD text into section-tagged items and collect ``Key: value`` metadata."""
    items: list[_Item] = []
    meta: dict[str, str] = {}
    section = Section.INTRO
    buffer: list[str] = []

    def flush() -> None:
        items.extend(_split_items(buffer, section))
        buffer.clear()

    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        m = _META_RE.match(_BULLET_RE.sub("", line, count=1))
        key = m.group("key").strip().casefold() if m else ""
        if m and key in _META_KEYS:
            meta.setdefault(_META_KEYS[key], m.group("value").strip())
            heading = _classify_heading(m.group("key"))
            if _META_KEYS[key] == "education":
                flush()
                items.append(_Item(m.group("value").strip(), Section.EDUCATION))
            elif heading and _META_KEYS[key] not in ("title", "company", "location", "arrangement", "experience",
                                                     "skip"):
                flush()
                section = heading
                buffer.append(m.group("value"))
            continue
        heading = _classify_heading(line)
        if heading is not None:
            flush()
            section = heading
            continue
        # Inline heading: "Requirements: 3+ years of Python ..."
        if ":" in line[:45]:
            head, _, rest = line.partition(":")
            inline = _classify_heading(head + ":")
            if inline is not None and rest.strip():
                flush()
                section = inline
                buffer.append(rest.strip())
                continue
        buffer.append(line)
    flush()
    return items, meta


# ---- extraction -------------------------------------------------------------------


def _importance(item: _Item) -> Importance:
    if _PREFERRED_CUE.search(item.text):
        return Importance.PREFERRED
    if item.section is Section.PREFERRED:
        return Importance.PREFERRED
    if item.section is Section.REQUIRED or _REQUIRED_CUE.search(item.text):
        return Importance.REQUIRED
    return Importance.UNSPECIFIED


def parse_years(text: str) -> Optional[tuple[Optional[float], Optional[float]]]:
    """``(min, max)`` years from the first experience expression in ``text``, or None."""
    for rx, kind in _EXPERIENCE_RES:
        m = rx.search(text)
        if not m:
            continue
        if kind == "range":
            lo, hi = float(m.group(1)), float(m.group(2))
            if hi < lo or hi > 40:
                return None  # malformed range: leave it to the user rather than guess
            return lo, hi
        value = float(m.group(1))
        if value > 40:
            continue
        return (value, None) if kind == "min" else (None, value)
    return None


def _excerpt(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _edu_level(text: str) -> str:
    for rx, level in _EDU_LEVELS:
        if rx.search(text):
            return level
    return ""


def _extract_item(item: _Item, extra: list[SkillTerm], state: _State) -> None:
    text = item.text
    importance = _importance(item)
    in_requirements = item.section in (Section.REQUIRED, Section.PREFERRED)
    base_conf = 0.9 if in_requirements else 0.75 if item.section is Section.RESPONSIBILITIES else 0.6
    produced_specific = False

    hits = find_terms(text, extra)
    skill_names = list(dict.fromkeys(h.term.name for h in hits))

    years = parse_years(text)
    if years and (_EXPERIENCE_CONTEXT.search(text) or (len(text) <= 40 and item.section is Section.INTRO)):
        lo, hi = years
        term = skill_names[0] if len(skill_names) == 1 else "overall"
        state.reqs.append(Requirement(
            text=_excerpt(text, 500), normalized_term=term, category=RequirementCategory.EXPERIENCE,
            importance=importance if importance is not Importance.UNSPECIFIED else Importance.REQUIRED,
            source_excerpt=_excerpt(text), confidence=min(base_conf + 0.05, 0.9), min_years=lo, max_years=hi))
        produced_specific = True

    if item.section is Section.EDUCATION or _EDU_RE.search(text):
        if _EDU_RE.search(text) or item.section is Section.EDUCATION:
            state.reqs.append(Requirement(
                text=_excerpt(text, 500), normalized_term=_edu_level(text), category=RequirementCategory.EDUCATION,
                importance=importance, source_excerpt=_excerpt(text),
                confidence=0.85 if item.section is Section.EDUCATION else base_conf - 0.1))
            produced_specific = True

    if _CERT_RE.search(text):
        state.reqs.append(Requirement(
            text=_excerpt(text, 500), category=RequirementCategory.CERTIFICATION, importance=importance,
            source_excerpt=_excerpt(text), confidence=base_conf - 0.1))
        produced_specific = True

    for name in skill_names:
        state.reqs.append(Requirement(
            text=name, normalized_term=name, category=RequirementCategory.SKILL, importance=importance,
            source_excerpt=_excerpt(text), confidence=base_conf))

    if item.section is Section.RESPONSIBILITIES:
        state.reqs.append(Requirement(
            text=_excerpt(text, 500), category=RequirementCategory.RESPONSIBILITY,
            source_excerpt=_excerpt(text), confidence=0.85))
    elif in_requirements and not produced_specific and not skill_names:
        state.reqs.append(Requirement(
            text=_excerpt(text, 500), category=RequirementCategory.QUALIFICATION, importance=importance,
            source_excerpt=_excerpt(text), confidence=0.7))
    elif item.section in (Section.INTRO, Section.OTHER) and item.is_bullet and _RESPONSIBILITY_START.match(text):
        state.reqs.append(Requirement(
            text=_excerpt(text, 500), category=RequirementCategory.RESPONSIBILITY,
            source_excerpt=_excerpt(text), confidence=0.5))


def _key_skill_tokens(item: _Item, extra: list[SkillTerm], state: _State) -> None:
    """Naukri-style tag lists: every comma/pipe-separated token is a skill, known or not."""
    tokens = [t.strip(" *•.") for t in re.split(r"[,|;•\n]", item.text)]
    for token in tokens:
        if not token or len(token) > 40:
            continue
        term = lookup(token, extra)
        hits = [] if term else find_terms(token, extra)
        if term or len(hits) == 1 and hits[0].end - hits[0].start == len(token):
            name = (term or hits[0].term).name
            conf = 0.85
        else:
            name, conf = token, 0.6
        state.reqs.append(Requirement(
            text=name, normalized_term=name, category=RequirementCategory.SKILL,
            importance=Importance.UNSPECIFIED, source_excerpt=_excerpt(item.text), confidence=conf))


def _merge(reqs: list[Requirement]) -> list[Requirement]:
    """One SKILL/DOMAIN requirement per term (strongest importance wins); drop repeated text elsewhere."""
    merged: dict[tuple, Requirement] = {}
    for r in reqs:
        if r.category in (RequirementCategory.SKILL, RequirementCategory.DOMAIN):
            key = (r.category, r.normalized_term.casefold())
        else:
            key = (r.category, r.text.casefold(), r.normalized_term.casefold())
        current = merged.get(key)
        if current is None:
            merged[key] = r
            continue
        better = (_IMPORTANCE_RANK[r.importance], r.confidence) > (_IMPORTANCE_RANK[current.importance], current.confidence)
        if better:
            merged[key] = r.model_copy(update={"id": current.id, "confidence": max(r.confidence, current.confidence)})
    order = {r.id: i for i, r in enumerate(merged.values())}
    return sorted(
        merged.values(),
        key=lambda r: (_CATEGORY_ORDER.index(r.category), -_IMPORTANCE_RANK[r.importance], order[r.id]),
    )


def _arrangement(text: str, meta: dict[str, str]) -> WorkArrangement:
    value = meta.get("arrangement", "")
    for source in ([value] if value else []) + [text]:
        found = {
            WorkArrangement.HYBRID: bool(_HYBRID_RE.search(source)),
            WorkArrangement.REMOTE: bool(_REMOTE_RE.search(source)),
            WorkArrangement.ONSITE: bool(_ONSITE_RE.search(source)),
        }
        kinds = [k for k, v in found.items() if v]
        if len(kinds) == 1:
            return kinds[0]
        if found[WorkArrangement.HYBRID]:
            return WorkArrangement.HYBRID
    return WorkArrangement.UNSPECIFIED


def _overall_experience(state: _State, warnings: list[str]) -> tuple[Optional[float], Optional[float]]:
    """Job-level range: metadata first, else a single unambiguous 'overall' statement. Never guessed."""
    if state.experience_meta:
        return state.experience_meta
    ranges = {(r.min_years, r.max_years) for r in state.reqs
              if r.category is RequirementCategory.EXPERIENCE and r.normalized_term == "overall"}
    if len(ranges) == 1:
        return ranges.pop()
    if len(ranges) > 1:
        warnings.append("Several different experience ranges were found. Set the overall range yourself.")
    return None, None


def _suggested_title(text: str, meta: dict[str, str]) -> str:
    if meta.get("title"):
        return meta["title"][:120]
    for line in text.splitlines():
        line = _clean_line(line)
        if not line:
            continue
        if len(line) <= 80 and not line.endswith(".") and _TITLE_WORDS.search(line) and _classify_heading(line) is None:
            return line
        break
    return ""


def injection_warnings(text: str) -> list[str]:
    found = []
    for rx in _INJECTION_RES:
        m = rx.search(text)
        if m:
            found.append(m.group(0).strip())
    if not found:
        return []
    quoted = "; ".join(f"“{_excerpt(f, 60)}”" for f in found[:3])
    return [f"The JD contains text that looks like instructions to an AI system ({quoted}). "
            "It is treated as plain job text and will never be followed."]


def parse_jd(job: Job, extra_terms: Iterable[SkillTerm] = ()) -> ParseResult:
    """Analyze ``job.description`` into a draft ``JDAnalysis`` for user review."""
    extra = list(extra_terms)
    text = job.description
    items, meta = segment(text)
    state = _State(meta=meta)
    warnings: list[str] = []

    if meta.get("experience"):
        state.experience_meta = parse_years(meta["experience"])
        if state.experience_meta:
            lo, hi = state.experience_meta
            state.reqs.append(Requirement(
                text=f"Experience: {meta['experience']}", normalized_term="overall",
                category=RequirementCategory.EXPERIENCE, importance=Importance.REQUIRED,
                source_excerpt=_excerpt(meta["experience"]), confidence=0.9, min_years=lo, max_years=hi))

    for item in items:
        if item.section in (Section.IGNORE, Section.ABOUT_COMPANY):
            continue
        if item.section is Section.KEY_SKILLS:
            _key_skill_tokens(item, extra, state)
        else:
            _extract_item(item, extra, state)

    relevant = "\n".join(i.text for i in items if i.section is not Section.IGNORE)
    for hit in find_terms(relevant, terms=DOMAIN_TERMS):
        state.reqs.append(Requirement(
            text=hit.term.name, normalized_term=hit.term.name, category=RequirementCategory.DOMAIN,
            source_excerpt=_excerpt(_line_at(relevant, hit.start)), confidence=0.6))

    sections = {i.section for i in items}
    if not sections & {Section.REQUIRED, Section.PREFERRED, Section.KEY_SKILLS}:
        warnings.append("No clear requirements section was found. Requirements were inferred from the whole "
                        "text. Review importance (required vs preferred) carefully.")
    warnings.extend(injection_warnings(text))

    requirements = _merge(state.reqs)
    lo, hi = _overall_experience(state, warnings)
    analysis = JDAnalysis(
        job_id=job.id, parser=PARSER_NAME, jd_hash=description_hash(text),
        work_arrangement=_arrangement(relevant, meta), experience_min_years=lo, experience_max_years=hi,
        requirements=requirements, warnings=warnings,
    )
    return ParseResult(
        analysis=analysis,
        suggested_title=_suggested_title(text, meta),
        suggested_company=meta.get("company", "")[:120],
        suggested_location=meta.get("location", "")[:120],
    )


def _line_at(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start: end if end != -1 else len(text)].strip()
