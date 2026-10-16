"""Scanned PDF pages (an image, no text layer) are read with Tesseract OCR
(Turkish + English) when it is installed. Pages that have a text layer are
never OCR'd. Without OCR, or when OCR fails, an image-only page is skipped
with a warning instead of silently.

Tesseract is installed in the backend image, not necessarily on the
developer machine, so most tests replace the OCR call; the last one runs the
real engine and skips when it is missing."""

import logging

import fitz
import pytest

import app.parsing.pdf_parser as pdf_parser
from app.parsing.pdf_parser import extract_paragraphs, pdf_parser_version


def _scanned_page_pdf(tmp_path, text: str = "Iade suresi 30 gundur.", with_text_page=True) -> str:
    """Page 1: real text. Page 2: the same kind of sentence, but only as a
    rendered image (what a scanner produces)."""
    source = fitz.open()
    source.new_page(width=420, height=160).insert_text((30, 80), text, fontsize=22)
    pixmap = source[0].get_pixmap(dpi=200)

    doc = fitz.open()
    if with_text_page:
        doc.new_page().insert_text((72, 72), "This page has a text layer.", fontsize=11)
    scanned = doc.new_page(width=420, height=160)
    scanned.insert_image(scanned.rect, pixmap=pixmap)
    path = tmp_path / "scanned.pdf"
    doc.save(path)
    return str(path)


def _fake_ocr(calls: list[int], lines):
    def ocr(page):
        calls.append(page.number + 1)
        return lines

    return ocr


def test_image_only_page_is_read_with_ocr(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(
        pdf_parser,
        "_ocr_lines",
        _fake_ocr(
            calls,
            [((30, 60, 200, 75), "Iade suresi"), ((30, 80, 190, 95), "30 gundur.")],
        ),
    )

    paragraphs = extract_paragraphs(_scanned_page_pdf(tmp_path))

    assert calls == [2]
    assert [(p.page_number, p.paragraph_index, p.text) for p in paragraphs] == [
        (1, 0, "This page has a text layer."),
        (2, 0, "Iade suresi 30 gundur."),
    ]


def test_pages_with_a_text_layer_are_never_ocrd(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr_lines", _fake_ocr(calls, []))
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Plain text page.", fontsize=11)
    path = tmp_path / "text.pdf"
    doc.save(path)

    extract_paragraphs(str(path))

    assert calls == []


def test_image_only_page_without_ocr_is_skipped_with_a_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger="app.parsing.pdf_parser"):
        paragraphs = extract_paragraphs(_scanned_page_pdf(tmp_path))

    assert [p.page_number for p in paragraphs] == [1]
    [record] = caplog.records
    assert "page 2" in record.getMessage()
    assert "OCR is not available" in record.getMessage()


def test_ocr_failure_skips_the_page_with_a_warning(tmp_path, monkeypatch, caplog):
    def broken(page):
        raise RuntimeError("tesseract crashed")

    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr_lines", broken)

    with caplog.at_level(logging.WARNING, logger="app.parsing.pdf_parser"):
        paragraphs = extract_paragraphs(_scanned_page_pdf(tmp_path))

    assert [p.page_number for p in paragraphs] == [1]
    assert "OCR failed" in caplog.records[0].getMessage()


def test_parser_version_records_whether_ocr_is_available(monkeypatch):
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: False)
    without = pdf_parser_version()
    monkeypatch.setattr(pdf_parser, "ocr_available", lambda: True)
    with_ocr = pdf_parser_version()

    assert without == pdf_parser.PDF_PARSER_VERSION
    assert with_ocr == f"{pdf_parser.PDF_PARSER_VERSION}+ocr_tesseract_{pdf_parser.OCR_LANGUAGES}"


@pytest.mark.skipif(
    not pdf_parser.ocr_available(), reason="Tesseract with tur+eng is not installed"
)
def test_real_tesseract_reads_a_scanned_turkish_sentence(tmp_path):
    path = _scanned_page_pdf(tmp_path, text="İade süresi 30 gündür.", with_text_page=False)

    text = " ".join(p.text for p in extract_paragraphs(path))

    assert "30" in text
    assert "süresi" in text
