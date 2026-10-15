"""Ruled tables in text PDFs are extracted as tables: each row becomes one
self-contained line that repeats the column headers, so a chunk boundary
can never separate a value from the header that gives it meaning. The
table's cells are not emitted a second time as loose text blocks."""

import fitz
import pytest

from app.ingestion.chunker import chunk_document
from app.parsing.pdf_parser import extract_paragraphs

COLS = [72, 200, 330, 460]


def _ruled_table(page, top: float, cells: list[list[str]], row_height: float = 25) -> float:
    rows = [top + i * row_height for i in range(len(cells) + 1)]
    for x in COLS:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((COLS[0], y), (COLS[-1], y))
    for r, row in enumerate(cells):
        for c, value in enumerate(row):
            if value:
                page.insert_text((COLS[c] + 5, rows[r] + 17), value, fontsize=10)
    return rows[-1]


@pytest.fixture
def table_pdf(tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Pricing overview for Nimbus plans.", fontsize=11)
    bottom = _ruled_table(
        page,
        90,
        [["Plan", "Storage", "Price"], ["Free", "15GB", "0 TL"], ["Pro", "1TB", ""]],
    )
    page.insert_text((72, bottom + 35), "Prices include VAT.", fontsize=11)
    doc.new_page().insert_text((72, 60), "Second page has no table.", fontsize=11)
    path = tmp_path / "pricing.pdf"
    doc.save(path)
    return str(path)


def test_rows_are_linearized_with_their_headers_in_reading_order(table_pdf):
    page_one = [p.text for p in extract_paragraphs(table_pdf) if p.page_number == 1]

    assert page_one == [
        "Pricing overview for Nimbus plans.",
        "Table: Plan | Storage | Price\n"
        "Plan: Free | Storage: 15GB | Price: 0 TL\n"
        "Plan: Pro | Storage: 1TB",
        "Prices include VAT.",
    ]


def test_paragraph_indexes_stay_sequential_per_page(table_pdf):
    page_one = [p for p in extract_paragraphs(table_pdf) if p.page_number == 1]

    assert [p.paragraph_index for p in page_one] == [0, 1, 2]


def test_table_cells_are_not_repeated_as_loose_text(table_pdf):
    text = "\n".join(p.text for p in extract_paragraphs(table_pdf))

    assert "Free 15GB 0 TL" not in text
    assert text.count("15GB") == 1


def test_pages_without_tables_are_unchanged(table_pdf):
    page_two = [p.text for p in extract_paragraphs(table_pdf) if p.page_number == 2]

    assert page_two == ["Second page has no table."]


def test_table_rows_reach_the_chunks(table_pdf):
    chunks = chunk_document(table_pdf, source_id="pricing")

    page_one = " ".join(c.text for c in chunks if c.page_number == 1)
    assert "Plan: Free | Storage: 15GB | Price: 0 TL" in page_one


def test_multi_line_cells_are_joined_with_spaces(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rows = [90, 115, 165]
    for x in COLS:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    for y in rows:
        page.draw_line((COLS[0], y), (COLS[-1], y))
    for c, header in enumerate(["Step", "Command", "Notes"]):
        page.insert_text((COLS[c] + 5, 107), header, fontsize=10)
    page.insert_text((COLS[0] + 5, 132), "Login", fontsize=10)
    page.insert_text((COLS[1] + 5, 132), "nimbus login", fontsize=10)
    page.insert_text((COLS[2] + 5, 132), "Opens a", fontsize=10)
    page.insert_text((COLS[2] + 5, 147), "browser", fontsize=10)
    path = tmp_path / "steps.pdf"
    doc.save(path)

    [table] = [p.text for p in extract_paragraphs(str(path))]

    assert table.splitlines()[1] == "Step: Login | Command: nimbus login | Notes: Opens a browser"
