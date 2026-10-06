"""Optional LLM rewriting of a deterministic draft, with every change checked against the profile.

What is sent: target job title, JD requirement terms (from the user-confirmed
analysis), the draft's bullets with their allowed skill terms and verified
metrics, role titles/dates, evidenced skill names, and documented years.
What is never sent: name, email, phone, links, location, employer names, or raw JD text.

Rewrites that add numbers or skills are discarded and the original wording kept.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from string import Template
from typing import Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from src.schemas.analysis import Importance, JDAnalysis
from src.schemas.match import MatchReport
from src.schemas.profile import MasterProfile
from src.schemas.resume import ResumeContent, ResumeSummary, TextOrigin
from src.services.claim_checker import check_rewrite, check_summary
from src.services.llm.provider import LLMError, LLMProvider
from src.services.matching_service import build_index, documented_experience_years

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
MAX_ATTEMPTS = 2  # one retry, only for malformed/schema-invalid output
MAX_TOKENS = 16000

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"],
            "additionalProperties": False,
        },
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "bullets"],
    "additionalProperties": False,
}


class _OutSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    evidence_ids: list[str]


class _OutBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str


class RewriteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: _OutSummary
    bullets: list[_OutBullet]


@dataclass
class RewriteRequest:
    system: str
    user: str
    bullet_ids: list[str]
    evidence_ids: list[str]


@dataclass
class RewriteResult:
    content: ResumeContent
    notes: list[str] = field(default_factory=list)
    rewritten: int = 0
    rejected: int = 0


def _load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_request(content: ResumeContent, profile: MasterProfile, analysis: JDAnalysis, report: MatchReport,
                  target_role: str, today: Optional[date] = None) -> RewriteRequest:
    """Assemble the exact prompts that would be sent (shown to the user before consent)."""
    idx = build_index(profile)
    by_id = idx.by_id
    evidence = profile.evidence_index()
    by_req = report.by_requirement()
    reqs = [r for r in analysis.requirements if r.importance is not Importance.UNSPECIFIED
            or r.category.value in ("responsibility", "qualification")]
    req_lines = []
    for r in reqs:
        m = by_req.get(r.id)
        status = m.effective_status.value if m else "unknown"
        label = r.normalized_term if r.normalized_term and r.normalized_term != "overall" else r.text[:160]
        req_lines.append(f"- [{r.importance.value}; your evidence: {status}] {label}")

    bullets, bullet_ids, evidence_ids = [], [], []
    for entry in [*content.experience, *content.projects]:
        for b in entry.bullets:
            bid = b.evidence_ids[0]
            source = [evidence[e][1] for e in b.evidence_ids if e in evidence]
            terms = sorted({t for e in b.evidence_ids if e in by_id for t in by_id[e].terms})
            metrics = [f"{m.label}: {m.value}" for s in source for m in getattr(s, "verified_metrics", [])]
            bullets.append({"id": bid, "text": b.text, "allowed_terms": [_display_term(t, idx) for t in terms],
                            "verified_metrics": metrics})
            bullet_ids.append(bid)
            evidence_ids.append(bid)
    roles = [f"- {e.title} ({e.start_date or '?'} to {e.end_date or 'present'})" for e in content.experience]
    years = math.floor(documented_experience_years(profile, today))
    user = Template(_load("resume_rewrite_user.md")).substitute(
        target_role=target_role or "(not specified)",
        requirements="\n".join(req_lines) or "(none)",
        years=years,
        skills=", ".join(s.name for s in content.skills) or "(none)",
        roles="\n".join(roles) or "(none)",
        evidence="\n".join(f"- {b['id']}: {b['text']}" for b in bullets) or "(none)",
        bullets=json.dumps(bullets, ensure_ascii=False, indent=1),
    )
    return RewriteRequest(system=_load("resume_rewrite_system.md"), user=user, bullet_ids=bullet_ids,
                          evidence_ids=evidence_ids)


def _display_term(term_cf: str, idx) -> str:
    """Terms are stored casefolded in the index; show the canonical spelling where known."""
    from src.services.skill_taxonomy import lookup

    t = lookup(term_cf, idx.extra)
    return t.name if t else term_cf


def _call(provider: LLMProvider, request: RewriteRequest) -> RewriteOutput:
    user = request.user
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = provider.generate_json(system=request.system, user=user, schema=OUTPUT_SCHEMA, max_tokens=MAX_TOKENS)
        try:
            return RewriteOutput.model_validate_json(raw)
        except ValidationError as exc:
            last_error = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
            logger.warning("event=llm_output_invalid attempt=%d errors=%d", attempt, len(exc.errors()))
            user = (request.user + "\n\nYour previous answer did not match the required JSON schema "
                    f"({last_error}). Return only the JSON object.")
    raise LLMError(f"The model's answer did not match the expected format after {MAX_ATTEMPTS} attempts.")


def rewrite(content: ResumeContent, profile: MasterProfile, analysis: JDAnalysis, report: MatchReport,
            provider: LLMProvider, *, target_role: str = "", today: Optional[date] = None) -> RewriteResult:
    """Ask the provider for rewrites, then keep only those that pass the claim checks."""
    request = build_request(content, profile, analysis, report, target_role, today)
    output = _call(provider, request)
    idx = build_index(profile)
    by_id = idx.by_id
    evidence = profile.evidence_index()
    result = RewriteResult(content=content.model_copy(deep=True))
    proposals = {b.id: b.text.strip() for b in output.bullets}
    unknown = set(proposals) - set(request.bullet_ids)
    if unknown:
        result.notes.append(f"Ignored {len(unknown)} rewrite(s) for bullets that were not sent.")

    for entry in [*result.content.experience, *result.content.projects]:
        for i, b in enumerate(entry.bullets):
            new = proposals.get(b.evidence_ids[0])
            if not new or new == b.text:
                continue
            source = [evidence[e][1] for e in b.evidence_ids if e in evidence]
            check = check_rewrite(
                new, b.source_text,
                verified_values=[m.value for s in source for m in getattr(s, "verified_metrics", [])],
                tagged_terms=[t for e in b.evidence_ids if e in by_id for t in by_id[e].linked],
                extra=idx.extra,
            )
            if check.ok:
                entry.bullets[i] = b.model_copy(update={"text": new, "origin": TextOrigin.REWRITTEN,
                                                        "notes": check.warnings})
                result.rewritten += 1
            else:
                entry.bullets[i] = b.model_copy(update={"notes": ["Rewrite discarded: " + " ".join(check.errors)]})
                result.rejected += 1

    s = output.summary
    cited = [e for e in dict.fromkeys(s.evidence_ids) if e in request.evidence_ids]
    if s.text.strip():
        metrics = [m.value for e in cited for m in getattr(evidence[e][1], "verified_metrics", [])]
        check = check_summary(
            s.text, cited_texts=[by_id[e].text for e in cited if e in by_id], cited_metric_values=metrics,
            evidenced_terms={t for d in idx.docs for t in d.terms} | {sk.name for sk in content.skills},
            total_experience_years=documented_experience_years(profile, today), extra=idx.extra,
        )
        if not cited:
            check.errors.append("It cites no evidence that was provided.")
        if check.ok:
            result.content.summary = ResumeSummary(text=s.text.strip(), evidence_ids=cited,
                                                   origin=TextOrigin.REWRITTEN, notes=check.warnings)
        else:
            result.content.summary = content.summary.model_copy(update={
                "notes": [*content.summary.notes, "AI summary discarded: " + " ".join(check.errors)]})
            result.notes.append("The AI summary was discarded because it failed the claim checks.")
    if result.rejected:
        result.notes.append(f"{result.rejected} bullet rewrite(s) were discarded because they added facts; "
                            "the original wording was kept.")
    logger.info("event=rewrite_applied provider=%s rewritten=%d rejected=%d", provider.name,
                result.rewritten, result.rejected)
    return result
