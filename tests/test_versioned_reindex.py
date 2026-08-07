"""Sprint 13: zero-downtime versioned re-index with deferred cleanup.
Real scenarios against a real folder, a real Qdrant (:memory:) collection,
and a real SQLite registry — proving both halves of the DoD: a failure
mid-embed leaves the OLD version searchable (the fix), and a successful
re-index has a real, measured window where both versions are visible
(the disclosed tradeoff). Only Ollama embedding is faked.
"""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector

COLLECTION = "test_versioned_reindex"


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


async def _fake_embed(text: str) -> list[float]:
    vector = [0.01] * EMBEDDING_DIM
    vector[hash(text.lower()[:20]) % EMBEDDING_DIM] = 1.0
    return vector


class SimulatedEmbedFailure(Exception):
    pass


def _store(name: str = COLLECTION) -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"), collection_name=name)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


def _all_points(store: QdrantStore, name: str = COLLECTION):
    points, _ = store._client.scroll(name, limit=1000)
    return points


async def test_embed_failure_mid_reindex_leaves_old_version_searchable(tmp_path):
    """The core DoD: contrast with Sprint 4's delete-first ordering, which
    would have already wiped the old chunks before this failure occurred.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sentences = [f"Original sentence number {i} about apples." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(sentences))

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5,
    )
    old_hash = registry.get_document("filesystem", "doc_md").content_hash
    old_points_before = [p for p in _all_points(store) if p.payload["source_id"] == "doc_md"]
    assert len(old_points_before) > 1  # sanity: really did split into multiple chunks

    new_sentences = [f"Completely rewritten sentence number {i} about oranges." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(new_sentences))

    call_count = 0

    async def flaky_embed(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        if call_count > 2:  # succeed for a couple of chunks, then fail mid-reindex
            raise SimulatedEmbedFailure("simulated network failure mid-embed")
        return await _fake_embed(text)

    try:
        await ingest_connector(
            connector, store, registry, flaky_embed, _FakeSparseEncoder(),
            chunk_size_tokens=15, overlap_tokens=5,
        )
        raise AssertionError("expected the simulated embed failure to propagate")
    except SimulatedEmbedFailure:
        pass

    # The OLD version's chunks are untouched — still present, still the
    # original text, still findable. Sprint 4's delete-first ordering
    # would have deleted these BEFORE the first embed call.
    points_after_failure = [p for p in _all_points(store) if p.payload["source_id"] == "doc_md"]
    old_ids = {p.id for p in old_points_before}
    surviving_old = [p for p in points_after_failure if p.id in old_ids]
    assert len(surviving_old) == len(old_points_before)
    assert any("apples" in p.payload["text"] for p in surviving_old)

    # Registry still points at the OLD hash — a retry will correctly see
    # this document as still "changed" and try again.
    assert registry.get_document("filesystem", "doc_md").content_hash == old_hash


async def test_multi_batch_partial_failure_rolls_back_the_partial_new_version(tmp_path):
    """The Sprint 16 fix: Sprint 13's guarantee ("a failure mid-embed
    leaves the OLD version fully intact") was only true within a single
    upsert batch. With upsert_batch_size small enough to force multiple
    batches, a failure in batch 2+ used to leave batch 1's NEW-version
    points sitting in Qdrant alongside the untouched OLD version —
    delete_stale_chunks never ran, so nothing cleaned them up. This test
    proves the rollback: after the failure, NO points anywhere carry the
    new document_version, not just "the old ones survived".
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sentences = [f"Original sentence number {i} about apples." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(sentences))

    connector = LocalFilesystemConnector(docs_dir)
    store = _store("test_versioned_reindex_rollback")
    registry = _registry(tmp_path)

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5, upsert_batch_size=2,
    )
    old_hash = registry.get_document("filesystem", "doc_md").content_hash
    old_points_before = [
        p for p in _all_points(store, "test_versioned_reindex_rollback")
        if p.payload["source_id"] == "doc_md"
    ]
    assert len(old_points_before) >= 6  # sanity: enough chunks for 3+ batches of 2

    new_sentences = [f"Completely rewritten sentence number {i} about oranges." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(new_sentences))

    call_count = 0

    async def flaky_embed(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        # Let batch 1 (2 chunks) succeed fully, then fail partway through
        # batch 2 — proving the rollback covers a batch that already
        # started, not just batches that never ran.
        if call_count > 3:
            raise SimulatedEmbedFailure("simulated network failure mid-batch-2")
        return await _fake_embed(text)

    try:
        await ingest_connector(
            connector, store, registry, flaky_embed, _FakeSparseEncoder(),
            chunk_size_tokens=15, overlap_tokens=5, upsert_batch_size=2,
        )
        raise AssertionError("expected the simulated embed failure to propagate")
    except SimulatedEmbedFailure:
        pass

    points_after_failure = [
        p for p in _all_points(store, "test_versioned_reindex_rollback")
        if p.payload["source_id"] == "doc_md"
    ]

    # The OLD version is fully intact — same guarantee as the single-batch
    # case above.
    old_ids = {p.id for p in old_points_before}
    surviving_old = [p for p in points_after_failure if p.id in old_ids]
    assert len(surviving_old) == len(old_points_before)
    assert any("apples" in p.payload["text"] for p in surviving_old)

    # The NEW twist this test exists for: batch 1's NEW-version points
    # (which DID get upserted before batch 2 failed) must have been
    # rolled back too — zero points anywhere carry the new hash.
    new_version_points = [
        p for p in points_after_failure if p.payload["document_version"] != old_hash
    ]
    assert new_version_points == []
    assert not any("oranges" in p.payload["text"] for p in points_after_failure)

    # Registry still points at the OLD hash — a retry will correctly see
    # this document as still "changed".
    assert registry.get_document("filesystem", "doc_md").content_hash == old_hash


async def test_successful_reindex_cleans_up_the_old_version(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nOriginal content about apples.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store("test_versioned_reindex_cleanup")
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    (docs_dir / "doc.md").write_text("# Doc\n\nRewritten content about oranges.")
    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    points = [p for p in _all_points(store, "test_versioned_reindex_cleanup")]
    doc_points = [p for p in points if p.payload["source_id"] == "doc_md"]
    assert len(doc_points) == 1  # old version's chunk was cleaned up
    assert "oranges" in doc_points[0].payload["text"]
    assert not any("apples" in p.payload["text"] for p in doc_points)


async def test_duplicate_visibility_window_really_exists_before_cleanup(tmp_path):
    """Proves the disclosed tradeoff is a real, observable intermediate
    state — not just a comment — by inspecting Qdrant's actual contents
    at the exact moment between the new version's upsert and the old
    version's deletion.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nOriginal content about apples.")

    connector = LocalFilesystemConnector(docs_dir)
    real_store = _store("test_versioned_reindex_window")
    registry = _registry(tmp_path)

    await ingest_connector(connector, real_store, registry, _fake_embed, _FakeSparseEncoder())

    (docs_dir / "doc.md").write_text("# Doc\n\nRewritten content about oranges.")

    observed = {}

    class _SnapshotStore(QdrantStore):
        def delete_stale_versions(self, source_type, source_id, keep_version):
            points = _all_points(self, "test_versioned_reindex_window")
            matching = [p for p in points if p.payload["source_id"] == source_id]
            observed["document_versions_present"] = {
                p.payload["document_version"] for p in matching
            }
            observed["texts_present"] = {p.payload["text"] for p in matching}
            return super().delete_stale_versions(source_type, source_id, keep_version)

    snapshot_store = _SnapshotStore(
        client=real_store._client, collection_name="test_versioned_reindex_window"
    )

    await ingest_connector(connector, snapshot_store, registry, _fake_embed, _FakeSparseEncoder())

    # At the moment delete_stale_versions was called, BOTH the old and the
    # new version's chunks were simultaneously present and searchable.
    assert len(observed["document_versions_present"]) == 2
    assert any("apples" in t for t in observed["texts_present"])
    assert any("oranges" in t for t in observed["texts_present"])


async def test_duplicate_visibility_window_duration_is_measured_via_real_spans(tmp_path):
    """Real OTel timestamps (nanosecond precision), not an estimate — the
    actual measured gap between the last upsert_batch span ending and
    delete_stale_chunks starting, for a real run.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc.md").write_text("# Doc\n\nOriginal content about apples.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store("test_versioned_reindex_timing")
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    (docs_dir / "doc.md").write_text("# Doc\n\nRewritten content about oranges.")

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    spans = exporter.get_finished_spans()
    upsert_spans = [s for s in spans if s.name == "upsert_batch"]
    delete_span = next(s for s in spans if s.name == "delete_stale_chunks")

    last_upsert_end = max(s.end_time for s in upsert_spans)
    window_ns = delete_span.start_time - last_upsert_end

    assert window_ns >= 0  # delete really does happen strictly after the last upsert
    # Recorded, not asserted tight — this is an observed real number, not
    # a guaranteed bound; see the Sprint 13 closing note for the actual
    # measured value from this run.
    print(f"\nduplicate-visibility window: {window_ns / 1000:.1f} microseconds")


async def test_multi_batch_duplicate_visibility_window_measured_from_first_upsert(tmp_path):
    """Sprint 16: the single-batch measurement above understates the real
    window for a multi-batch re-index. Once batch 1 is upserted, its
    NEW-version chunks are already searchable side by side with the
    (still fully intact) OLD version — and stay that way until
    delete_stale_chunks finally runs after the LAST batch. The real
    window is FIRST upsert_batch end -> delete_stale_chunks start, which
    only collapses to the single-batch number when there's exactly one
    batch. This measures it for a real multi-batch document instead.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sentences = [f"Original sentence number {i} about apples." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(sentences))

    connector = LocalFilesystemConnector(docs_dir)
    store = _store("test_versioned_reindex_multi_batch_timing")
    registry = _registry(tmp_path)

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5, upsert_batch_size=2,
    )

    new_sentences = [f"Completely rewritten sentence number {i} about oranges." for i in range(20)]
    (docs_dir / "doc.md").write_text("# Doc\n\n" + " ".join(new_sentences))

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(),
        chunk_size_tokens=15, overlap_tokens=5, upsert_batch_size=2, tracer=tracer,
    )

    spans = exporter.get_finished_spans()
    upsert_spans = [s for s in spans if s.name == "upsert_batch"]
    delete_span = next(s for s in spans if s.name == "delete_stale_chunks")

    assert len(upsert_spans) >= 3  # sanity: this really did run multiple batches

    first_upsert_end = min(s.end_time for s in upsert_spans)
    last_upsert_end = max(s.end_time for s in upsert_spans)
    window_from_first_ns = delete_span.start_time - first_upsert_end
    window_from_last_ns = delete_span.start_time - last_upsert_end

    assert window_from_first_ns >= window_from_last_ns >= 0
    print(
        f"\nmulti-batch duplicate-visibility window "
        f"(first upsert_batch -> cleanup): {window_from_first_ns / 1000:.1f} microseconds "
        f"across {len(upsert_spans)} batches "
        f"(last-batch-only measurement would have shown "
        f"{window_from_last_ns / 1000:.1f} microseconds)"
    )
