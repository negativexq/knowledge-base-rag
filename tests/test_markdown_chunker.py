from app.ingestion.chunker import compute_doc_id
from app.ingestion.markdown_chunker import chunk_markdown_document


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
