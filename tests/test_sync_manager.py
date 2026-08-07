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
from app.sync.models import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_REJECTED,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    TRIGGER_MANUAL,
)

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


def _make_manager(
    tmp_path, embed_fn, docs_dir, embedding_concurrency=None
) -> tuple[SyncManager, _CountingStore, SyncHistory]:
    connector = LocalFilesystemConnector(docs_dir)
    store = _CountingStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    kwargs = {}
    if embedding_concurrency is not None:
        kwargs["embedding_concurrency"] = embedding_concurrency
    manager = SyncManager(
        connectors={"filesystem": connector},
        store=store,
        registry=registry,
        history=history,
        embed_fn=embed_fn,
        sparse_encoder=_FakeSparseEncoder(),
        **kwargs,
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
async def test_a_real_cancellation_records_cancelled_status_not_stuck_running(tmp_path):
    """Sprint 17: before this, trigger_sync's `except Exception as exc:`
    never caught asyncio.CancelledError (BaseException, not Exception),
    so a cancelled run's sync_runs row was left forever at STATUS_RUNNING
    — indistinguishable from a process that silently crashed mid-sync.
    Cancels a REAL asyncio Task wrapping trigger_sync (task.cancel() from
    outside, not a manually-raised CancelledError) while it's genuinely
    in-flight.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# A\n\nSome content.")
    manager, _, history = _make_manager(tmp_path, _slow_embed_fn(1.0), docs_dir)

    task = asyncio.create_task(manager.trigger_sync("filesystem", TRIGGER_MANUAL))
    await asyncio.sleep(0.02)  # let it start and pass the first await point
    assert manager.is_running("filesystem") is True

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager.is_running("filesystem") is False  # finally: always runs

    run = history.latest_run("filesystem")
    assert run is not None
    assert run.status == STATUS_CANCELLED
    assert run.status != STATUS_RUNNING


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


@pytest.mark.asyncio
async def test_embedding_concurrency_is_threaded_through_to_ingest_connector(tmp_path):
    """SyncManager's embedding_concurrency isn't just stored — it actually
    bounds how many embed_fn calls ingest_connector runs at once.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    # Enough real content to split into several chunks (default chunk size
    # is 500 tokens) — concurrency=3 can only be observed maxing out if
    # there are at least 3 chunks to embed concurrently.
    sentences = " ".join(f"Sentence {i} has several words in it." for i in range(200))
    (docs_dir / "doc.md").write_text(f"# Doc\n\n{sentences}")

    in_flight = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def tracking_embed(text: str) -> list[float]:
        nonlocal in_flight, max_concurrent
        async with lock:
            in_flight += 1
            max_concurrent = max(max_concurrent, in_flight)
        await asyncio.sleep(0.02)
        async with lock:
            in_flight -= 1
        return [0.01] * EMBEDDING_DIM

    manager, _, _ = _make_manager(tmp_path, tracking_embed, docs_dir, embedding_concurrency=3)

    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert max_concurrent == 3
