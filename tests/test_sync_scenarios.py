"""Sprint 4 DoD: three real, end-to-end sync scenarios against a real
folder, a real Qdrant (:memory:) collection, and a real SQLite registry
file — no mocking of the sync logic itself. Only Ollama embedding is faked
(deterministic, no network/model download).
"""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
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
