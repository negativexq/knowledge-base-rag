"""Sprint 4 DoD: three real, end-to-end sync scenarios against a real
folder, a real Qdrant (:memory:) collection, and a real SQLite registry
file — no mocking of the sync logic itself. Only Ollama embedding is faked
(deterministic, no network/model download).
"""

import sqlite3

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.fingerprint import PipelineFingerprint
from app.ingestion.ingest import ingest_connector
from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import CURRENT_INDEX_SCHEMA_VERSION, DocumentRegistry
from app.retrieval.sparse import SparseVector

COLLECTION = "test_sync_scenarios"


class _CountingStore(QdrantStore):
    """Wraps the real QdrantStore, counting write calls — proof that a
    no-op sync issues literally zero write requests, not just that the
    end state happens to look unchanged.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upsert_calls = 0
        self.delete_calls = 0

    def upsert_chunks(self, *args, **kwargs):
        self.upsert_calls += 1
        return super().upsert_chunks(*args, **kwargs)

    def delete_by_source(self, *args, **kwargs):
        self.delete_calls += 1
        return super().delete_by_source(*args, **kwargs)


async def _fake_embed(text: str) -> list[float]:
    vector = [0.01] * EMBEDDING_DIM
    vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
    return vector


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def _store() -> _CountingStore:
    return _CountingStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


def _all_points(store: QdrantStore):
    points, _ = store._client.scroll(COLLECTION, limit=1000)
    return points


@pytest.mark.asyncio
async def test_updating_one_file_only_changes_that_files_chunks(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nOriginal content about apples.")
    (docs_dir / "b.md").write_text("# B\n\nUnrelated content about bicycles.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    b_points_before = {
        p.id: p.payload for p in _all_points(store) if p.payload["source_id"] == "b_md"
    }
    assert b_points_before  # sanity: B was actually ingested

    (docs_dir / "a.md").write_text("# A\n\nCompletely rewritten content about oranges.")
    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    all_points = _all_points(store)
    a_points = [p for p in all_points if p.payload["source_id"] == "a_md"]
    b_points_after = {p.id: p.payload for p in all_points if p.payload["source_id"] == "b_md"}

    assert any("oranges" in p.payload["text"] for p in a_points)
    assert not any("apples" in p.payload["text"] for p in a_points)
    # B's points are byte-for-byte the same points — untouched, not just
    # "still present": same IDs, same payload.
    assert b_points_after == b_points_before


@pytest.mark.asyncio
async def test_deleting_a_file_leaves_zero_orphan_chunks(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent about apples.")
    (docs_dir / "b.md").write_text("# B\n\nContent about bicycles.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert store.count() > 0

    (docs_dir / "a.md").unlink()
    stats = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert stats.files_deleted == 1
    all_points = _all_points(store)
    assert not any(p.payload["source_id"] == "a_md" for p in all_points)
    assert any(p.payload["source_id"] == "b_md" for p in all_points)
    assert registry.get_document("filesystem", "a_md") is None
    assert registry.get_document("filesystem", "b_md") is not None


@pytest.mark.asyncio
async def test_noop_sync_issues_zero_qdrant_write_calls(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent about apples.")
    (docs_dir / "b.md").write_text("# B\n\nContent about bicycles.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    first = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert first.files_processed == 2
    assert store.upsert_calls > 0  # sanity: the first run really did write

    store.upsert_calls = 0
    store.delete_calls = 0

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert second.files_skipped == 2
    assert second.files_processed == 0
    assert store.upsert_calls == 0
    assert store.delete_calls == 0


@pytest.mark.asyncio
async def test_shrinking_a_document_leaves_no_orphan_chunks(tmp_path):
    """A document that goes from many chunks to one must not leave the
    extra old chunks behind in Qdrant — the concrete proof for the
    orphan-chunk open question resolved in docs/sprint-04-plan.md.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sentences = [f"Sentence number {i} has several words in it." for i in range(30)]
    (docs_dir / "long.md").write_text("# Long\n\n" + " ".join(sentences))

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5,
    )
    long_points_before = [p for p in _all_points(store) if p.payload["source_id"] == "long_md"]
    assert len(long_points_before) > 1  # sanity: it really did split into multiple chunks

    (docs_dir / "long.md").write_text("# Long\n\nJust one short sentence now.")
    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5,
    )

    long_points_after = [p for p in _all_points(store) if p.payload["source_id"] == "long_md"]
    assert len(long_points_after) == 1
    assert "short sentence" in long_points_after[0].payload["text"]


@pytest.mark.asyncio
async def test_sync_creates_delete_document_spans_for_removed_files(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    (docs_dir / "a.md").unlink()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    delete_spans = [s for s in exporter.get_finished_spans() if s.name == "delete_document"]
    assert len(delete_spans) == 1
    assert delete_spans[0].attributes["delete.source_id"] == "a_md"


@pytest.mark.asyncio
async def test_manually_deleting_qdrant_points_triggers_automatic_reindex_on_next_sync(tmp_path):
    """Sprint 17.2, the review's exact scenario: the registry and Qdrant
    are two separate persistent stores that can silently drift apart.
    Ingest a document for real, then delete its Qdrant points directly
    (store.delete_by_source — simulating data loss by any means OTHER
    than this app's own writes: manual deletion, external tooling, a
    lost volume) WITHOUT touching the registry at all, so content_hash
    stays identical. Before this fix, `registry.has_changed()` alone
    decided the skip — content unchanged meant skip forever, even with
    zero points actually in Qdrant. Now the document must be detected as
    missing from the index and automatically re-ingested.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nOriginal content, never edited again.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    first = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert first.files_processed == 1
    assert store.count() > 0
    hash_before = registry.get_document("filesystem", "a_md").content_hash

    # Simulate external data loss — NOT this app's own delete path, and
    # the registry is never touched.
    store.delete_by_source("filesystem", "a_md")
    assert store.count() == 0

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    # The document must NOT have been silently skipped — it was
    # re-processed even though its content_hash never changed.
    assert second.files_processed == 1
    assert second.files_skipped == 0
    assert store.count() > 0

    # Content is genuinely unchanged, so the registry's hash is the same
    # as before — this proves the trigger was the missing index, not a
    # content edit.
    assert registry.get_document("filesystem", "a_md").content_hash == hash_before


@pytest.mark.asyncio
async def test_intact_index_is_still_skipped_not_needlessly_reindexed(tmp_path):
    """The other half of the reconciliation logic: an unchanged document
    whose index IS still intact must still be skipped — reconciliation
    must not turn every sync into a full re-index.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert second.files_processed == 0
    assert second.files_skipped == 1


@pytest.mark.asyncio
async def test_partial_qdrant_point_loss_is_detected_and_triggers_reindex(tmp_path):
    """Sprint 17.2 bonus: a presence-only check (has_document_version)
    can't tell "some points missing" apart from "all points present" —
    both report at least one point exists. chunk_count tracking lets a
    partial loss be detected too: delete only SOME of a multi-chunk
    document's points (registry untouched, chunk_count still says the
    original total), and the next sync must notice the mismatch and
    restore the full chunk count.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sentences = [f"Sentence number {i} about a topic that never changes." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(sentences))

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    first = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5,
    )
    assert first.files_processed == 1
    original_chunk_count = registry.get_document("filesystem", "doc_md").chunk_count
    assert original_chunk_count >= 3  # sanity: really did split into several chunks

    all_points = _all_points(store)
    doc_points = [p for p in all_points if p.payload["source_id"] == "doc_md"]
    assert len(doc_points) == original_chunk_count

    # Delete only ONE point, not the whole document — a partial loss,
    # not a total one.
    store._client.delete(COLLECTION, points_selector=[doc_points[0].id])
    remaining = [
        p for p in _all_points(store) if p.payload["source_id"] == "doc_md"
    ]
    assert len(remaining) == original_chunk_count - 1  # confirmed: genuinely partial

    second = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5,
    )

    assert second.files_processed == 1  # re-indexed, not skipped
    assert second.files_skipped == 0

    restored = [
        p for p in _all_points(store) if p.payload["source_id"] == "doc_md"
    ]
    assert len(restored) == original_chunk_count  # full chunk count restored


@pytest.mark.asyncio
async def test_extra_same_version_point_is_cleaned_up_and_the_loop_actually_stops(tmp_path):
    """Sprint 17.3, the critical fix: delete_stale_versions only removes
    points with a DIFFERENT document_version — an unexpected extra point
    sharing the CURRENT version (the exact "harmless duplicate" Sprint
    17.2 disclosed) is invisible to it. Left uncleaned, Sprint 17.2's
    own chunk_count reconciliation would see the count mismatch forever
    and re-ingest this document on every sync without the extra point
    ever going away — a real infinite loop. This proves BOTH halves:
    the extra point is cleaned up on the first sync after it appears,
    AND a second sync afterward is a genuine no-op (files_skipped==1),
    proving the loop actually terminates rather than just running one
    cleanup pass.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    content_hash = registry.get_document("filesystem", "doc_md").content_hash

    # Simulate exactly the Sprint 17.2-disclosed edge case: a duplicate
    # point sharing the SAME document_version but a different point ID
    # (a different char_range makes point_id_for produce a distinct ID).
    duplicate_chunk = Chunk(
        doc_id=content_hash,
        source_type="filesystem",
        source_id="doc_md",
        page_number=0,
        paragraph_index=0,
        char_range=(99999, 99999),
        text="stale leftover text",
        document_version=content_hash,
    )
    store.upsert_chunks(
        [duplicate_chunk], [[0.01] * EMBEDDING_DIM], [SparseVector(indices=[], values=[])]
    )

    ids_with_duplicate = store.list_point_ids_for_version("filesystem", "doc_md", content_hash)
    assert QdrantStore.point_id_for(duplicate_chunk) in ids_with_duplicate  # sanity: really added

    # First sync after the duplicate appears: cleaned up.
    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert second.files_processed == 1

    ids_after_cleanup = store.list_point_ids_for_version("filesystem", "doc_md", content_hash)
    assert QdrantStore.point_id_for(duplicate_chunk) not in ids_after_cleanup

    # Second sync: the loop must actually terminate here, not repeat.
    third = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert third.files_processed == 0
    assert third.files_skipped == 1


@pytest.mark.asyncio
async def test_qdrant_only_orphan_is_cleaned_up_even_when_the_registry_never_knew_about_it(
    tmp_path,
):
    """Sprint 17.3, the review's exact scenario: two documents ingested
    for real. Then a GENUINELY FRESH, disconnected registry instance is
    used for the next sync — not a DELETE FROM documents on the same
    registry, a separate DocumentRegistry pointed at a different db
    file entirely, simulating "the registry was reset/replaced, Qdrant
    was not touched." One of the two files is removed from the
    connector's folder before that sync runs. The removed document's
    Qdrant points must be cleaned up even though this fresh registry
    never had a row for EITHER document to begin with.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent for document A.")
    (docs_dir / "b.md").write_text("# B\n\nContent for document B.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    original_registry = _registry(tmp_path)

    await ingest_connector(connector, store, original_registry, _fake_embed, _FakeSparseEncoder())
    assert store.count() == 2  # sanity: both documents really landed

    # Remove one file from the connector's view, and use a FRESH registry
    # that has never seen either document — not the same registry with
    # its rows deleted.
    (docs_dir / "a.md").unlink()
    fresh_registry = DocumentRegistry(tmp_path / "a_completely_different_registry.db")
    assert fresh_registry.get_document("filesystem", "a_md") is None  # sanity: genuinely unknown
    assert fresh_registry.get_document("filesystem", "b_md") is None

    result = await ingest_connector(
        connector, store, fresh_registry, _fake_embed, _FakeSparseEncoder()
    )

    # "a" is gone from Qdrant even though the fresh registry never had a
    # row for it to trigger the registry-known deletion path.
    remaining = _all_points(store)
    remaining_source_ids = {p.payload["source_id"] for p in remaining}
    assert "a_md" not in remaining_source_ids
    assert "b_md" in remaining_source_ids  # "b" is still there — re-ingested as "new"
    assert result.files_deleted >= 1


@pytest.mark.asyncio
async def test_a_genuinely_empty_document_does_not_loop_forever(tmp_path):
    """Sprint 17.3, item 5/6: a genuinely empty (whitespace-only)
    Markdown file produces exactly 0 chunks. Before this fix,
    chunk_count=0 was ambiguous — it could mean "never tracked" or
    "genuinely zero" — and the reconciliation logic's `if
    expected_chunk_count > 0:` gate treated a real 0 the same as
    "unknown," falling back to presence-only checking
    (has_document_version), which can NEVER return True for a document
    with zero real points. A genuinely empty document could therefore
    never be recognized as correctly, completely indexed — every sync
    would treat it as needing re-ingest, forever.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "empty.md").write_text("   \n\n  ")  # whitespace-only -> 0 chunks

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    first = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert first.files_processed == 1
    record = registry.get_document("filesystem", "empty_md")
    assert record.chunk_count == 0  # genuinely zero, now distinguishable from "unknown"

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert second.files_processed == 0  # NOT reprocessed — the loop must not happen
    assert second.files_skipped == 1


@pytest.mark.asyncio
async def test_untracked_chunk_count_is_promoted_after_one_forced_reindex(tmp_path):
    """Sprint 17.4: before this fix, `expected_chunk_count is None` fell
    back to `actual_chunk_count > 0` — a document with an untracked
    chunk_count that happened to have real, intact Qdrant points was
    treated as "complete" and SKIPPED, which means
    registry.upsert_document(...) (the only call site that ever writes
    a real chunk_count) was never reached. chunk_count could therefore
    stay None forever, and partial loss could never be caught for that
    document via the count-comparison logic. The fix forces exactly ONE
    re-ingest for an untracked document, which writes a real count —
    after that, normal reconciliation applies.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    record = registry.get_document("filesystem", "doc_md")
    assert record.chunk_count is not None and record.chunk_count > 0  # sanity

    # Simulate an untracked row (e.g. migrated from a pre-chunk_count
    # registry) — real Qdrant points still fully intact, only the
    # registry's own tracking is missing.
    with registry._conn:
        registry._conn.execute(
            "UPDATE documents SET chunk_count = NULL WHERE source_type = 'filesystem' "
            "AND source_id = 'doc_md'"
        )
    assert registry.get_document("filesystem", "doc_md").chunk_count is None  # sanity

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert second.files_processed == 1  # forced re-ingest, not skipped
    assert second.files_skipped == 0
    promoted = registry.get_document("filesystem", "doc_md")
    assert promoted.chunk_count is not None and promoted.chunk_count > 0  # now tracked

    third = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    assert third.files_processed == 0  # now genuinely skipped, tracking took hold
    assert third.files_skipped == 1


@pytest.mark.asyncio
async def test_real_sprint_17_2_upgrade_with_existing_qdrant_data_ends_up_tracked(tmp_path):
    """Sprint 17.4, the combined end-to-end scenario: a document was
    ingested for real under an ordinary registry (real content_hash,
    real Qdrant points). Its registry row is then rewritten via raw SQL
    against a table built with the ACTUAL Sprint 17.2 schema (chunk_count
    INTEGER NOT NULL DEFAULT 0) to carry the SAME content_hash but
    chunk_count=0 — simulating "this row was written back when Sprint
    17.2 was live," where 0 is ambiguous (Sprint 17.4 item 1 converts it
    to NULL on migration). A fresh DocumentRegistry opened against that
    file must (a) migrate the column to genuinely nullable, (b) turn
    that ambiguous 0 into NULL, and then, combined with item 2's fix,
    (c) force exactly one re-ingest (content unchanged, but chunk_count
    untracked) before settling into normal skip behavior — proving both
    fixes resolve the real upgrade path together, not just in isolation.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    original_registry = _registry(tmp_path)

    await ingest_connector(connector, store, original_registry, _fake_embed, _FakeSparseEncoder())
    original_record = original_registry.get_document("filesystem", "doc_md")
    real_content_hash = original_record.content_hash
    points_before = [p for p in _all_points(store) if p.payload["source_id"] == "doc_md"]
    assert len(points_before) > 0  # sanity: real points genuinely exist

    # Rebuild the registry file from scratch using the REAL Sprint 17.2
    # schema, carrying the SAME content_hash but the ambiguous legacy
    # chunk_count=0.
    migrated_db_path = tmp_path / "migrated_from_17_2.db"
    raw_conn = sqlite3.connect(str(migrated_db_path))
    raw_conn.execute(
        """
        CREATE TABLE documents (
            source_type    TEXT    NOT NULL,
            source_id      TEXT    NOT NULL,
            content_hash   TEXT    NOT NULL,
            last_synced_at TEXT    NOT NULL,
            version        INTEGER NOT NULL,
            status         TEXT    NOT NULL,
            chunk_count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (source_type, source_id)
        );
        """
    )
    raw_conn.execute(
        "INSERT INTO documents (source_type, source_id, content_hash, last_synced_at, "
        "version, status, chunk_count) VALUES "
        "('filesystem', 'doc_md', ?, '2020-01-01T00:00:00+00:00', 1, 'active', 0)",
        (real_content_hash,),
    )
    raw_conn.commit()
    raw_conn.close()

    migrated_registry = DocumentRegistry(migrated_db_path)  # must migrate on open
    assert migrated_registry.get_document("filesystem", "doc_md").chunk_count is None

    first = await ingest_connector(
        connector, store, migrated_registry, _fake_embed, _FakeSparseEncoder()
    )
    assert first.files_processed == 1  # forced re-ingest — chunk_count was untracked
    assert first.files_skipped == 0
    after_first = migrated_registry.get_document("filesystem", "doc_md")
    assert after_first.chunk_count is not None and after_first.chunk_count > 0

    second = await ingest_connector(
        connector, store, migrated_registry, _fake_embed, _FakeSparseEncoder()
    )
    assert second.files_processed == 0  # genuine no-op now
    assert second.files_skipped == 1


@pytest.mark.asyncio
async def test_pipeline_fingerprint_mismatch_forces_reindex_even_with_unchanged_content(
    tmp_path,
):
    """Sprint 18: content_hash and chunk_count staying identical is not
    enough once the EMBEDDING MODEL a document was indexed under changes
    — the vectors in Qdrant are for a completely different model, but
    nothing about the document's own content changed, so content_hash
    comparison alone would trust them forever. Passing a
    pipeline_fingerprint into ingest_connector adds exactly the
    reconciliation dimension chunk_count already established for partial
    point loss (Sprint 17.2) — a stored fingerprint that doesn't match
    the CURRENT one is treated the same as an incomplete index.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    fingerprint_v1 = PipelineFingerprint(
        embedding_model="nomic-embed-text",
        embedding_revision="latest",
        embedding_dimension=768,
        query_instruction="search_query: ",
        document_instruction="search_document: ",
        index_schema_version=CURRENT_INDEX_SCHEMA_VERSION,
    )
    first = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        pipeline_fingerprint=fingerprint_v1,
    )
    assert first.files_processed == 1
    assert registry.get_document("filesystem", "a_md").pipeline_fingerprint == (
        fingerprint_v1.digest()
    )

    # Content is UNCHANGED — only the embedding model (a different name,
    # standing in for e.g. swapping to Qwen3-Embedding-4B) changed.
    fingerprint_v2 = PipelineFingerprint(
        embedding_model="qwen3-embedding:4b",
        embedding_revision="latest",
        embedding_dimension=2560,
        query_instruction="Instruct: x\nQuery: ",
        document_instruction="",
        index_schema_version=CURRENT_INDEX_SCHEMA_VERSION,
    )
    second = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        pipeline_fingerprint=fingerprint_v2,
    )

    assert second.files_processed == 1  # forced re-index, NOT skipped
    assert second.files_skipped == 0
    assert registry.get_document("filesystem", "a_md").pipeline_fingerprint == (
        fingerprint_v2.digest()
    )


@pytest.mark.asyncio
async def test_pipeline_fingerprint_match_is_skipped_normally(tmp_path):
    """The other half: an unchanged document with a MATCHING fingerprint
    must still be skipped — passing a fingerprint must not turn every
    sync into a full re-index.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    fingerprint = PipelineFingerprint(
        embedding_model="nomic-embed-text",
        embedding_revision="latest",
        embedding_dimension=768,
        query_instruction="search_query: ",
        document_instruction="search_document: ",
        index_schema_version=CURRENT_INDEX_SCHEMA_VERSION,
    )
    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        pipeline_fingerprint=fingerprint,
    )

    second = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        pipeline_fingerprint=fingerprint,
    )

    assert second.files_processed == 0
    assert second.files_skipped == 1


@pytest.mark.asyncio
async def test_omitting_pipeline_fingerprint_keeps_existing_behavior_unchanged(tmp_path):
    """Backward compatibility: every existing caller (SyncManager, all
    prior sprints' tests) never passes pipeline_fingerprint — the default
    None must skip this check entirely, not treat "no fingerprint given"
    as a mismatch.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\nContent that never changes.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    second = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert second.files_processed == 0
    assert second.files_skipped == 1
