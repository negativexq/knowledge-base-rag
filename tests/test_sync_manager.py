import asyncio
import time

import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager, UnknownConnectorError
from app.sync.models import STATUS_ERROR, STATUS_REJECTED, STATUS_SUCCESS, TRIGGER_MANUAL

COLLECTION = "test_sync_manager"


class _CountingStore(QdrantStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upsert_calls = 0

    def upsert_chunks(self, *args, **kwargs):
        self.upsert_calls += 1
        return super().upsert_chunks(*args, **kwargs)


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def _fast_embed_fn():
    async def embed(text: str) -> list[float]:
        return [0.01] * EMBEDDING_DIM

    return embed


def _slow_embed_fn(delay: float):
    async def embed(text: str) -> list[float]:
        await asyncio.sleep(delay)
        return [0.01] * EMBEDDING_DIM

    return embed


def _make_manager(tmp_path, embed_fn, docs_dir) -> tuple[SyncManager, _CountingStore, SyncHistory]:
    connector = LocalFilesystemConnector(docs_dir)
    store = _CountingStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    manager = SyncManager(
        connectors={"filesystem": connector},
        store=store,
        registry=registry,
        history=history,
        embed_fn=embed_fn,
        sparse_encoder=_FakeSparseEncoder(),
    )
    return manager, store, history


@pytest.mark.asyncio
async def test_trigger_sync_for_unknown_source_type_raises(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    manager, _, _ = _make_manager(tmp_path, _fast_embed_fn(), docs_dir)

    with pytest.raises(UnknownConnectorError):
        await manager.trigger_sync("notion", TRIGGER_MANUAL)


@pytest.mark.asyncio
async def test_trigger_sync_success_records_history_and_returns_stats(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")
    manager, store, history = _make_manager(tmp_path, _fast_embed_fn(), docs_dir)

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.status == STATUS_SUCCESS
    assert result.stats.files_processed == 1
    assert result.error is None

    run = history.get_run(result.run_id)
    assert run.status == STATUS_SUCCESS
    assert run.files_processed == 1
    assert run.trigger == TRIGGER_MANUAL


@pytest.mark.asyncio
async def test_trigger_sync_error_records_history_with_message(tmp_path):
    docs_dir = tmp_path / "this-does-not-exist"  # connector will fail to list it
    manager, _, history = _make_manager(tmp_path, _fast_embed_fn(), docs_dir)

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.status == STATUS_ERROR
    assert result.error is not None

    run = history.get_run(result.run_id)
    assert run.status == STATUS_ERROR
    assert run.error_message is not None


@pytest.mark.asyncio
async def test_is_running_reflects_current_state(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")
    manager, _, _ = _make_manager(tmp_path, _slow_embed_fn(0.1), docs_dir)

    assert manager.is_running("filesystem") is False
    task = asyncio.create_task(manager.trigger_sync("filesystem", TRIGGER_MANUAL))
    await asyncio.sleep(0.02)  # let it start and pass the first await point

    assert manager.is_running("filesystem") is True
    await task
    assert manager.is_running("filesystem") is False


@pytest.mark.asyncio
async def test_concurrent_sync_of_the_same_connector_rejects_the_second_attempt(tmp_path):
    """The real race-condition proof: two trigger_sync() calls for the SAME
    connector, launched genuinely concurrently via asyncio.gather, with the
    embed step artificially slowed so there's a real window for a race. Only
    one may actually perform the ingest; the other must be rejected
    immediately, not queued behind it.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")
    delay = 0.2
    manager, store, _ = _make_manager(tmp_path, _slow_embed_fn(delay), docs_dir)

    start = time.monotonic()
    first, second = await asyncio.gather(
        manager.trigger_sync("filesystem", TRIGGER_MANUAL),
        manager.trigger_sync("filesystem", TRIGGER_MANUAL),
    )
    elapsed = time.monotonic() - start

    statuses = {first.status, second.status}
    assert statuses == {STATUS_SUCCESS, STATUS_REJECTED}
    assert store.upsert_calls == 1  # only the successful run actually wrote anything

    # If the rejected call had instead queued/waited for the first to
    # finish and then run for real, this would take ~2x delay. It doesn't.
    assert elapsed < delay * 1.5


@pytest.mark.asyncio
async def test_concurrent_sync_of_different_connectors_both_run(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")

    fs_connector = LocalFilesystemConnector(docs_dir)
    store = _CountingStore(client=QdrantClient(":memory:"), collection_name=COLLECTION + "2")
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")

    class _OtherFsConnector(LocalFilesystemConnector):
        source_type = "other-filesystem"

    other_docs = tmp_path / "other-docs"
    other_docs.mkdir()
    (other_docs / "b.md").write_text("# B\n\nOther content.")

    manager = SyncManager(
        connectors={"filesystem": fs_connector, "other-filesystem": _OtherFsConnector(other_docs)},
        store=store,
        registry=registry,
        history=history,
        embed_fn=_slow_embed_fn(0.1),
        sparse_encoder=_FakeSparseEncoder(),
    )

    results = await asyncio.gather(
        manager.trigger_sync("filesystem", TRIGGER_MANUAL),
        manager.trigger_sync("other-filesystem", TRIGGER_MANUAL),
    )

    assert {r.status for r in results} == {STATUS_SUCCESS}
