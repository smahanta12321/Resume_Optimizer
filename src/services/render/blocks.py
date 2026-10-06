"""Resume content -> an ordered list of neutral blocks shared by the DOCX and PDF renderers.

Both renderers consume the same blocks, so the two files always carry the same
text, and export validation checks each file against this list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from src.schemas.resume import ResumeContent

BlockKind = Literal["name", "headline", "contact", "heading", "text", "entry", "bullet"]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SECTION_HEADINGS = {
    "summary": "Summary", "skills": "Skills", "experience": "Experience", "projects": "Projects",
    "education": "Education", "certifications": "Certifications",
}


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str


def format_month(ym: Optional[str]) -> str:
    """'2022-07' -> 'Jul 2022'. Unparseable values are returned unchanged."""
    if not ym:
        return ""
    try:
        year, month = ym.split("-")
        return f"{_MONTHS[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return ym


def date_range(start: Optional[str], end: Optional[str], *, open_ended: bool = True) -> str:
    """'Jul 2022 – Present'. A missing end means current only for roles/projects (``open_ended``)."""
    s, e = format_month(start), format_month(end)
    if not s and not e:
        return ""
    if not e:
        return f"{s} – Present" if open_ended else s
    return f"{s} – {e}" if s else e


def _join(*parts: str, sep: str = " | ") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())


def build_blocks(c: ResumeContent) -> list[Block]:
    blocks = [Block("name", c.contact.full_name)]
    if c.headline:
        blocks.append(Block("headline", c.headline))
    contact = _join(c.contact.email, c.contact.phone, c.contact.location, *[link.url for link in c.contact.links])
    if contact:
        blocks.append(Block("contact", contact))
    if c.summary.text:
        blocks += [Block("heading", SECTION_HEADINGS["summary"]), Block("text", c.summary.text)]
    if c.skills:
        blocks += [Block("heading", SECTION_HEADINGS["skills"]), Block("text", ", ".join(s.name for s in c.skills))]
    for key, entries in (("experience", c.experience), ("projects", c.projects)):
        if not entries:
            continue
        blocks.append(Block("heading", SECTION_HEADINGS[key]))
        for e in entries:
            blocks.append(Block("entry", _join(e.title, e.organization, e.location,
                                               date_range(e.start_date, e.end_date,
                                                          open_ended=e.kind == "experience" or bool(e.start_date)))))
            blocks += [Block("bullet", b.text) for b in e.bullets]
    if c.education:
        blocks.append(Block("heading", SECTION_HEADINGS["education"]))
        for e in c.education:
            degree = f"{e.degree}, {e.field_of_study}" if e.field_of_study else e.degree
            blocks.append(Block("entry", _join(degree, e.institution,
                                               date_range(e.start_date, e.end_date, open_ended=False))))
    if c.certifications:
        blocks.append(Block("heading", SECTION_HEADINGS["certifications"]))
        blocks += [Block("bullet", _join(x.name, x.issuer, format_month(x.issue_date), sep=", "))
                   for x in c.certifications]
    return blocks
