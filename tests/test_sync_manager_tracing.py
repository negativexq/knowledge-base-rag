
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager
from app.sync.models import STATUS_ERROR, STATUS_REJECTED, STATUS_SUCCESS, TRIGGER_MANUAL


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


async def _fake_embed(text: str) -> list[float]:
    return [0.01] * EMBEDDING_DIM


def _manager(tmp_path, docs_dir, tracer, collection="test_sync_manager_tracing") -> SyncManager:
    connector = LocalFilesystemConnector(docs_dir)
    store = QdrantStore(client=QdrantClient(":memory:"), collection_name=collection)
    registry = DocumentRegistry(tmp_path / "registry.db")
    history = SyncHistory(tmp_path / "registry.db")
    return SyncManager(
        connectors={"filesystem": connector},
        store=store,
        registry=registry,
        history=history,
        embed_fn=_fake_embed,
        sparse_encoder=_FakeSparseEncoder(),
        tracer=tracer,
    ), history


@pytest.mark.asyncio
async def test_successful_sync_run_shares_one_trace_with_ingest_connector_spans(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    tracer, exporter = _local_tracer_with_exporter()
    manager, history = _manager(tmp_path, docs_dir, tracer)

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    spans = exporter.get_finished_spans()
    trace_ids = {s.context.trace_id for s in spans}
    assert len(trace_ids) == 1
    span_names = {s.name for s in spans}
    assert {"sync_run", "ingest_connector", "fetch_documents"} <= span_names

    sync_run_span = next(s for s in spans if s.name == "sync_run")
    expected_trace_id = format(sync_run_span.context.trace_id, "032x")
    assert result.trace_id == expected_trace_id

    run = history.get_run(result.run_id)
    assert run.trace_id == expected_trace_id


@pytest.mark.asyncio
async def test_sync_run_span_records_final_status_attribute(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    tracer, exporter = _local_tracer_with_exporter()
    manager, _ = _manager(tmp_path, docs_dir, tracer)

    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    sync_run_span = next(s for s in exporter.get_finished_spans() if s.name == "sync_run")
    assert sync_run_span.attributes["sync.status"] == STATUS_SUCCESS
    assert sync_run_span.attributes["sync.source_type"] == "filesystem"
    assert sync_run_span.attributes["sync.trigger"] == TRIGGER_MANUAL


@pytest.mark.asyncio
async def test_rejected_sync_still_produces_a_span_with_a_trace_id(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    tracer, exporter = _local_tracer_with_exporter()
    manager, history = _manager(tmp_path, docs_dir, tracer)

    manager._running["filesystem"] = True  # simulate an in-flight sync
    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.status == STATUS_REJECTED
    assert result.trace_id is not None
    assert result.run_id is None  # rejected before a history row was ever started

    sync_run_spans = [s for s in exporter.get_finished_spans() if s.name == "sync_run"]
    assert len(sync_run_spans) == 1
    assert sync_run_spans[0].attributes["sync.status"] == STATUS_REJECTED
    # a rejected attempt never reaches ingest_connector at all
    assert not any(s.name == "ingest_connector" for s in exporter.get_finished_spans())
    assert history.list_runs(source_type="filesystem") == []


@pytest.mark.asyncio
async def test_error_sync_records_status_and_trace_id_in_history(tmp_path):
    docs_dir = tmp_path / "this-does-not-exist"
    tracer, exporter = _local_tracer_with_exporter()
    manager, history = _manager(tmp_path, docs_dir, tracer)

    result = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert result.status == STATUS_ERROR
    sync_run_span = next(s for s in exporter.get_finished_spans() if s.name == "sync_run")
    assert sync_run_span.attributes["sync.status"] == STATUS_ERROR

    run = history.get_run(result.run_id)
    assert run.status == STATUS_ERROR
    assert run.trace_id == format(sync_run_span.context.trace_id, "032x")


@pytest.mark.asyncio
async def test_two_separate_sync_runs_get_two_separate_trace_ids(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    tracer, exporter = _local_tracer_with_exporter()
    manager, _ = _manager(tmp_path, docs_dir, tracer)

    first = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)
    (docs_dir / "a.md").write_text("# A\n\nchanged text")
    second = await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    assert first.trace_id != second.trace_id


@pytest.mark.asyncio
async def test_no_span_attribute_leaks_full_document_text(tmp_path):
    secret = "CONFIDENTIAL " + ("lorem ipsum dolor sit amet " * 20)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\n" + secret)
    tracer, exporter = _local_tracer_with_exporter()
    manager, _ = _manager(tmp_path, docs_dir, tracer)

    await manager.trigger_sync("filesystem", TRIGGER_MANUAL)

    for span in exporter.get_finished_spans():
        for value in span.attributes.values():
            assert "CONFIDENTIAL" not in str(value)
