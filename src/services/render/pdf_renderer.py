"""PDF renderer (reportlab): single column, selectable text, embedded TrueType font where available."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import black
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from src.services.render.blocks import Block
from src.services.render.style import PAGE_SIZES_IN, PdfFont, Style, pdf_font


def _styles(style: Style, font: PdfFont) -> dict[str, ParagraphStyle]:
    lead = style.line_spacing * 1.2

    def ps(name, size, *, bold=False, before=0.0, after=2.0, **kw):
        return ParagraphStyle(name, fontName=font.bold if bold else font.regular, fontSize=size,
                              leading=size * lead, spaceBefore=before, spaceAfter=after, textColor=black, **kw)

    return {
        "name": ps("name", style.name_pt, bold=True, after=2),
        "headline": ps("headline", style.headline_pt, after=2),
        "contact": ps("contact", style.contact_pt, after=4),
        "heading": ps("heading", style.heading_pt, bold=True, before=8, after=1, keepWithNext=1),
        "text": ps("text", style.body_pt),
        "entry": ps("entry", style.body_pt, before=4, keepWithNext=1),
        "bullet": ps("bullet", style.body_pt, after=1, leftIndent=14, bulletIndent=3,
                     bulletFontName=font.regular, bulletFontSize=style.body_pt),
    }


def render_pdf(blocks: list[Block], path: Path, style: Style, page_size: str = "A4", *, title: str = "",
               font: PdfFont | None = None) -> Path:
    font = font or pdf_font()
    if font.embedded:
        registerFontFamily(font.regular, normal=font.regular, bold=font.bold, italic=font.regular,
                           boldItalic=font.bold)
    styles = _styles(style, font)
    width, height = PAGE_SIZES_IN[page_size]
    margin = style.margin_in * inch
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=(width * inch, height * inch), leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin, title=title,
        author=next((b.text for b in blocks if b.kind == "name"), ""), subject="", creator="AI Resume Optimizer",
        invariant=1,
    )
    story = []
    for block in blocks:
        text = escape(block.text)
        if block.kind == "heading":
            story.append(Paragraph(text, styles["heading"]))
            story.append(HRFlowable(width="100%", thickness=0.6, color=black, spaceBefore=1, spaceAfter=3))
        elif block.kind == "entry":
            first, sep, rest = text.partition(" | ")
            story.append(Paragraph(f'<font name="{font.bold}">{first}</font>{sep}{rest}', styles["entry"]))
        elif block.kind == "bullet":
            story.append(Paragraph(text, styles["bullet"], bulletText="•"))
        else:
            story.append(Paragraph(text, styles[block.kind]))
            if block.kind == "contact":
                story.append(Spacer(1, 2))
    doc.build(story)
    return path
