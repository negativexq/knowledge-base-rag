"""Two ways the PDF parser lost text the page holds (v2 loss audit):

- OCR spans meet without a space ("State Bank of" + "Travancore" read as
  "ofTravancore"), so names stopped matching.
- A decorative page frame detected as a table swallowed every text block
  inside it, though the table's cells held only the title: the cover's
  "Rick Scott GOVERNOR" never reached a chunk."""

from app.parsing.pdf_parser import _Item, _line_text, _outside_tables


def _line(*spans: str) -> dict:
    return {"spans": [{"text": text} for text in spans]}


def test_ocr_spans_are_separate_words():
    line = _line("State", " Bank", " of", "Travancore")

    assert _line_text(line, word_spans=True) == "State Bank of Travancore"
    assert _line_text(_line("Union", " Bank", "of India"), word_spans=True) == "Union Bank of India"


def test_text_layer_spans_still_join_as_written():
    # A span boundary can fall inside a word on the text layer (a drop cap,
    # a kerning run), so only OCR spans are taken as words.
    assert _line_text(_line("D", "rop cap")) == "Drop cap"


FRAME = _Item(
    (73.0, 73.0, 537.0, 716.0),
    "Table: Florida Department of Health Division of Medical Quality Assurance Strategic Plan",
    kind="table",
)


def test_text_inside_a_table_that_its_cells_do_not_hold_is_kept():
    title = _Item((150.0, 282.0, 391.0, 307.0), "Florida Department of Health")
    governor = _Item((311.0, 561.0, 380.0, 577.0), "Rick Scott")

    kept = _outside_tables([title, governor], [FRAME])

    assert kept == [governor]


def test_text_outside_every_table_is_kept():
    footer = _Item((100.0, 750.0, 300.0, 760.0), "Version 1.3")

    assert _outside_tables([footer], [FRAME]) == [footer]
