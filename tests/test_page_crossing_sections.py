"""A PDF section that continues on the next page stays one unit for
chunking: a chunk may cross the page break inside its section. Its
page_number and paragraph_index still name where it starts (the citation
anchor); page_end names the page it ends on. PDFs without detected sections
keep page-bound chunks."""

import fitz
import pytest

from app.evaluation.mmlongbench import payload_pages
from app.evidence.support_units import section_label
from app.ingestion.chunker import chunk_document
from app.parsing.pdf_parser import extract_paragraphs


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
    path = tmp_path / "report.pdf"
    doc.save(path)
    return str(path)


def _chunk_with(chunks, text):
    [chunk] = [c for c in chunks if text in c.text]
    return chunk


def test_a_section_continuing_on_the_next_page_is_one_chunk(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")

    outlook = _chunk_with(chunks, "steady demand")
    assert "stable prices" in outlook.text
    assert "Currency" not in outlook.text
    assert (outlook.page_number, outlook.page_end, outlook.page_crossing) == (1, 2, True)


def test_a_crossing_chunk_is_anchored_where_it_starts(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")
    page_one = [p for p in extract_paragraphs(report_pdf) if p.page_number == 1]
    page_text = "\n\n".join(p.text for p in page_one) + "\n\n"

    outlook = _chunk_with(chunks, "steady demand")
    assert outlook.paragraph_index == [p.text for p in page_one].index("Outlook")
    assert page_text[outlook.char_range[0] :].startswith("Outlook")


def test_chunks_within_one_page_do_not_cross(report_pdf):
    chunks = chunk_document(report_pdf, source_id="report")

    risks = _chunk_with(chunks, "Currency")
    assert (risks.page_number, risks.page_end, risks.page_crossing) == (2, 2, False)


def test_a_long_crossing_section_starts_later_chunks_on_their_own_page(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Background", fontsize=16)
    sentence = "This sentence explains the background in plain words. "
    page.insert_textbox(fitz.Rect(72, 80, 520, 800), sentence * 40, fontsize=10)
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 60, 520, 800), sentence * 40, fontsize=10)
    path = tmp_path / "long.pdf"
    doc.save(path)

    chunks = chunk_document(str(path), source_id="long", chunk_size_tokens=120, overlap_tokens=10)

    assert {c.section_path for c in chunks} == {("Background",)}
    assert any(c.page_crossing for c in chunks)
    assert [c.page_number for c in chunks] == sorted(c.page_number for c in chunks)
    assert chunks[-1].page_number == 2


def test_pdfs_without_sections_keep_page_bound_chunks(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample")

    assert all(c.page_end == c.page_number and c.page_crossing is False for c in chunks)


def test_labels_and_benchmark_pages_cover_the_page_range():
    payload = {"page_number": 3, "page_end": 4, "section_path": ["Packages"]}

    assert section_label(payload) == "Packages (pages 3–4)"
    assert payload_pages(payload) == [3, 4]
    assert payload_pages({"page_number": 5}) == [5]
