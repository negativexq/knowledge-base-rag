import shutil
from pathlib import Path

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

COLLECTION = "test_ingest_connector"


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _store() -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)


def _registry(tmp_path) -> DocumentRegistry:
    return DocumentRegistry(tmp_path / "registry.db")


async def _fake_embed(text: str) -> list[float]:
    return [float(len(text) % 97)] * EMBEDDING_DIM


class _FakeSparseEncoder:
    def embed_document(self, text: str) -> SparseVector:
        words = {w.lower() for w in text.split()}
        indices = sorted({hash(w) % 5000 for w in words})
        return SparseVector(indices=indices, values=[1.0] * len(indices))


def _make_docs_dir(tmp_path, sample_pdf) -> str:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "handbook.pdf")
    (docs_dir / "readme.md").write_text("# Kurulum\n\nInstall steps go here.")
    return str(docs_dir)


@pytest.mark.asyncio
async def test_ingest_connector_processes_both_pdf_and_markdown(sample_pdf, tmp_path):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    stats = await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    assert stats.files_processed == 2
    assert stats.chunks_upserted > 0
    assert store.count() == stats.chunks_upserted


@pytest.mark.asyncio
async def test_ingest_connector_tags_every_chunk_with_the_connectors_source_type(
    sample_pdf, tmp_path
):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    scroll_result, _ = store._client.scroll(COLLECTION, limit=100)
    assert scroll_result
    assert all(point.payload["source_type"] == "filesystem" for point in scroll_result)


@pytest.mark.asyncio
async def test_ingest_connector_markdown_chunks_carry_heading_path_pdf_chunks_do_not(
    sample_pdf, tmp_path
):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    scroll_result, _ = store._client.scroll(COLLECTION, limit=100)
    pdf_points = [p for p in scroll_result if p.payload["source_id"] == "handbook_pdf"]
    md_points = [p for p in scroll_result if p.payload["source_id"] == "readme_md"]

    assert pdf_points and md_points
    assert all(p.payload["heading_path"] == [] for p in pdf_points)
    assert all(p.payload["heading_path"] == ["Kurulum"] for p in md_points)


@pytest.mark.asyncio
async def test_ingest_connector_registers_both_documents_with_correct_source_type(
    sample_pdf, tmp_path
):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    pdf_record = registry.get_document("filesystem", "handbook_pdf")
    md_record = registry.get_document("filesystem", "readme_md")

    assert pdf_record is not None
    assert md_record is not None
    assert pdf_record.source_type == "filesystem"
    assert md_record.source_type == "filesystem"
    assert pdf_record.version == 1
    assert md_record.version == 1


@pytest.mark.asyncio
async def test_ingest_connector_registry_hash_matches_connector_hash(sample_pdf, tmp_path):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())

    for document in await connector.list_documents():
        record = registry.get_document(connector.source_type, document.source_id)
        assert record.content_hash == await connector.get_content_hash(document)


@pytest.mark.asyncio
async def test_ingest_connector_rerun_bumps_registry_version_only_when_content_changes(
    sample_pdf, tmp_path
):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)

    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    first_version = registry.get_document("filesystem", "readme_md").version

    # unchanged re-run — ingest_connector skips it entirely (Sprint 4), so
    # this also proves the skip path doesn't touch the registry version
    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    second_version = registry.get_document("filesystem", "readme_md").version

    assert second_version == first_version

    (Path(docs_dir) / "readme.md").write_text("# Kurulum\n\nUpdated install steps.")
    await ingest_connector(connector, store, registry, _fake_embed, _FakeSparseEncoder())
    third_version = registry.get_document("filesystem", "readme_md").version

    assert third_version == first_version + 1


@pytest.mark.asyncio
async def test_ingest_connector_creates_spans_with_content_type_attribute(sample_pdf, tmp_path):
    docs_dir = _make_docs_dir(tmp_path, sample_pdf)
    connector = LocalFilesystemConnector(docs_dir)
    store = _store()
    registry = _registry(tmp_path)
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_connector(
        connector, store, registry, _fake_embed, _FakeSparseEncoder(), tracer=tracer
    )

    doc_spans = [s for s in exporter.get_finished_spans() if s.name == "ingest_document"]
    content_types = {s.attributes["ingest.content_type"] for s in doc_spans}
    assert content_types == {"pdf", "markdown"}
    assert all(s.attributes["ingest.source_type"] == "filesystem" for s in doc_spans)
