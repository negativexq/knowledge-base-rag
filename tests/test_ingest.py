import shutil

import fitz
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from app.ingestion.chunker import chunk_document
from app.ingestion.ingest import ingest_path
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.retrieval.sparse import SparseVector


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter

COLLECTION = "test_ingest"


def _store() -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"), collection_name=COLLECTION)


async def _fake_embed(text: str) -> list[float]:
    # deterministic, cheap stand-in for a real Ollama call
    return [float(len(text) % 97)] * EMBEDDING_DIM


class _FakeSparseEncoder:
    """Deterministic, hermetic stand-in for SparseEncoder (no model download)."""

    def embed_document(self, text: str) -> SparseVector:
        return SparseVector(indices=[hash(text) % 1000], values=[1.0])


def _make_other_pdf(path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 150), "OTHERDOC-PARA0 some different content here.")
    doc.save(path)
    doc.close()


@pytest.mark.asyncio
async def test_ingest_path_upserts_one_point_per_chunk(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")

    expected_chunks = chunk_document(
        sample_pdf, source_id="sample", chunk_size_tokens=20, overlap_tokens=5
    )
    store = _store()

    stats = await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )

    assert stats.files_processed == 1
    assert stats.chunks_upserted == len(expected_chunks)
    assert store.count() == len(expected_chunks)


@pytest.mark.asyncio
async def test_ingest_path_assigns_source_type_and_slugified_source_id(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    store = _store()

    await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )

    scroll_result, _ = store._client.scroll(COLLECTION, limit=1)
    point = scroll_result[0]
    assert point.payload["source_type"] == "pdf"
    assert point.payload["source_id"] == "sample"


@pytest.mark.asyncio
async def test_ingest_path_is_idempotent_on_repeat_run(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    store = _store()

    first = await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )
    second = await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )

    assert first.chunks_upserted == second.chunks_upserted
    assert store.count() == first.chunks_upserted


@pytest.mark.asyncio
async def test_ingest_path_processes_all_pdfs_in_folder(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    _make_other_pdf(docs_dir / "other.pdf")

    store = _store()
    stats = await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )

    assert stats.files_processed == 2
    assert store.count() == stats.chunks_upserted


@pytest.mark.asyncio
async def test_ingest_path_writes_sparse_vectors_alongside_dense(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    store = _store()

    await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
    )

    scroll_result, _ = store._client.scroll(COLLECTION, limit=1, with_vectors=True)
    point = scroll_result[0]
    assert "sparse" in point.vector
    assert len(point.vector["sparse"].indices) > 0


@pytest.mark.asyncio
async def test_ingest_path_creates_spans_for_each_pipeline_stage(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    store = _store()
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
        tracer=tracer,
    )

    span_names = {span.name for span in exporter.get_finished_spans()}
    assert "ingest_document" in span_names
    assert "parse_and_chunk" in span_names
    assert "embed_batch" in span_names
    assert "upsert_batch" in span_names

    spans_by_name = {span.name: span for span in exporter.get_finished_spans()}
    assert spans_by_name["ingest_document"].attributes["ingest.source_filename"] == "sample.pdf"
    assert spans_by_name["ingest_document"].attributes["ingest.source_type"] == "pdf"
    assert spans_by_name["ingest_document"].attributes["ingest.source_id"] == "sample"
    assert spans_by_name["parse_and_chunk"].attributes["parse.chunk_count"] > 0
    assert "embed.chunk_count" in spans_by_name["embed_batch"].attributes


@pytest.mark.asyncio
async def test_ingest_path_spans_do_not_contain_chunk_text(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")
    store = _store()
    tracer, exporter = _local_tracer_with_exporter()

    await ingest_path(
        str(docs_dir),
        store,
        _fake_embed,
        _FakeSparseEncoder(),
        chunk_size_tokens=20,
        overlap_tokens=5,
        tracer=tracer,
    )

    for span in exporter.get_finished_spans():
        for value in span.attributes.values():
            assert "PAGE1-PARA0" not in str(value)
