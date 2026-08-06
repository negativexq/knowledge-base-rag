import re

from app.ingestion.chunker import (
    _build_page_text,
    _chunk_page_text,
    _extend_to_sentence_end,
    chunk_document,
    compute_doc_id,
)
from app.parsing.models import Paragraph

_SENTENCE_END = re.compile(r'[.!?][\'")\]]?$')


def test_compute_doc_id_is_stable_for_same_content(sample_pdf, tmp_path):
    copy_path = tmp_path / "copy.pdf"
    copy_path.write_bytes(open(sample_pdf, "rb").read())

    assert compute_doc_id(sample_pdf) == compute_doc_id(str(copy_path))


def test_build_page_text_tracks_paragraph_char_offsets():
    paragraphs = [
        Paragraph(page_number=1, paragraph_index=0, text="First paragraph."),
        Paragraph(page_number=1, paragraph_index=1, text="Second paragraph here."),
    ]

    page_text, offsets = _build_page_text(paragraphs)

    assert page_text.startswith("First paragraph.")
    for paragraph_index, start, end in offsets:
        assert page_text[start:end] == paragraphs[paragraph_index].text


def test_extend_to_sentence_end_moves_forward_to_next_period():
    text = "This is one sentence. This is another sentence. And a third."
    mid_word_pos = text.index("another")

    extended = _extend_to_sentence_end(text, mid_word_pos)

    assert text[:extended].endswith("sentence.")


def test_extend_to_sentence_end_falls_back_when_no_period_nearby():
    text = "word " * 500  # no sentence-ending punctuation anywhere
    pos = 100

    assert _extend_to_sentence_end(text, pos) == pos


def test_chunk_page_text_never_splits_a_sentence_across_non_final_chunks():
    paragraphs = [
        Paragraph(page_number=1, paragraph_index=0, text=_long_paragraph())
    ]
    page_text, offsets = _build_page_text(paragraphs)

    chunks = _chunk_page_text(
        page_text,
        offsets,
        page_number=1,
        chunk_size_tokens=15,
        overlap_tokens=5,
    )

    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert _SENTENCE_END.search(chunk.text.strip()), chunk.text


def test_chunk_page_text_overlaps_consecutive_chunks():
    paragraphs = [
        Paragraph(page_number=1, paragraph_index=0, text=_long_paragraph())
    ]
    page_text, offsets = _build_page_text(paragraphs)

    chunks = _chunk_page_text(
        page_text,
        offsets,
        page_number=1,
        chunk_size_tokens=15,
        overlap_tokens=5,
    )

    for prev_chunk, next_chunk in zip(chunks, chunks[1:]):
        assert next_chunk.char_range[0] < prev_chunk.char_range[1]


def test_chunk_document_maps_each_chunk_to_correct_page(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5)

    assert chunks  # non-empty
    for chunk in chunks:
        marker = f"PAGE{chunk.page_number}-"
        assert marker in chunk.text, (
            f"chunk attributed to page {chunk.page_number} but text is: {chunk.text!r}"
        )


def test_chunk_document_skips_page_with_no_text_layer(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5)

    assert all(chunk.page_number != 4 for chunk in chunks)


def test_chunk_document_metadata_shape(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5)

    for chunk in chunks:
        assert chunk.doc_id == compute_doc_id(sample_pdf)
        assert chunk.source_type == "pdf"
        assert chunk.source_id == "sample"
        assert isinstance(chunk.page_number, int)
        assert isinstance(chunk.paragraph_index, int)
        assert isinstance(chunk.char_range, tuple) and len(chunk.char_range) == 2
        assert chunk.char_range[0] < chunk.char_range[1]
        assert chunk.text


def test_chunk_document_defaults_source_type_to_pdf(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5)

    assert all(chunk.source_type == "pdf" for chunk in chunks)


def test_chunk_document_pdf_chunks_have_empty_heading_path(sample_pdf):
    chunks = chunk_document(sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5)

    assert all(chunk.heading_path == () for chunk in chunks)


def test_chunk_document_accepts_an_explicit_doc_id_override(sample_pdf):
    chunks = chunk_document(
        sample_pdf,
        source_id="sample",
        chunk_size_tokens=20,
        overlap_tokens=5,
        doc_id="explicit-hash",
    )

    assert all(chunk.doc_id == "explicit-hash" for chunk in chunks)


def _long_paragraph() -> str:
    sentences = [f"Sentence number {i} has several words in it." for i in range(20)]
    return " ".join(sentences)
