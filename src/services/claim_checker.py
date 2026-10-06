"""Deterministic claim checks for resume text derived from master-profile evidence.

Errors block a rewrite or edit: new numbers, new skills/tools, and summary claims
that the cited evidence cannot back. Warnings mark wording a human should check:
new proper names and stronger verbs or adjectives than the source used.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from src.services.skill_taxonomy import SkillTerm, find_terms

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_YEARS_CLAIM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.I)
_PROPER_RE = re.compile(r"(?<![\w.])([A-Z][A-Za-z0-9+#&.-]*[A-Za-z0-9+#])")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;•]\s+|\n\s*)$")
_STRONG_WORDS = (
    "led", "lead", "leading", "managed", "owned", "architected", "spearheaded", "headed", "directed", "founded",
    "expert", "world-class", "cutting-edge", "significantly", "dramatically", "substantially", "greatly",
    "massively", "revolutionized", "pioneered", "best-in-class", "industry-leading",
)
_FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine)\b")
MAX_BULLET_CHARS = 350


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


def _terms(text: str, extra: list[SkillTerm]) -> set[str]:
    return {h.term.name for h in find_terms(text, extra)}


def _proper_names(text: str) -> set[str]:
    names = set()
    for m in _PROPER_RE.finditer(text):
        if _SENTENCE_START.search(text[: m.start()]):
            continue  # capitalized only because it starts a sentence
        names.add(m.group(1))
    return names


def _strong_words(text: str) -> set[str]:
    low = text.casefold()
    return {w for w in _STRONG_WORDS if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", low)}


def check_rewrite(
    new_text: str,
    source_text: str,
    *,
    verified_values: Iterable[str] = (),
    tagged_terms: Iterable[str] = (),
    extra: Iterable[SkillTerm] = (),
) -> CheckResult:
    """Compare a rewritten/edited bullet against the profile text it must stay faithful to."""
    extra = list(extra)
    result = CheckResult()
    text = new_text.strip()
    if not text:
        result.errors.append("The text is empty.")
        return result
    if len(text) > max(MAX_BULLET_CHARS, 2 * len(source_text)):
        result.errors.append(f"The text is much longer than the source ({len(text)} characters).")

    backed_numbers = _numbers(source_text) | {n for v in verified_values for n in _numbers(v)}
    new_numbers = sorted(_numbers(text) - backed_numbers)
    if new_numbers:
        result.errors.append(f"Adds number(s) not in the source or its verified metrics: {', '.join(new_numbers)}.")

    allowed_terms = _terms(source_text, extra) | set(tagged_terms)
    allowed_cf = {t.casefold() for t in allowed_terms}
    new_terms = sorted(t for t in _terms(text, extra) if t.casefold() not in allowed_cf)
    if new_terms:
        result.errors.append(f"Mentions skills/tools the source does not: {', '.join(new_terms)}.")

    source_cf = source_text.casefold()
    names = sorted(n for n in _proper_names(text)
                   if n.casefold() not in source_cf and n.casefold() not in allowed_cf)
    if names:
        result.warnings.append(f"New name(s) not in the source: {', '.join(names)}. Check they are accurate.")
    stronger = sorted(_strong_words(text) - _strong_words(source_text))
    if stronger:
        result.warnings.append(f"Stronger wording than the source ({', '.join(stronger)}). Make sure it is accurate.")
    if _FIRST_PERSON.search(text):
        result.warnings.append("Uses first person (I/my). Resumes usually omit it.")
    return result


def check_summary(
    text: str,
    *,
    cited_texts: Iterable[str],
    cited_metric_values: Iterable[str] = (),
    evidenced_terms: Iterable[str] = (),
    total_experience_years: float | None = None,
    extra: Iterable[SkillTerm] = (),
) -> CheckResult:
    """Check a generated/edited summary against the evidence it cites and the computed experience."""
    extra = list(extra)
    result = CheckResult()
    if not text.strip():
        return result
    cited = " ".join(cited_texts)

    years_claims = [float(m.group(1)) for m in _YEARS_CLAIM_RE.finditer(text)]
    for years in years_claims:
        limit = math.floor(total_experience_years or 0)
        if years > limit:
            result.errors.append(
                f"Claims {years:g} years of experience; your dated roles support at most {limit}.")
    body = _YEARS_CLAIM_RE.sub(" ", text)
    backed = _numbers(cited) | {n for v in cited_metric_values for n in _numbers(v)}
    new_numbers = sorted(_numbers(body) - backed)
    if new_numbers:
        result.errors.append(f"Adds number(s) the cited evidence does not contain: {', '.join(new_numbers)}.")

    allowed_cf = {t.casefold() for t in evidenced_terms}
    new_terms = sorted(t for t in _terms(text, extra) if t.casefold() not in allowed_cf)
    if new_terms:
        result.errors.append(f"Mentions skills/tools your evidence does not show: {', '.join(new_terms)}.")

    stronger = sorted(_strong_words(text) - _strong_words(cited))
    if stronger:
        result.warnings.append(f"Strong wording ({', '.join(stronger)}). Make sure your evidence backs it.")
    if _FIRST_PERSON.search(text):
        result.warnings.append("Uses first person (I/my). Resume summaries usually omit it.")
    return result
