import logging
import os
from functools import cache

import fitz

from app.parsing.models import Paragraph

logger = logging.getLogger(__name__)

TEXT_BLOCK_TYPE = 0
# Recorded in the ingestion pipeline fingerprint (app/ingestion/fingerprint.py)
# through pdf_parser_version(); bump it whenever extraction output changes so
# existing PDFs are re-indexed.
PDF_PARSER_VERSION = "pymupdf_blocks_ruled_tables_v2"
# Tesseract languages for scanned pages (installed in the backend image as
# tesseract-ocr-tur / tesseract-ocr-eng) and the render resolution; 300 dpi
# is Tesseract's recommended input resolution.
OCR_LANGUAGES = "tur+eng"
OCR_DPI = 300


@cache
def ocr_available() -> bool:
    """True when Tesseract and every OCR_LANGUAGES model are installed."""
    try:
        tessdata = fitz.get_tessdata()
    except RuntimeError:
        return False
    return all(
        os.path.exists(os.path.join(tessdata, f"{language}.traineddata"))
        for language in OCR_LANGUAGES.split("+")
    )


def pdf_parser_version() -> str:
    """The parser identity for the pipeline fingerprint. OCR availability is
    part of it: the same scanned PDF yields text with OCR and nothing
    without, so moving between the two must re-index."""
    if ocr_available():
        return f"{PDF_PARSER_VERSION}+ocr_tesseract_{OCR_LANGUAGES}"
    return PDF_PARSER_VERSION


def _ocr_blocks(page: fitz.Page) -> list[tuple]:
    textpage = page.get_textpage_ocr(language=OCR_LANGUAGES, dpi=OCR_DPI, full=True)
    return page.get_text("blocks", textpage=textpage)


def _is_scanned(page: fitz.Page) -> bool:
    return not page.get_text("text").strip() and bool(page.get_images())


def _page_blocks(page: fitz.Page, pdf_path: str, page_number: int) -> list[tuple]:
    if not _is_scanned(page):
        return page.get_text("blocks")
    name = os.path.basename(pdf_path)
    if not ocr_available():
        logger.warning(
            "Skipping %s page %d: it has no text layer and OCR is not available",
            name,
            page_number,
        )
        return []
    try:
        return _ocr_blocks(page)
    except Exception:
        logger.warning("Skipping %s page %d: OCR failed", name, page_number, exc_info=True)
        return []


def extract_paragraphs(pdf_path: str) -> list[Paragraph]:
    """Extract paragraphs per page, in reading order.

    Ruled tables (PyMuPDF's line-based table finder) become one paragraph
    each, rendered by ``_table_text``; text blocks inside a table's area are
    dropped so the cells are not emitted twice.

    A page with no text layer but an image (a scan) is read with Tesseract
    OCR when it is installed; otherwise, or when OCR fails, the page is
    skipped with a warning. Pages with a text layer are never OCR'd.
    """
    paragraphs: list[Paragraph] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            tables = [
                (table.bbox, text)
                for table in page.find_tables().tables
                if (text := _table_text(table.extract()))
            ]
            items: list[tuple[float, float, str]] = [
                (bbox[1], bbox[0], text) for bbox, text in tables
            ]
            for block in _page_blocks(page, pdf_path, page_number):
                if block[6] != TEXT_BLOCK_TYPE or _inside_any(block, tables):
                    continue
                text = " ".join(line.strip() for line in block[4].splitlines() if line.strip())
                if text:
                    items.append((block[1], block[0], text))
            items.sort(key=lambda item: (round(item[0], 1), item[1]))

            for paragraph_index, (_, _, text) in enumerate(items):
                paragraphs.append(
                    Paragraph(page_number=page_number, paragraph_index=paragraph_index, text=text)
                )

    return paragraphs


def _cell(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _table_text(rows: list[list[object]]) -> str:
    """One line naming the columns, then one line per data row that repeats
    each column header next to its value ("Plan: Free | Storage: 15GB"), so
    any single row still carries its meaning after chunking. The first row
    is taken as the header; empty cells are left out."""
    cleaned = [[_cell(value) for value in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    header = [name or f"Column {i}" for i, name in enumerate(cleaned[0], 1)]
    lines = ["Table: " + " | ".join(header)]
    for row in cleaned[1:]:
        pairs = [f"{name}: {value}" for name, value in zip(header, row) if value]
        if pairs:
            lines.append(" | ".join(pairs))
    return "\n".join(lines)


def _inside_any(block: tuple, tables: list[tuple[tuple, str]]) -> bool:
    center_x = (block[0] + block[2]) / 2
    center_y = (block[1] + block[3]) / 2
    return any(
        bbox[0] <= center_x <= bbox[2] and bbox[1] <= center_y <= bbox[3] for bbox, _ in tables
    )
