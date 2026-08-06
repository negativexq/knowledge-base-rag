"""Sprint 8: proves the three blind spots identified in
docs/sprint-08-plan.md are actually fixed — not just that spans exist, but
that they (1) share one trace_id end to end, (2) cover connector I/O
(fetch_documents, check_document, Notion's fetch) that was previously
invisible, and (3) make skipped documents show up in the trace instead of
disappearing silently. Also guards against high-cardinality data leaking
into span attributes (production-rag-platform's Sprint 8 lesson).
"""

import shutil

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector

COLLECTION = "test_ingest_connector_tracing"


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _store(name=COLLECTION) -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"), collection_name=name)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


async def _fake_embed(text: str) -> list[float]:
    return [float(len(text) % 97)] * EMBEDDING_DIM


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


LONG_SECRET_TEXT = "CONFIDENTIAL " + ("lorem ipsum dolor sit amet " * 20)


@pytest.mark.asyncio
async def test_a_full_sync_run_produces_exactly_one_trace(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\n" + LONG_SECRET_TEXT)
    (docs_dir / "b.md").write_text("# B\n\nSome other content.")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    spans = exporter.get_finished_spans()
    trace_ids = {s.context.trace_id for s in spans}
    assert len(trace_ids) == 1, "all spans from one sync run must share a single trace_id"
    span_names = {s.name for s in spans}
    assert {
        "ingest_connector",
        "fetch_documents",
        "check_document",
        "ingest_document",
        "parse_and_chunk",
        "delete_stale_chunks",
        "embed_batch",
        "upsert_batch",
    } <= span_names


@pytest.mark.asyncio
async def test_fetch_documents_span_reports_document_count(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    (docs_dir / "b.md").write_text("# B\n\ntext")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    fetch_span = next(s for s in exporter.get_finished_spans() if s.name == "fetch_documents")
    assert fetch_span.attributes["fetch.document_count"] == 2


@pytest.mark.asyncio
async def test_check_document_span_exists_even_for_skipped_documents(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    # first run: real ingest, no need to inspect spans
    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    # second run: nothing changed, so it's skipped — but must still be
    # visible in the trace as a checked-and-skipped document.
    tracer, exporter = _local_tracer_with_exporter()
    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    check_spans = [s for s in exporter.get_finished_spans() if s.name == "check_document"]
    assert len(check_spans) == 1
    assert check_spans[0].attributes["check.changed"] is False
    assert check_spans[0].attributes["check.source_id"] == "a_md"
    # and no ingest_document span was created for the skipped doc
    assert not any(s.name == "ingest_document" for s in exporter.get_finished_spans())


@pytest.mark.asyncio
async def test_check_document_span_reports_changed_true_for_a_new_document(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    check_span = next(s for s in exporter.get_finished_spans() if s.name == "check_document")
    assert check_span.attributes["check.changed"] is True


@pytest.mark.asyncio
async def test_top_level_span_reports_final_ingest_stats(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\ntext")
    (docs_dir / "b.md").write_text("# B\n\ntext")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    stats = await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    top_span = next(s for s in exporter.get_finished_spans() if s.name == "ingest_connector")
    assert top_span.attributes["ingest.source_type"] == "filesystem"
    assert top_span.attributes["ingest.files_processed"] == stats.files_processed
    assert top_span.attributes["ingest.files_skipped"] == stats.files_skipped
    assert top_span.attributes["ingest.files_deleted"] == stats.files_deleted
    assert top_span.attributes["ingest.chunks_upserted"] == stats.chunks_upserted


@pytest.mark.asyncio
async def test_notion_fetch_content_gets_its_own_fetch_span_separate_from_parsing(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/search":
            page = {
                "object": "page",
                "id": "page-1",
                "last_edited_time": "2024-01-01T00:00:00.000Z",
            }
            return httpx.Response(
                200, json={"object": "list", "has_more": False, "results": [page]}
            )

        heading_text = {"type": "text", "text": {"content": "A"}, "plain_text": "A"}
        paragraph_text = {
            "type": "text",
            "text": {"content": "notion text"},
            "plain_text": "notion text",
        }
        blocks = [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [heading_text]},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [paragraph_text]},
            },
        ]
        return httpx.Response(200, json={"object": "list", "has_more": False, "results": blocks})

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.notion.com/v1"
    )
    connector = NotionConnector(api_key="k", http_client=http_client)
    store = _store(COLLECTION + "_notion")
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    spans = exporter.get_finished_spans()
    fetch_spans = [s for s in spans if s.name == "fetch"]
    assert len(fetch_spans) == 1
    assert fetch_spans[0].attributes["fetch.source_id"] == "page-1"

    trace_ids = {s.context.trace_id for s in spans}
    assert len(trace_ids) == 1  # the fetch span is part of the same trace


@pytest.mark.asyncio
async def test_pdf_and_markdown_documents_do_not_get_a_fetch_span(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "handbook.pdf")
    (docs_dir / "readme.md").write_text("# A\n\ntext")

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    assert not any(s.name == "fetch" for s in exporter.get_finished_spans())


@pytest.mark.asyncio
async def test_no_span_attribute_contains_the_full_document_text(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# A\n\n" + LONG_SECRET_TEXT)

    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    for span in exporter.get_finished_spans():
        for value in span.attributes.values():
            assert "CONFIDENTIAL" not in str(value)
            assert "lorem ipsum" not in str(value)
