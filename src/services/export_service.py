"""Export approved resume versions to DOCX and PDF under ``output_dir/<job_id>/<version_id>/``."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from src.schemas.export import CheckStatus, ExportCheck, ExportRecord
from src.schemas.resume import ResumeVersion
from src.services.export_validation import normalize, validate_docx, validate_pdf
from src.services.render.blocks import build_blocks
from src.services.render.docx_renderer import render_docx
from src.services.render.pdf_renderer import render_pdf
from src.services.render.style import CLASSIC, PAGE_SIZES_IN, Style, pdf_font

logger = logging.getLogger(__name__)
RENDERER_VERSION = "v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9-]{1,40}$")


class ExportError(RuntimeError):
    """Export could not run. Message is user-facing."""


def safe_filename(*parts: str, max_len: int = 80) -> str:
    """'Asha Example', 'Fictional Corp' -> 'Asha_Example_Fictional_Corp' (ASCII letters, digits, _ and - only)."""
    words = []
    for part in parts:
        ascii_part = part.encode("ascii", "ignore").decode()
        words += re.findall(r"[A-Za-z0-9]+", ascii_part)
    name = "_".join(words)[:max_len].strip("_")
    return name or "resume"


def _job_dir(output_dir: Path, job_id: str) -> Path:
    if not _SAFE_ID.match(job_id):
        raise ExportError("Unexpected job ID format.")
    root = Path(output_dir).resolve()
    folder = (root / job_id).resolve()
    if root not in folder.parents:
        raise ExportError("Refusing to write outside the output folder.")
    return folder


def export_version(version: ResumeVersion, *, output_dir: Path, page_size: str = "A4", style: Style = CLASSIC,
                   company: str = "", role: str = "") -> ExportRecord:
    """Render and validate both files. Only approved versions can be exported."""
    if version.approved_at is None:
        raise ExportError("Approve this version before exporting it.")
    if page_size not in PAGE_SIZES_IN:
        raise ExportError(f"Unknown page size {page_size!r}. Use A4 or Letter.")
    if not _SAFE_ID.match(version.id):
        raise ExportError("Unexpected version ID format.")
    folder = _job_dir(output_dir, version.job_id) / version.id
    base = safe_filename(version.content.contact.full_name, company, role, "Resume")
    docx_path, pdf_path = folder / f"{base}.docx", folder / f"{base}.pdf"
    title = " - ".join(x for x in (version.content.contact.full_name, role, "Resume") if x)

    blocks = build_blocks(version.content)
    font = pdf_font()
    try:
        render_docx(blocks, docx_path, style, page_size, title=title)
        render_pdf(blocks, pdf_path, style, page_size, title=title, font=font)
    except OSError as exc:
        logger.error("event=export_write_failed error_type=%s", type(exc).__name__)
        raise ExportError(f"Could not write the files ({exc.strerror or type(exc).__name__}). If a previous "
                          "export is open in Word or a PDF viewer, close it and try again.") from exc

    checks = validate_docx(docx_path, blocks)
    pdf_checks, pages = validate_pdf(pdf_path, blocks, int(version.target_pages), font)
    checks += pdf_checks
    same = _same_text(docx_path, pdf_path)
    checks.append(same)
    record = ExportRecord(version_id=version.id, job_id=version.job_id, renderer=f"{style.name}-{RENDERER_VERSION}",
                          page_size=page_size,
                          pdf_font=font.source, docx_path=str(docx_path), pdf_path=str(pdf_path), pdf_pages=pages,
                          target_pages=int(version.target_pages), checks=checks)
    logger.info("event=resume_exported version_id=%s pages=%s failed=%d warnings=%d", version.id, pages,
                len(record.failed), len(record.warnings))
    return record


def _same_text(docx_path: Path, pdf_path: Path) -> ExportCheck:
    """Both files should carry the same words (layout aside)."""
    import docx
    import pdfplumber

    try:
        d = normalize(" ".join(p.text for p in docx.Document(str(docx_path)).paragraphs))
        with pdfplumber.open(pdf_path) as pdf:
            p = normalize(" ".join((pg.extract_text() or "") for pg in pdf.pages))
    except Exception:  # already reported by the per-file "Opens" checks
        return ExportCheck(file="both", name="DOCX and PDF match", status=CheckStatus.WARN, detail="Not compared.")
    same = d.split() == p.split()
    return ExportCheck(file="both", name="DOCX and PDF match", status=CheckStatus.PASS if same else CheckStatus.WARN,
                       detail="Both files contain the same text." if same
                       else "The two files' text differs slightly; review both before sending.")


def delete_job_outputs(output_dir: Path, job_id: str) -> bool:
    """Remove exported files for a job (called when the job is deleted)."""
    try:
        folder = _job_dir(output_dir, job_id)
    except ExportError:
        return False
    if folder.is_dir():
        shutil.rmtree(folder)
        logger.info("event=job_outputs_deleted job_id=%s", job_id)
        return True
    return False
