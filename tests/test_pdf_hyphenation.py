"""A word broken across lines with a hyphen ("pri-" / "marily") is joined
back, on the text layer and in OCR prose, so retrieval, matching and the
model read "primarily". A hyphen before a capital or a digit, or at the
end of the text, is kept ("Covid-" / "19", "CAN-" / "Bus")."""

import fitz
import pytest

import app.parsing.pdf_parser as pdf_parser
from app.parsing.pdf_parser import extract_elements


@pytest.mark.parametrize(
    ("lines", "text"),
    [
        (
            ["claims that consist pri-", "marily of one fact."],
            "claims that consist primarily of one fact.",
        ),
        (["the Covid-", "19 period"], "the Covid- 19 period"),
        (["a CAN-", "Bus link"], "a CAN- Bus link"),
        (["ends with a dash -", "and goes on"], "ends with a dash - and goes on"),
    ],
)
def test_line_break_hyphens_are_joined_only_inside_a_word(lines, text):
    assert pdf_parser._join_lines(lines) == text


def test_the_text_layer_joins_a_hyphenated_word(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Most fact-checking datasets consist pri-", fontsize=11)
    page.insert_text((72, 114), "marily of simple claims.", fontsize=11)
    path = tmp_path / "hyphen.pdf"
    doc.save(path)

    [element] = extract_elements(str(path))

    assert element.text == "Most fact-checking datasets consist primarily of simple claims."


def test_ocr_prose_joins_a_hyphenated_word():
    lines = [
        ((50, 100, 250, 110), "the datasets consist pri-"),
        ((50, 114, 230, 124), "marily of simple claims"),
    ]

    assert [text for _, text in pdf_parser._ocr_layout(lines)] == [
        "the datasets consist primarily of simple claims"
    ]
