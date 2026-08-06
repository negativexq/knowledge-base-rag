import hashlib

from app.connectors.filesystem import LocalFilesystemConnector


def test_source_type_is_filesystem():
    assert LocalFilesystemConnector("/tmp").source_type == "filesystem"


def test_list_documents_finds_pdf_and_markdown_files(tmp_path):
    (tmp_path / "handbook.pdf").write_bytes(b"%PDF-fake-content")
    (tmp_path / "readme.md").write_text("# Readme")

    connector = LocalFilesystemConnector(tmp_path)
    documents = connector.list_documents()

    content_types = {d.content_type for d in documents}
    assert content_types == {"pdf", "markdown"}
    assert len(documents) == 2


def test_list_documents_ignores_unsupported_extensions(tmp_path):
    (tmp_path / "handbook.pdf").write_bytes(b"%PDF-fake-content")
    (tmp_path / "notes.txt").write_text("plain text, not supported")
    (tmp_path / ".DS_Store").write_bytes(b"junk")

    connector = LocalFilesystemConnector(tmp_path)
    documents = connector.list_documents()

    assert len(documents) == 1
    assert documents[0].content_type == "pdf"


def test_list_documents_is_not_recursive(tmp_path):
    (tmp_path / "top.md").write_text("# Top")
    subfolder = tmp_path / "nested"
    subfolder.mkdir()
    (subfolder / "buried.md").write_text("# Buried")

    connector = LocalFilesystemConnector(tmp_path)
    documents = connector.list_documents()

    assert [d.path.name for d in documents] == ["top.md"]


def test_source_id_includes_extension_to_avoid_same_stem_collisions(tmp_path):
    (tmp_path / "handbook.pdf").write_bytes(b"pdf content")
    (tmp_path / "handbook.md").write_text("# Handbook")

    connector = LocalFilesystemConnector(tmp_path)
    documents = connector.list_documents()

    source_ids = {d.source_id for d in documents}
    assert len(source_ids) == 2  # no collision despite the same filename stem
    assert "handbook_pdf" in source_ids
    assert "handbook_md" in source_ids


def test_list_documents_is_sorted_deterministically(tmp_path):
    (tmp_path / "b.md").write_text("# B")
    (tmp_path / "a.md").write_text("# A")

    connector = LocalFilesystemConnector(tmp_path)
    documents = connector.list_documents()

    assert [d.path.name for d in documents] == ["a.md", "b.md"]


def test_fetch_content_returns_the_raw_file_bytes(tmp_path):
    (tmp_path / "readme.md").write_text("# Hello")

    connector = LocalFilesystemConnector(tmp_path)
    document = connector.list_documents()[0]

    assert connector.fetch_content(document) == b"# Hello"


def test_get_content_hash_matches_sha256_of_file_bytes(tmp_path):
    (tmp_path / "readme.md").write_text("# Hello")

    connector = LocalFilesystemConnector(tmp_path)
    document = connector.list_documents()[0]

    expected = hashlib.sha256(b"# Hello").hexdigest()
    assert connector.get_content_hash(document) == expected


def test_get_content_hash_changes_when_file_content_changes(tmp_path):
    path = tmp_path / "readme.md"
    path.write_text("version one")
    connector = LocalFilesystemConnector(tmp_path)
    document = connector.list_documents()[0]
    first_hash = connector.get_content_hash(document)

    path.write_text("version two")
    second_hash = connector.get_content_hash(document)

    assert first_hash != second_hash
