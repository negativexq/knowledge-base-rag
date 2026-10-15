import fitz

from app.parsing.models import Paragraph

TEXT_BLOCK_TYPE = 0
# Recorded in the ingestion pipeline fingerprint (app/ingestion/fingerprint.py);
# bump it whenever extraction output changes so existing PDFs are re-indexed.
PDF_PARSER_VERSION = "pymupdf_blocks_ruled_tables_v2"


def extract_paragraphs(pdf_path: str) -> list[Paragraph]:
    """Extract paragraphs per page, in reading order.

    Ruled tables (PyMuPDF's line-based table finder) become one paragraph
    each, rendered by ``_table_text``; text blocks inside a table's area are
    dropped so the cells are not emitted twice.

    Only PDFs with an extractable text layer are supported. A page with no
    text layer (e.g. a scanned image) yields no paragraphs and is silently
    skipped — OCR fallback is out of scope for this sprint.
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
            for block in page.get_text("blocks"):
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
