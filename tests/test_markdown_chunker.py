from app.ingestion.chunker import compute_doc_id
from app.ingestion.markdown_chunker import chunk_markdown_document, chunk_markdown_text


def _write_md(tmp_path, text: str, name: str = "doc.md") -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_chunk_markdown_document_tags_chunks_with_heading_path(tmp_path):
    md_path = _write_md(tmp_path, "# Kurulum\n\nBu bir kurulum paragrafıdır.")

    chunks = chunk_markdown_document(md_path, source_id="readme")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ("Kurulum",)


def test_chunk_markdown_document_metadata_shape(tmp_path):
    md_path = _write_md(tmp_path, "# Kurulum\n\nSome text here.")

    chunks = chunk_markdown_document(md_path, source_id="readme")

    for chunk in chunks:
        assert chunk.doc_id == compute_doc_id(md_path)
        assert chunk.source_type == "markdown"
        assert chunk.source_id == "readme"
        assert chunk.text


def test_chunk_markdown_document_defaults_source_type_to_markdown(tmp_path):
    md_path = _write_md(tmp_path, "# A\n\ntext")

    chunks = chunk_markdown_document(md_path, source_id="doc")

    assert all(chunk.source_type == "markdown" for chunk in chunks)


def test_chunk_markdown_document_accepts_an_explicit_doc_id_override(tmp_path):
    md_path = _write_md(tmp_path, "# A\n\ntext")

    chunks = chunk_markdown_document(md_path, source_id="doc", doc_id="explicit-hash")

    assert all(chunk.doc_id == "explicit-hash" for chunk in chunks)


def test_chunk_markdown_document_separates_chunks_by_heading_section(tmp_path):
    text = "# Kurulum\n\nInstall steps here.\n\n# Sorun Giderme\n\nTroubleshooting steps here."
    md_path = _write_md(tmp_path, text)

    chunks = chunk_markdown_document(md_path, source_id="readme")

    heading_paths = {chunk.heading_path for chunk in chunks}
    assert heading_paths == {("Kurulum",), ("Sorun Giderme",)}
    for chunk in chunks:
        if chunk.heading_path == ("Kurulum",):
            assert "Install steps" in chunk.text
        else:
            assert "Troubleshooting steps" in chunk.text


def test_chunk_markdown_document_preserves_nested_heading_path(tmp_path):
    text = "# Kurulum\n\n## Adım 1\n\nDo this first step very carefully."
    md_path = _write_md(tmp_path, text)

    chunks = chunk_markdown_document(md_path, source_id="readme")

    assert all(chunk.heading_path == ("Kurulum", "Adım 1") for chunk in chunks)


def test_chunk_markdown_document_splits_a_long_section_into_multiple_chunks(tmp_path):
    sentences = [f"Sentence number {i} has several words in it." for i in range(30)]
    text = "# Long Section\n\n" + " ".join(sentences)
    md_path = _write_md(tmp_path, text)

    chunks = chunk_markdown_document(
        md_path, source_id="doc", chunk_size_tokens=15, overlap_tokens=5
    )

    assert len(chunks) > 1
    assert all(chunk.heading_path == ("Long Section",) for chunk in chunks)


def test_chunk_markdown_document_with_no_heading_has_empty_heading_path(tmp_path):
    md_path = _write_md(tmp_path, "Just a plain paragraph, no heading at all.")

    chunks = chunk_markdown_document(md_path, source_id="doc")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ()


def test_chunk_markdown_document_empty_file_produces_no_chunks(tmp_path):
    md_path = _write_md(tmp_path, "")

    chunks = chunk_markdown_document(md_path, source_id="doc")

    assert chunks == []


def test_chunk_markdown_text_requires_no_file_and_uses_given_doc_id():
    chunks = chunk_markdown_text(
        "# Kurulum\n\nText from memory, no file involved.",
        source_id="notion-page-id",
        source_type="notion",
        doc_id="explicit-hash",
    )

    assert len(chunks) == 1
    assert chunks[0].doc_id == "explicit-hash"
    assert chunks[0].source_type == "notion"
    assert chunks[0].heading_path == ("Kurulum",)


def test_chunk_markdown_document_delegates_to_chunk_markdown_text(tmp_path):
    md_path = _write_md(tmp_path, "# A\n\ntext")

    via_document = chunk_markdown_document(md_path, source_id="doc", doc_id="h")
    via_text = chunk_markdown_text(
        "# A\n\ntext", source_id="doc", source_type="markdown", doc_id="h"
    )

    assert via_document == via_text


def test_repeated_heading_path_produces_chunks_with_distinct_occurrence_and_no_text_bleed():
    """Sprint 17.5: before the fix, `surrogate_by_heading` was keyed only
    by heading_path, so a second, independent "# Overview" section reused
    the FIRST occurrence's surrogate — its paragraphs were appended onto
    the same "page" as the first occurrence's, merging two unrelated
    sections' text into one chunking pass and making their citation
    identity indistinguishable.
    """
    text = (
        "# Overview\n\nFirst overview text about apples.\n\n"
        "# Other\n\nUnrelated middle section.\n\n"
        "# Overview\n\nSecond overview text about oranges."
    )

    chunks = chunk_markdown_text(text, source_id="doc", source_type="markdown", doc_id="h")

    overview_chunks = [c for c in chunks if c.heading_path == ("Overview",)]
    assert len(overview_chunks) == 2
    first, second = sorted(overview_chunks, key=lambda c: c.heading_occurrence)

    assert first.heading_occurrence == 0
    assert second.heading_occurrence == 1
    # No text bleed: each occurrence's chunk only contains its own text.
    assert "apples" in first.text and "oranges" not in first.text
    assert "oranges" in second.text and "apples" not in second.text
    # Different surrogate "page" -> different page_number -> different
    # point_id_for(...) identity even though heading_path is identical.
    assert first.page_number != second.page_number
