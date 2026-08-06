from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from opentelemetry import trace

from app.connectors.filesystem import LocalFilesystemConnector
from app.ingestion.chunker import DEFAULT_CHUNK_SIZE_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_document
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.ingestion.qdrant_store import QdrantStore
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseVector
from app.shared.slug import slugify
from app.shared.tracing import get_tracer

# nomic-embed-text requires a task instruction prefix on the embedded text;
# "search_document: " is the indexing-side prefix (query side uses
# "search_query: ", applied at retrieval time in app/retrieval).
SEARCH_DOCUMENT_PREFIX = "search_document: "

EmbedFn = Callable[[str], Awaitable[list[float]]]


class SparseEncoderProtocol(Protocol):
    def embed_document(self, text: str) -> SparseVector: ...


@dataclass
class IngestStats:
    files_processed: int
    chunks_upserted: int


async def ingest_path(
    path: str,
    store: QdrantStore,
    embed_fn: EmbedFn,
    sparse_encoder: SparseEncoderProtocol,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    batch_size: int = 64,
    tracer: trace.Tracer | None = None,
) -> IngestStats:
    tracer = tracer or get_tracer(__name__)
    store.ensure_collection()

    files_processed = 0
    chunks_upserted = 0

    for pdf_path in sorted(Path(path).glob("*.pdf")):
        source_id = slugify(pdf_path.name)

        with tracer.start_as_current_span("ingest_document") as doc_span:
            doc_span.set_attribute("ingest.source_filename", pdf_path.name)
            doc_span.set_attribute("ingest.source_type", "pdf")
            doc_span.set_attribute("ingest.source_id", source_id)

            with tracer.start_as_current_span("parse_and_chunk") as span:
                chunks = chunk_document(
                    str(pdf_path), source_id, "pdf", chunk_size_tokens, overlap_tokens
                )
                span.set_attribute("parse.chunk_count", len(chunks))

            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start : batch_start + batch_size]

                with tracer.start_as_current_span("embed_batch") as span:
                    span.set_attribute("embed.chunk_count", len(batch))
                    dense_vectors = [await embed_fn(chunk.text) for chunk in batch]
                    sparse_vectors = [sparse_encoder.embed_document(chunk.text) for chunk in batch]

                with tracer.start_as_current_span("upsert_batch") as span:
                    span.set_attribute("upsert.chunk_count", len(batch))
                    store.upsert_chunks(batch, dense_vectors, sparse_vectors)

                chunks_upserted += len(batch)

            doc_span.set_attribute("ingest.chunk_count", len(chunks))

        files_processed += 1

    return IngestStats(files_processed=files_processed, chunks_upserted=chunks_upserted)


async def ingest_connector(
    connector: LocalFilesystemConnector,
    store: QdrantStore,
    registry: DocumentRegistry,
    embed_fn: EmbedFn,
    sparse_encoder: SparseEncoderProtocol,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    batch_size: int = 64,
    tracer: trace.Tracer | None = None,
) -> IngestStats:
    """Connector-driven, multi-format ingestion — the Sprint 3 entry point
    (ingest_path above is Sprint 0's PDF-only, folder-glob entry point,
    unchanged and still valid for pure-PDF folders).

    No incremental sync yet (Sprint 4): every call re-scans and re-ingests
    every document the connector lists, even if its content_hash hasn't
    changed. registry.upsert_document is still called for each one, so
    DocumentRegistry.has_changed already answers correctly — ingest_connector
    just doesn't act on that answer yet.

    Typed against LocalFilesystemConnector specifically, not the generic
    Connector Protocol — see docs/sprint-03-plan.md: generalizing this
    dispatch (currently keyed on document.path) is deferred until Sprint 6
    adds a second, real connector to design it against.
    """
    tracer = tracer or get_tracer(__name__)
    store.ensure_collection()

    files_processed = 0
    chunks_upserted = 0

    for document in connector.list_documents():
        content_hash = connector.get_content_hash(document)

        with tracer.start_as_current_span("ingest_document") as doc_span:
            doc_span.set_attribute("ingest.source_type", connector.source_type)
            doc_span.set_attribute("ingest.source_id", document.source_id)
            doc_span.set_attribute("ingest.content_type", document.content_type)

            with tracer.start_as_current_span("parse_and_chunk") as span:
                if document.content_type == "pdf":
                    chunks = chunk_document(
                        str(document.path),
                        document.source_id,
                        connector.source_type,
                        chunk_size_tokens,
                        overlap_tokens,
                        doc_id=content_hash,
                    )
                elif document.content_type == "markdown":
                    chunks = chunk_markdown_document(
                        str(document.path),
                        document.source_id,
                        connector.source_type,
                        chunk_size_tokens,
                        overlap_tokens,
                        doc_id=content_hash,
                    )
                else:
                    raise ValueError(f"Unsupported content_type: {document.content_type!r}")
                span.set_attribute("parse.chunk_count", len(chunks))

            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start : batch_start + batch_size]

                with tracer.start_as_current_span("embed_batch") as span:
                    span.set_attribute("embed.chunk_count", len(batch))
                    dense_vectors = [await embed_fn(chunk.text) for chunk in batch]
                    sparse_vectors = [sparse_encoder.embed_document(chunk.text) for chunk in batch]

                with tracer.start_as_current_span("upsert_batch") as span:
                    span.set_attribute("upsert.chunk_count", len(batch))
                    store.upsert_chunks(batch, dense_vectors, sparse_vectors)

                chunks_upserted += len(batch)

            doc_span.set_attribute("ingest.chunk_count", len(chunks))

        # Registered only after a successful chunk+upsert, so a failure
        # partway through doesn't leave the registry claiming a document
        # was ingested when it wasn't.
        registry.upsert_document(connector.source_type, document.source_id, content_hash)
        files_processed += 1

    return IngestStats(files_processed=files_processed, chunks_upserted=chunks_upserted)
