"""The default ATS-friendly template ('classic') and PDF font discovery.

Sizes are fixed at readable values; the renderers never shrink text to fit a page.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIN_FONT_PT = 9.0  # validation fails anything smaller


@dataclass(frozen=True)
class Style:
    name: str = "classic"
    font_family: str = "Arial"     # DOCX font; PDF uses the discovered TTF (or Helvetica)
    name_pt: float = 18
    headline_pt: float = 11.5
    contact_pt: float = 10
    heading_pt: float = 12
    body_pt: float = 10.5
    margin_in: float = 0.7
    line_spacing: float = 1.15


CLASSIC = Style()
# Tighter spacing and margins for longer histories; still >= 9.5 pt everywhere (never shrunk below readable).
COMPACT = Style(name="compact", name_pt=16, headline_pt=11, contact_pt=9.5, heading_pt=11, body_pt=10,
                margin_in=0.6, line_spacing=1.05)
TEMPLATES = {"classic": CLASSIC, "compact": COMPACT}
PAGE_SIZES_IN = {"A4": (8.27, 11.69), "Letter": (8.5, 11.0)}


@dataclass(frozen=True)
class PdfFont:
    regular: str            # reportlab font name
    bold: str
    embedded: bool          # True when a TrueType font is embedded (full Unicode coverage of that font)
    source: str = ""


_CANDIDATES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def _font_candidates() -> list[tuple[str, str]]:
    env_regular = os.getenv("RESUME_OPTIMIZER_PDF_FONT", "").strip()
    env_bold = os.getenv("RESUME_OPTIMIZER_PDF_FONT_BOLD", "").strip()
    out = [(env_regular, env_bold or env_regular)] if env_regular else []
    windir = os.getenv("WINDIR")
    if windir:
        out.append((f"{windir}/Fonts/arial.ttf", f"{windir}/Fonts/arialbd.ttf"))
    return out + _CANDIDATES


@lru_cache(maxsize=1)
def pdf_font() -> PdfFont:
    """Register the first available TrueType regular/bold pair; fall back to built-in Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont, TTFError

    for regular, bold in _font_candidates():
        if not (Path(regular).is_file() and Path(bold).is_file()):
            continue
        try:
            pdfmetrics.registerFont(TTFont("ResumeSans", regular))
            pdfmetrics.registerFont(TTFont("ResumeSans-Bold", bold))
        except (TTFError, OSError) as exc:
            logger.warning("event=pdf_font_register_failed error_type=%s", type(exc).__name__)
            continue
        return PdfFont("ResumeSans", "ResumeSans-Bold", True, Path(regular).name)
    return PdfFont("Helvetica", "Helvetica-Bold", False, "built-in Helvetica")


def unrenderable_chars(text: str, font: Optional[PdfFont] = None) -> set[str]:
    """Characters the built-in Helvetica (WinAnsi) cannot draw. Embedded fonts are assumed to cover them."""
    font = font or pdf_font()
    if font.embedded:
        return set()
    bad = set()
    for ch in set(text):
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            bad.add(ch)
    return bad
