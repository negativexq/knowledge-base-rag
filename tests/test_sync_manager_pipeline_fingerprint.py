"""Sprint 22 correctness patch: SyncManager must pass the currently
active pipeline fingerprint into every production ingest_connector()
call — closing the gap where a content-hash-unchanged document indexed
under a stale (pre-migration) embedding model could be skipped forever
even though its vectors no longer match the now-active pipeline.

All four scenarios go through SyncManager.trigger_sync() (the real
production entry point), never by calling ingest_connector() directly —
that's the point of this patch: prove the fingerprint actually threads
through the real orchestration path, not just that ingest_connector's
own (already-tested, Sprint 18) fingerprint-reconciliation logic works
in isolation.
"""

import pytest
from qdrant_client import QdrantClient

from app.ingestion.fingerprint import PipelineFingerprint
from app.ingestion.qdrant_store import QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager
from app.sync.models import TRIGGER_MANUAL

COLLECTION = "test_sync_manager_pipeline_fingerprint"
DIMENSION = 1024

QWEN_FINGERPRINT = PipelineFingerprint(
    embedding_model="qwen3-embedding:4b",
    embedding_revision="latest",
    embedding_dimension=DIMENSION,
    query_instruction="Instruct: ...\nQuery: ",
    document_instruction="",
    index_schema_version=3,
    embedding_backend="ollama",
)

NOMIC_FINGERPRINT = PipelineFingerprint(
    embedding_model="nomic-embed-text",
    embedding_revision="latest",
    embedding_dimension=768,
    query_instruction="search_query: ",
    document_instruction="search_document: ",
    index_schema_version=3,
    embedding_backend="ollama",
)


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


class _RecordingStore(QdrantStore):
    """Records every dense vector length ever upserted — the concrete
    proof that a SyncManager wired for qwen3-4b@1024 can never write a
    768-dim (nomic) vector into the collection it owns.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upsert_calls = 0
        self.upserted_vector_dims: set[int] = set()

    def upsert_chunks(self, chunks, dense_vectors, sparse_vectors):
        self.upsert_calls += 1
        self.upserted_vector_dims.update(len(v) for v in dense_vectors)
        return super().upsert_chunks(chunks, dense_vectors, sparse_vectors)


def _qwen_embed_fn():
    async def embed(text: str) -> list[float]:
        vector = [0.01] * DIMENSION
        vector[hash(text.lower()[:20]) % DIMENSION] = 1.0
        return vector

    return embed


_ManagerBundle = tuple[SyncManager, _RecordingStore, DocumentRegistry]


def _make_manager(
    tmp_path, docs_dir, pipeline_fingerprint, store: _RecordingStore | None = None,
    registry: DocumentRegistry | None = None,
) -> _ManagerBundle:
    """store/registry are optional so a test can build a SECOND manager
    that shares the exact same physical Qdrant collection and registry
    file as a first one — the realistic shape of "the active pipeline
    fingerprint changed" (a migration activated), as opposed to two
    entirely separate collections.
    """
    from app.connectors.filesystem import LocalFilesystemConnector

    connector = LocalFilesystemConnector(str(docs_dir))
    if store is None:
        client = QdrantClient(":memory:")
        store = _RecordingStore(
            client=client, collection_name=COLLECTION, dense_dimension=DIMENSION
        )
    if registry is None:
        registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    manager = SyncManager(
        connectors={"filesystem": connector},
        store=store,
        registry=registry,
        history=history,
        embed_fn=_qwen_embed_fn(),
        sparse_encoder=_FakeSparseEncoder(),
        pipeline_fingerprint=pipeline_fingerprint,
    )
    return manager, store, registry


@pytest.mark.asyncio
async def test_new_document_is_indexed_and_registry_stores_the_active_fingerprint(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.")
    manager, store, registry = _make_manager(tmp_path, docs_dir, QWEN_FINGERPRINT)

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.stats.files_processed == 1
    record = registry.get_document("filesystem", "one_md")
    assert record.pipeline_fingerprint == QWEN_FINGERPRINT.digest()
    assert store.upserted_vector_dims == {DIMENSION}


@pytest.mark.asyncio
async def test_changed_document_is_reindexed_and_fingerprint_is_preserved(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_path = docs_dir / "one.md"
    doc_path.write_text("# One\n\nContent about apples.")
    manager, store, registry = _make_manager(tmp_path, docs_dir, QWEN_FINGERPRINT)
    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    doc_path.write_text("# One\n\nCompletely different content about oranges.")
    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.stats.files_processed == 1  # re-indexed, not skipped
    record = registry.get_document("filesystem", "one_md")
    assert record.pipeline_fingerprint == QWEN_FINGERPRINT.digest()
    assert store.upserted_vector_dims == {DIMENSION}


@pytest.mark.asyncio
async def test_unchanged_document_with_matching_fingerprint_is_skipped(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.")
    manager, store, registry = _make_manager(tmp_path, docs_dir, QWEN_FINGERPRINT)
    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)
    calls_after_first_sync = store.upsert_calls

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.stats.files_processed == 0
    assert result.stats.files_skipped == 1
    assert store.upsert_calls == calls_after_first_sync  # no re-embed, no re-upsert


@pytest.mark.asyncio
async def test_unchanged_content_with_a_stale_fingerprint_is_treated_as_stale_and_reindexed(
    tmp_path,
):
    """Simulates a migration having changed the active pipeline: the
    document's content never changed, but a SECOND SyncManager, sharing
    the exact SAME physical collection and registry file as the first,
    is now configured with a DIFFERENT (post-migration) fingerprint than
    what's recorded for that document. A content-hash-only check would
    wrongly skip this forever; the fingerprint check must force a real
    re-index.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.")
    old_manager, store, registry = _make_manager(tmp_path, docs_dir, NOMIC_FINGERPRINT)
    await old_manager.trigger_sync("filesystem", TRIGGER_MANUAL)
    record_before = registry.get_document("filesystem", "one_md")
    assert record_before.pipeline_fingerprint == NOMIC_FINGERPRINT.digest()
    calls_after_nomic_sync = store.upsert_calls

    new_manager, _, _ = _make_manager(
        tmp_path, docs_dir, QWEN_FINGERPRINT, store=store, registry=registry
    )
    result = await new_manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.stats.files_processed == 1  # NOT skipped, despite unchanged content
    assert store.upsert_calls > calls_after_nomic_sync
    record_after = registry.get_document("filesystem", "one_md")
    assert record_after.pipeline_fingerprint == QWEN_FINGERPRINT.digest()


@pytest.mark.asyncio
async def test_syncmanager_never_writes_a_mixed_dimension_vector(tmp_path):
    """Structural proof that no nomic (768-dim) vector can enter a
    collection a qwen3-4b@1024-configured SyncManager owns — the
    embed_fn/store/fingerprint are all wired from ONE source of truth at
    construction time (app/wiring.py), so every write this manager makes
    is at the same dimension, across multiple documents and syncs.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "one.md").write_text("# One\n\nContent about apples.")
    (docs_dir / "two.md").write_text("# Two\n\nContent about oranges.")
    manager, store, _ = _make_manager(tmp_path, docs_dir, QWEN_FINGERPRINT)

    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)
    (docs_dir / "three.md").write_text("# Three\n\nContent about pears.")
    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert store.upserted_vector_dims == {DIMENSION}
