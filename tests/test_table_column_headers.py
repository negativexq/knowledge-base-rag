"""10-K statements reach the model without column headers: "ASSETS: Long-term
debt, excluding current portion | 6,692 | 7,514". The dates ("August 29,
2021") are printed above the ruled area, so the table's first row is "ASSETS"
with empty cells, and an operand could not be bound to its year (luna
resolver rows 1018, 1020, 1023). PyMuPDF finds such a header outside the
table; it is now used. A value printed after a lone currency symbol sits one
column right of its header ("$ | 11,258"); it takes the symbol's header."""

import fitz

from app.parsing.pdf_parser import _table_text, extract_paragraphs


def test_a_value_after_a_lone_currency_symbol_takes_its_header():
    rows = [
        ["ASSETS", "August 29, 2021", "", "", "August 30, 2020", ""],
        ["Cash and cash equivalents", "$", "11,258", "", "$", "12,277"],
        ["Long-term debt, excluding current portion", "6,692", "", "", "7,514", ""],
    ]

    assert _table_text(rows).splitlines() == [
        "Table: ASSETS | August 29, 2021 | August 30, 2020",
        "ASSETS: Cash and cash equivalents | August 29, 2021: $ 11,258 | August 30, 2020: $ 12,277",
        "ASSETS: Long-term debt, excluding current portion | August 29, 2021: 6,692 "
        "| August 30, 2020: 7,514",
    ]


def test_an_unnamed_column_that_does_not_follow_a_symbol_keeps_its_bare_value():
    rows = [["Region", "Q1", "", "Total"], ["North", "12", "note", "30"]]

    assert _table_text(rows).splitlines() == [
        "Table: Region | Q1 | | Total",
        "Region: North | Q1: 12 | note | Total: 30",
    ]


def _statement_pdf(tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    cols = [72, 300, 420, 540]
    page.insert_text((310, 95), "August 29, 2021", fontsize=9)
    page.insert_text((430, 95), "August 30, 2020", fontsize=9)
    rows = [
        ["ASSETS", "", ""],
        ["Total current assets", "29,505", "28,120"],
        ["Total assets", "59,268", "55,556"],
    ]
    top = 100
    ys = [top + i * 22 for i in range(len(rows) + 1)]
    for y in ys:
        page.draw_line((cols[0], y), (cols[-1], y))
    for x in cols:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value:
                page.insert_text((cols[c] + 5, ys[r] + 15), value, fontsize=9)
    path = tmp_path / "statement.pdf"
    doc.save(path)
    return str(path)


def test_a_header_printed_above_the_table_names_its_columns(tmp_path):
    text = "\n".join(p.text for p in extract_paragraphs(_statement_pdf(tmp_path)))

    assert "Total assets | August 29, 2021: 59,268 | August 30, 2020: 55,556" in text
