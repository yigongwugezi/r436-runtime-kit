"""PDF textbook processing — pymupdf4llm extraction and page management.

Uses pymupdf4llm to convert PDF pages to markdown, handling both
text-based and scanned/image-based PDFs (via built-in OCR).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def ensure_textbook_dir(textbook_id: str) -> Path:
    """Create and return the storage directory for a textbook."""
    storage_root = settings.project_root / "backend" / settings.textbook_storage_path.lstrip("./")
    textbook_dir = storage_root / textbook_id
    textbook_dir.mkdir(parents=True, exist_ok=True)
    return textbook_dir


def save_uploaded_pdf(textbook_id: str, file_bytes: bytes, filename: str) -> str:
    """Save uploaded PDF bytes to disk.

    Returns the absolute file path.
    """
    textbook_dir = ensure_textbook_dir(textbook_id)
    safe_filename = f"{textbook_id}.pdf"
    file_path = textbook_dir / safe_filename
    file_path.write_bytes(file_bytes)
    logger.info("Saved textbook PDF: %s (%d bytes)", file_path, len(file_bytes))
    return str(file_path)


def get_pdf_page_count(pdf_path: str) -> int:
    """Return the number of pages in a PDF file."""
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    count = doc.page_count
    doc.close()
    return count


def extract_pdf_content(pdf_path: str) -> list[dict[str, Any]]:
    """Extract markdown text per page using pymupdf4llm.

    Returns a list of dicts: [{page_number, content, page_label}, ...]

    pymupdf4llm.to_markdown() with page_chunks=True returns markdown
    with page-break markers. We parse those markers to produce
    per-page records.
    """
    import pymupdf4llm

    logger.info("Extracting PDF content via pymupdf4llm: %s", pdf_path)

    try:
        md_text = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
    except Exception:
        logger.exception("pymupdf4llm extraction failed for %s", pdf_path)
        raise

    # pymupdf4llm page_chunks output wraps pages in <!-- Page N --> markers
    # or returns a list of dicts depending on version. Handle both.
    if isinstance(md_text, list):
        pages = []
        for item in md_text:
            pages.append({
                "page_number": item.get("page", item.get("page_number", 0)),
                "content": item.get("text", item.get("content", "")),
                "page_label": str(item.get("page", "")),
            })
        return pages

    # String output with page markers
    pages = []
    import re

    # Split by <!-- Page N --> markers
    parts = re.split(r"<!--\s*Page\s+(\d+)\s*-->", str(md_text))

    # First element is content before any marker (if any)
    if parts and parts[0].strip():
        pages.append({"page_number": 1, "content": parts[0].strip(), "page_label": "1"})

    # Remaining pairs: (page_number, content)
    for i in range(1, len(parts) - 1, 2):
        try:
            page_num = int(parts[i])
        except (ValueError, IndexError):
            continue
        content = parts[i + 1] if i + 1 < len(parts) else ""
        pages.append({
            "page_number": page_num,
            "content": content.strip() if content else "",
            "page_label": str(page_num),
        })

    # If no page markers found, treat the entire output as one page
    if not pages:
        pages = [{"page_number": 1, "content": str(md_text), "page_label": "1"}]

    return pages


def extract_toc_from_pdf(pdf_path: str) -> list[dict[str, Any]] | None:
    """Try to extract TOC directly from PDF metadata.

    Returns a list of [{title, page, level}, ...] or None.
    Level 1 = chapter, level 2+ = section.
    """
    import fitz

    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        doc.close()

        if toc and len(toc) > 2:
            return [
                {"title": item[1], "page": item[2], "level": item[0]}
                for item in toc
            ]
    except Exception:
        logger.exception("Failed to extract native PDF TOC from %s", pdf_path)

    return None


def render_page_image(pdf_path: str, page_num: int, zoom: float = 1.5) -> bytes:
    """Render a single PDF page as a PNG image.

    Args:
        pdf_path: Path to the PDF file.
        page_num: 1-indexed page number.
        zoom: Resolution multiplier (1.5 = ~150 DPI equivalent).

    Returns PNG image bytes.
    """
    import fitz

    doc = fitz.open(pdf_path)
    if page_num < 1 or page_num > doc.page_count:
        doc.close()
        raise ValueError(f"Page {page_num} out of range (1-{doc.page_count})")

    page = doc[page_num - 1]  # 0-indexed
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def delete_textbook_files(textbook_id: str) -> None:
    """Remove all files for a textbook from disk."""
    import shutil

    storage_root = settings.project_root / "backend" / settings.textbook_storage_path.lstrip("./")
    textbook_dir = storage_root / textbook_id
    if textbook_dir.exists():
        shutil.rmtree(textbook_dir)
        logger.info("Deleted textbook files: %s", textbook_dir)
