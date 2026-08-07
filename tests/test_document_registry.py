"""Tests run against a real SQLite file (tmp_path), not sqlite3's ":memory:"
mode — same caution as Sprint 0's Qdrant lesson (":memory:" silently
dropped query_filter on prefetch+fusion queries that a real server honored).
A couple of tests below specifically open a SECOND connection to the same
file to prove data actually persisted to disk, which ":memory:" cannot
demonstrate.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.registry.store import (
    CURRENT_INDEX_SCHEMA_VERSION,
    DocumentRegistry,
    IndexSchemaMismatchError,
)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


def test_upsert_document_creates_a_new_record_at_version_1(tmp_path):
    registry = _registry(tmp_path)

    record = registry.upsert_document("pdf", "handbook", "hash-a")

    assert record.source_type == "pdf"
    assert record.source_id == "handbook"
    assert record.content_hash == "hash-a"
    assert record.version == 1
    assert record.status == "active"


def test_upsert_document_with_unchanged_hash_does_not_bump_version(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    second = registry.upsert_document("pdf", "handbook", "hash-a")

    assert second.version == 1


def test_upsert_document_with_changed_hash_bumps_version(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    updated = registry.upsert_document("pdf", "handbook", "hash-b")

    assert updated.content_hash == "hash-b"
    assert updated.version == 2


def test_upsert_document_refreshes_last_synced_at_even_when_hash_unchanged(tmp_path):
    registry = _registry(tmp_path)
    first = registry.upsert_document("pdf", "handbook", "hash-a")

    second = registry.upsert_document("pdf", "handbook", "hash-a")

    assert second.last_synced_at >= first.last_synced_at


def test_upsert_document_accepts_a_custom_status(tmp_path):
    registry = _registry(tmp_path)

    record = registry.upsert_document("pdf", "handbook", "hash-a", status="error")

    assert record.status == "error"


def test_get_document_returns_none_when_not_registered(tmp_path):
    registry = _registry(tmp_path)

    assert registry.get_document("pdf", "missing") is None


def test_get_document_returns_the_stored_record(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    record = registry.get_document("pdf", "handbook")

    assert record is not None
    assert record.content_hash == "hash-a"


def test_delete_document_removes_the_record(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    registry.delete_document("pdf", "handbook")

    assert registry.get_document("pdf", "handbook") is None


def test_delete_document_on_unregistered_document_is_a_no_op(tmp_path):
    registry = _registry(tmp_path)

    registry.delete_document("pdf", "never-existed")  # must not raise


def test_has_changed_is_true_for_a_never_registered_document(tmp_path):
    registry = _registry(tmp_path)

    assert registry.has_changed("pdf", "handbook", "hash-a") is True


def test_has_changed_is_false_when_hash_matches_the_registered_one(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    assert registry.has_changed("pdf", "handbook", "hash-a") is False


def test_has_changed_is_true_when_hash_differs_from_the_registered_one(tmp_path):
    """The concrete DoD proof: register a document, then detect that its
    hash changed.
    """
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "handbook", "hash-a")

    assert registry.has_changed("pdf", "handbook", "hash-b") is True


def test_two_documents_with_same_source_id_but_different_source_type_are_distinct(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "readme", "hash-pdf")
    registry.upsert_document("markdown", "readme", "hash-markdown")

    pdf_doc = registry.get_document("pdf", "readme")
    md_doc = registry.get_document("markdown", "readme")

    assert pdf_doc.content_hash == "hash-pdf"
    assert md_doc.content_hash == "hash-markdown"


def test_list_documents_returns_all_registered_documents(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "a", "hash-a")
    registry.upsert_document("pdf", "b", "hash-b")
    registry.upsert_document("markdown", "c", "hash-c")

    records = registry.list_documents()

    assert {(r.source_type, r.source_id) for r in records} == {
        ("pdf", "a"),
        ("pdf", "b"),
        ("markdown", "c"),
    }


def test_list_documents_filters_by_source_type(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("pdf", "a", "hash-a")
    registry.upsert_document("markdown", "c", "hash-c")

    records = registry.list_documents(source_type="pdf")

    assert [(r.source_type, r.source_id) for r in records] == [("pdf", "a")]


def test_data_persists_to_the_real_file_across_separate_connections(tmp_path):
    db_path = tmp_path / "registry.db"
    first_connection = DocumentRegistry(db_path)
    first_connection.upsert_document("pdf", "handbook", "hash-a")
    first_connection.close()

    second_connection = DocumentRegistry(db_path)
    record = second_connection.get_document("pdf", "handbook")

    assert record is not None
    assert record.content_hash == "hash-a"


def test_schema_creates_documents_table_with_expected_columns(tmp_path):
    db_path = tmp_path / "registry.db"
    DocumentRegistry(db_path)  # creates the schema as a side effect

    raw_conn = sqlite3.connect(str(db_path))
    columns = {row[1] for row in raw_conn.execute("PRAGMA table_info(documents)").fetchall()}
    raw_conn.close()

    assert columns == {
        "source_type",
        "source_id",
        "content_hash",
        "last_synced_at",
        "version",
        "status",
    }


def test_last_synced_at_is_a_real_datetime_with_timezone(tmp_path):
    registry = _registry(tmp_path)
    before = datetime.now(UTC) - timedelta(seconds=1)

    record = registry.upsert_document("pdf", "handbook", "hash-a")

    assert isinstance(record.last_synced_at, datetime)
    assert record.last_synced_at.tzinfo is not None
    assert record.last_synced_at >= before


def test_a_fresh_empty_registry_self_stamps_the_current_schema_version(tmp_path):
    """Sprint 17.1: a genuinely fresh install (no documents yet) has
    nothing to migrate — ensure_index_schema_version() adopts the
    current version automatically, no operator action needed beyond
    whatever brought up a fresh registry.db in the first place.
    """
    registry = _registry(tmp_path)

    registry.ensure_index_schema_version()  # must not raise

    assert registry.get_index_schema_version() == CURRENT_INDEX_SCHEMA_VERSION


def test_a_registry_with_documents_but_no_version_row_is_detected_as_stale(tmp_path):
    """Sprint 17.1: the real scenario this migration guard exists for — a
    registry built before Sprint 17.1's version-tracking mechanism
    existed at all (so it has document rows, but never had a version
    row written) predates the Sprint 17 point-ID formula fix too, and
    must be treated as needing migration, not silently trusted.
    """
    registry = _registry(tmp_path)
    registry.upsert_document("filesystem", "handbook", "hash-a")

    with pytest.raises(IndexSchemaMismatchError):
        registry.ensure_index_schema_version()


def test_a_registry_with_an_explicit_stale_version_row_is_detected(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_document("filesystem", "handbook", "hash-a")
    registry._set_index_schema_version(CURRENT_INDEX_SCHEMA_VERSION - 1)

    with pytest.raises(IndexSchemaMismatchError):
        registry.ensure_index_schema_version()


def test_ensure_index_schema_version_is_idempotent_once_current(tmp_path):
    registry = _registry(tmp_path)
    registry.ensure_index_schema_version()

    registry.ensure_index_schema_version()  # must not raise the second time either

    assert registry.get_index_schema_version() == CURRENT_INDEX_SCHEMA_VERSION
