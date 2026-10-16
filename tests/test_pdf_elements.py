"""PDF pages become typed document elements (heading, paragraph, table) that
carry their page, position and the heading path they sit under. Headings are
found from font size relative to the document's body text; text repeated on
most pages (running headers, footers) is never a heading. A short label
ending in ":" is kept with the value printed directly under it, and lines laid
out as rows of short cells keep their row structure."""

import logging

import fitz
import pytest

import app.parsing.pdf_parser as pdf_parser
from app.parsing.pdf_parser import extract_elements, extract_paragraphs


def _save(doc, tmp_path, name="doc.pdf") -> str:
    path = tmp_path / name
    doc.save(path)
    return str(path)


@pytest.fixture
def report_pdf(tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Annual Report", fontsize=22)
    page.insert_text((72, 100), "Revenue", fontsize=15)
    page.insert_text((72, 125), "Revenue grew in every region this year.", fontsize=11)
    page.insert_text((72, 165), "Outlook", fontsize=15)
    page.insert_text((72, 190), "We expect steady demand next year.", fontsize=11)
    page = doc.new_page()
    page.insert_text((72, 60), "The outlook assumes stable prices.", fontsize=11)
    page.insert_text((72, 100), "Risks", fontsize=15)
    page.insert_text((72, 125), "Currency moves are the main risk.", fontsize=11)
    return _save(doc, tmp_path)


def _by_text(elements):
    return {element.text: element for element in elements}


def test_larger_text_becomes_headings_with_levels(report_pdf):
    elements = _by_text(extract_elements(report_pdf))

    assert elements["Annual Report"].kind == "heading"
    assert elements["Annual Report"].heading_level == 1
    assert elements["Revenue"].kind == "heading"
    assert elements["Revenue"].heading_level == 2
    assert elements["Revenue grew in every region this year."].kind == "paragraph"


def test_paragraphs_carry_the_heading_path_they_sit_under(report_pdf):
    elements = _by_text(extract_elements(report_pdf))

    assert elements["Revenue grew in every region this year."].heading_path == (
        "Annual Report",
        "Revenue",
    )
    assert elements["We expect steady demand next year."].heading_path == (
        "Annual Report",
        "Outlook",
    )


def test_heading_path_continues_across_pages(report_pdf):
    elements = _by_text(extract_elements(report_pdf))

    assert elements["The outlook assumes stable prices."].heading_path == (
        "Annual Report",
        "Outlook",
    )
    assert elements["Currency moves are the main risk."].heading_path == (
        "Annual Report",
        "Risks",
    )


def test_elements_record_page_index_and_bbox(report_pdf):
    elements = extract_elements(report_pdf)

    assert [(e.page_number, e.index) for e in elements if e.page_number == 2] == [
        (2, 0),
        (2, 1),
        (2, 2),
    ]
    assert all(e.bbox[2] > e.bbox[0] and e.bbox[3] > e.bbox[1] for e in elements)


def test_paragraphs_are_the_element_texts_in_order(report_pdf):
    elements = extract_elements(report_pdf)
    paragraphs = extract_paragraphs(report_pdf)

    assert [(p.page_number, p.paragraph_index, p.text) for p in paragraphs] == [
        (e.page_number, e.index, e.text) for e in elements if e.kind != "furniture"
    ]


def _furniture_pdf(tmp_path) -> str:
    doc = fitz.open()
    for number in range(1, 4):
        page = doc.new_page()
        page.insert_text((72, 30), "ACME CORPORATION", fontsize=16)
        page.insert_text((72, 300), f"Body text on page {number} of the report.", fontsize=11)
        page.insert_text((72, 400), "See the appendix for definitions.", fontsize=11)
        page.insert_text((300, 820), str(number), fontsize=9)
    return _save(doc, tmp_path, "furniture.pdf")


def test_running_headers_and_page_numbers_are_page_furniture(tmp_path):
    elements = extract_elements(_furniture_pdf(tmp_path))

    furniture = [e.text for e in elements if e.kind == "furniture"]
    assert furniture == ["ACME CORPORATION", "1", "ACME CORPORATION", "2", "ACME CORPORATION", "3"]
    assert all(e.heading_path == () for e in elements)


def test_text_repeated_in_the_body_is_not_furniture(tmp_path):
    elements = extract_elements(_furniture_pdf(tmp_path))

    repeated = [e for e in elements if e.text == "See the appendix for definitions."]
    assert len(repeated) == 3
    assert all(e.kind == "paragraph" for e in repeated)


def test_page_furniture_is_left_out_of_paragraphs(tmp_path):
    texts = [p.text for p in extract_paragraphs(_furniture_pdf(tmp_path))]

    assert "ACME CORPORATION" not in texts
    assert "2" not in texts
    assert "Body text on page 2 of the report." in texts


def test_a_label_is_kept_with_the_value_under_it(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Produced by:", fontsize=12)
    page.insert_text((72, 140), "Northwind Records Office", fontsize=12)
    page.insert_text((72, 300), "Unrelated closing sentence of the page.", fontsize=12)
    texts = [e.text for e in extract_elements(_save(doc, tmp_path))]

    assert texts == [
        "Produced by: Northwind Records Office",
        "Unrelated closing sentence of the page.",
    ]


def test_a_sentence_ending_in_a_colon_is_not_merged(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 100), "The following steps describe how the system is installed:", fontsize=12
    )
    page.insert_text((72, 140), "Download the installer.", fontsize=12)
    texts = [e.text for e in extract_elements(_save(doc, tmp_path))]

    assert len(texts) == 2


def test_lines_of_short_cells_keep_their_rows(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    rows = [
        ("Part", "Prefix", "Package Type"),
        ("A100", "N", "44-pin carrier"),
        ("B200", "D", "40-pin ceramic"),
    ]
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("helv")
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            writer.append((72 + c * 110, 100 + r * 14), cell, font=font, fontsize=10)
    writer.write_text(page)
    [element] = extract_elements(_save(doc, tmp_path))

    assert element.text.splitlines() == [
        "Part | Prefix | Package Type",
        "A100 | N | 44-pin carrier",
        "B200 | D | 40-pin ceramic",
    ]


def test_tables_are_table_elements_with_their_rows(tmp_path):
    from tests.test_pdf_tables import _ruled_table

    doc = fitz.open()
    page = doc.new_page()
    _ruled_table(page, 90, [["Plan", "Storage"], ["Free", "15GB"]])
    [table] = extract_elements(_save(doc, tmp_path))

    assert table.kind == "table"
    assert table.table_rows == (("Plan", "Storage", ""), ("Free", "15GB", ""))


def test_empty_header_cells_are_not_given_made_up_names(tmp_path):
    from tests.test_pdf_tables import _ruled_table

    doc = fitz.open()
    page = doc.new_page()
    _ruled_table(page, 90, [["Region", "", "Total"], ["North", "12", "30"]])
    [table] = [p.text for p in extract_paragraphs(_save(doc, tmp_path))]

    assert "Column" not in table
    assert table.splitlines() == ["Table: Region | | Total", "Region: North | 12 | Total: 30"]


def _garbled_pdf(tmp_path) -> str:
    """Page 2's text layer is control characters: a font without a Unicode
    mapping, which is what PyMuPDF returns for such fonts."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "A normal page.", fontsize=11)
    page = doc.new_page()
    page.insert_text((72, 72), "Readable heading", fontsize=11)
    garbage = "".join(chr(c) for c in (0x18, 0x0F, 0x07, 0x0C, 0x04, 0x19, 0x02, 0x17)) * 12
    page.insert_text((72, 100), garbage, fontsize=11)
    return _save(doc, tmp_path, "garbled.pdf")


def test_garbled_text_layer_is_read_with_ocr(tmp_path, monkeypatch):
    path = _garbled_pdf(tmp_path)
    with fitz.open(path) as doc:
        raw = doc[1].get_text()
    if sum(ch < " " and ch not in "\n\t" for ch in raw) < 50:
        pytest.skip("this PyMuPDF build does not keep control characters in the text layer")
    calls: list[int] = []
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_lines",
        lambda page: calls.append(page.number + 1)
        or [
            ((72, 60, 200, 72), "Readable heading"),
            ((72, 76, 300, 88), "Excise duty rose last year."),
        ],
    )

    elements = extract_elements(path)

    assert calls == [2]
    [ocr] = [e for e in elements if e.page_number == 2]
    assert ocr.text == "Readable heading Excise duty rose last year."
    assert "ocr:garbled_text" in ocr.flags


def test_garbled_text_is_dropped_without_ocr(tmp_path, monkeypatch, caplog):
    path = _garbled_pdf(tmp_path)
    with fitz.open(path) as doc:
        raw = doc[1].get_text()
    if sum(ch < " " and ch not in "\n\t" for ch in raw) < 50:
        pytest.skip("this PyMuPDF build does not keep control characters in the text layer")
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger="app.parsing.pdf_parser"):
        elements = extract_elements(path)

    assert [e.text for e in elements if e.page_number == 2] == ["Readable heading"]
    assert "garbled" in caplog.records[0].getMessage()


def test_a_page_drawn_as_vector_shapes_is_read_with_ocr(tmp_path, monkeypatch):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 40), "COMPANY NAME", fontsize=14)
    for i in range(400):  # glyph outlines drawn as paths, no text layer
        x, y = 72 + (i % 40) * 10, 100 + (i // 40) * 20
        page.draw_rect(fitz.Rect(x, y, x + 6, y + 8))
    path = _save(doc, tmp_path, "vector.pdf")
    calls: list[int] = []
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_lines",
        lambda page: calls.append(page.number + 1)
        or [
            ((72, 30, 200, 50), "COMPANY NAME"),
            ((72, 100, 180, 116), "Harbor Trust"),
            ((72, 120, 190, 136), "Riverside Bank"),
        ],
    )

    elements = extract_elements(path)

    assert calls == [1]
    assert [e.text for e in elements] == ["COMPANY NAME", "Harbor Trust Riverside Bank"]
    assert all("ocr:vector_text" in e.flags for e in elements)


def test_ordinary_text_pages_with_a_few_drawings_are_not_ocrd(tmp_path, monkeypatch):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A text page with a rule under the title.", fontsize=11)
    page.draw_line((72, 80), (500, 80))
    calls: list[int] = []
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr_lines", lambda page: calls.append(1) or [])

    extract_elements(_save(doc, tmp_path))

    assert calls == []


def test_bold_titles_at_body_size_are_headings(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Introduction", fontsize=11, fontname="hebo")
    page.insert_text((72, 85), "Claims are checked against several sources.", fontsize=11)
    page.insert_text((72, 110), "Most of them need more than one reasoning step.", fontsize=11)
    elements = _by_text(extract_elements(_save(doc, tmp_path)))

    assert elements["Introduction"].kind == "heading"
    assert elements["Most of them need more than one reasoning step."].heading_path == (
        "Introduction",
    )


def test_bookmarks_decide_headings_and_levels(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Packages", fontsize=11)
    page.insert_text((72, 85), "Every part ships in one of three packages.", fontsize=11)
    page.insert_text((72, 120), "Big Note In Large Type", fontsize=20)
    page = doc.new_page()
    page.insert_text((72, 60), "Thermal data", fontsize=11)
    page.insert_text((72, 85), "Values are approximate for static air.", fontsize=11)
    doc.set_toc([[1, "Packages", 1], [2, "Thermal data", 2]])
    elements = _by_text(extract_elements(_save(doc, tmp_path)))

    assert elements["Packages"].heading_level == 1
    assert elements["Thermal data"].heading_level == 2
    assert elements["Big Note In Large Type"].kind == "paragraph"
    assert elements["Values are approximate for static air."].heading_path == (
        "Packages",
        "Thermal data",
    )


def test_noise_and_numbers_are_not_headings(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "T2 #1~ |l", fontsize=20)
    page.insert_text((72, 100), "2003", fontsize=20)
    page.insert_text((72, 140), "Body text that is long enough to set the body size.", fontsize=11)
    kinds = {e.text: e.kind for e in extract_elements(_save(doc, tmp_path))}

    assert kinds["T2 #1~ |l"] == "paragraph"
    assert kinds["2003"] == "paragraph"


def test_prose_lines_are_not_mistaken_for_rows(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("helv")
    for r, words in enumerate([("The", "quick", "brown", "fox"), ("jumps", "over", "the", "dog")]):
        x = 72
        for word in words:
            writer.append((x, 100 + r * 14), word, font=font, fontsize=10)
            x += font.text_length(word + " ", fontsize=10) + 1
    writer.write_text(page)
    [element] = extract_elements(_save(doc, tmp_path))

    assert "|" not in element.text


def test_a_label_value_pair_is_never_a_heading(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Owner:", fontsize=12, fontname="hebo")
    page.insert_text((72, 140), "Records Office", fontsize=12, fontname="hebo")
    page.insert_text((72, 200), "A long body sentence that sets the body text size.", fontsize=12)
    [pair] = [e for e in extract_elements(_save(doc, tmp_path)) if e.text.startswith("Owner")]

    assert pair.text == "Owner: Records Office"
    assert pair.kind == "paragraph"


def test_rows_whose_cells_do_not_line_up_are_prose(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("helv")
    for r, (words, step) in enumerate(
        [(("Ann", "Lee,", "Bo", "Chan,"), 52), (("Cy", "Dunn,", "Ed"), 81)]
    ):
        for c, word in enumerate(words):
            writer.append((72 + c * step, 100 + r * 14), word, font=font, fontsize=10)
    writer.write_text(page)
    [element] = extract_elements(_save(doc, tmp_path))

    assert "|" not in element.text


def test_numbered_section_titles_are_headings_without_any_styling(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "1. Plans and seats", fontsize=9)
    page.insert_text((72, 80), "Standard workspaces support ten seats in total.", fontsize=9)
    page.insert_text((72, 110), "1.1 Seat limits", fontsize=9)
    page.insert_text((72, 130), "A seat is an active workspace membership.", fontsize=9)
    page.insert_text((72, 160), "2. Workspace roles", fontsize=9)
    page.insert_text((72, 180), "Owners can manage billing for the workspace.", fontsize=9)
    elements = _by_text(extract_elements(_save(doc, tmp_path)))

    assert elements["1. Plans and seats"].kind == "heading"
    assert elements["A seat is an active workspace membership."].heading_path == (
        "1. Plans and seats",
        "1.1 Seat limits",
    )
    assert elements["Owners can manage billing for the workspace."].heading_path == (
        "2. Workspace roles",
    )
