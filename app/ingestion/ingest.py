from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from opentelemetry import trace

from app.connectors.base import Connector
from app.ingestion.chunker import DEFAULT_CHUNK_SIZE_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_document
from app.ingestion.markdown_chunker import chunk_markdown_document, chunk_markdown_text
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
    files_skipped: int = 0
    files_deleted: int = 0


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
    connector: Connector,
    store: QdrantStore,
    registry: DocumentRegistry,
    embed_fn: EmbedFn,
    sparse_encoder: SparseEncoderProtocol,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    batch_size: int = 64,
    tracer: trace.Tracer | None = None,
) -> IngestStats:
    """Connector-driven, multi-format, INCREMENTAL ingestion — the Sprint 4
    upgrade of Sprint 3's ingest_connector (ingest_path above is Sprint 0's
    PDF-only, folder-glob, registry-less entry point; still unchanged).

    Three-phase sync, using registry as the source of truth for "what did
    we already know":

    1. Deletions — a registry row for this connector's source_type whose
       source_id the connector no longer lists means the document vanished
       from its source. Its Qdrant points and registry row are removed.
    2. Unchanged — registry.has_changed() says no: skipped entirely, zero
       Qdrant calls (no re-parse, re-embed, or re-upsert), and the registry
       row is left untouched too (no last_synced_at refresh — see
       docs/sprint-04-plan.md for why that's an accepted simplification).
    3. New/changed — re-embedded and re-upserted under a NEW
       document_version (the new content_hash) FIRST; only once every
       batch is confirmed upserted are the OLD version's points deleted,
       keyed on (source_type, source_id, document_version) — see
       docs/sprint-13-plan.md for why this deferred-cleanup ordering
       replaced Sprint 4's delete-then-reingest (a failure mid-embed used
       to leave the document unsearchable; now the old version stays
       searchable until the new one is confirmed written, at the cost of
       a brief window where both versions are simultaneously visible).
       Keying on (source_type, source_id) rather than the old content-hash
       doc_id alone is still what guarantees no orphans even if the chunk
       count shrank (Sprint 4). Safe to call on a brand new document too
       (deletes zero points).

    Typed against the generic Connector Protocol — Sprint 3/4 kept this
    typed to LocalFilesystemConnector specifically ("generalize once a
    second connector proves what's needed"); Sprint 6's NotionConnector is
    that second connector, and requires two real changes here: content
    with no local path (content_type == "notion" fetches bytes over the
    network via connector.fetch_content() instead of reading document.path),
    and awaiting the connector's now-async methods (see
    docs/sprint-06-plan.md for why the Protocol itself had to become async).

    Sprint 8: the whole call is wrapped in one "ingest_connector" span so
    every document's work (fetch/parse/embed/upsert/cleanup, and even
    skipped documents) shares a single trace_id — before this, each
    "ingest_document"/"delete_document" span had no parent and became its
    own separate, unrelated trace. See docs/sprint-08-plan.md for the two
    other blind spots fixed alongside it: connector I/O (list_documents,
    get_content_hash, Notion's fetch_content) wasn't spanned at all, and
    skipped documents produced zero trace evidence they were even checked.
    """
    tracer = tracer or get_tracer(__name__)

    with tracer.start_as_current_span("ingest_connector") as sync_span:
        sync_span.set_attribute("ingest.source_type", connector.source_type)
        store.ensure_collection()

        files_processed = 0
        chunks_upserted = 0
        files_skipped = 0
        files_deleted = 0

        with tracer.start_as_current_span("fetch_documents") as span:
            current_documents = await connector.list_documents()
            span.set_attribute("fetch.document_count", len(current_documents))
        seen_source_ids = {document.source_id for document in current_documents}

        for record in registry.list_documents(source_type=connector.source_type):
            if record.source_id in seen_source_ids:
                continue

            with tracer.start_as_current_span("delete_document") as span:
                span.set_attribute("delete.source_type", connector.source_type)
                span.set_attribute("delete.source_id", record.source_id)
                store.delete_by_source(connector.source_type, record.source_id)
                registry.delete_document(connector.source_type, record.source_id)
            files_deleted += 1

        for document in current_documents:
            with tracer.start_as_current_span("check_document") as check_span:
                check_span.set_attribute("check.source_type", connector.source_type)
                check_span.set_attribute("check.source_id", document.source_id)
                content_hash = await connector.get_content_hash(document)
                changed = registry.has_changed(
                    connector.source_type, document.source_id, content_hash
                )
                check_span.set_attribute("check.changed", changed)

            if not changed:
                files_skipped += 1
                continue

            with tracer.start_as_current_span("ingest_document") as doc_span:
                doc_span.set_attribute("ingest.source_type", connector.source_type)
                doc_span.set_attribute("ingest.source_id", document.source_id)
                doc_span.set_attribute("ingest.content_type", document.content_type)

                if document.content_type == "notion":
                    with tracer.start_as_current_span("fetch") as span:
                        span.set_attribute("fetch.source_id", document.source_id)
                        content_bytes = await connector.fetch_content(document)

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
                    elif document.content_type == "notion":
                        chunks = chunk_markdown_text(
                            content_bytes.decode("utf-8"),
                            document.source_id,
                            connector.source_type,
                            content_hash,
                            chunk_size_tokens,
                            overlap_tokens,
                        )
                    else:
                        raise ValueError(f"Unsupported content_type: {document.content_type!r}")
                    span.set_attribute("parse.chunk_count", len(chunks))

                # Zero-downtime versioned re-index with DEFERRED cleanup
                # (Sprint 13) — NOT strict atomic. The new version's
                # chunks (tagged document_version=content_hash) are fully
                # embedded and upserted FIRST; the old version's chunks
                # are only deleted once that succeeds, so a failure
                # partway through embedding/upserting leaves the OLD
                # version still searchable instead of the document
                # going dark (Sprint 4's delete-first ordering could do
                # that). The real, disclosed tradeoff: between the last
                # upsert_batch below and delete_stale_chunks, BOTH
                # versions are simultaneously searchable — see
                # docs/sprint-13-plan.md and the README's re-index
                # section for the measured window and why it isn't
                # eliminated here.
                for batch_start in range(0, len(chunks), batch_size):
                    batch = chunks[batch_start : batch_start + batch_size]

                    with tracer.start_as_current_span("embed_batch") as span:
                        span.set_attribute("embed.chunk_count", len(batch))
                        dense_vectors = [await embed_fn(chunk.text) for chunk in batch]
                        sparse_vectors = [
                            sparse_encoder.embed_document(chunk.text) for chunk in batch
                        ]

                    with tracer.start_as_current_span("upsert_batch") as span:
                        span.set_attribute("upsert.chunk_count", len(batch))
                        store.upsert_chunks(batch, dense_vectors, sparse_vectors)

                    chunks_upserted += len(batch)

                doc_span.set_attribute("ingest.chunk_count", len(chunks))

                with tracer.start_as_current_span("delete_stale_chunks") as span:
                    span.set_attribute("delete_stale_chunks.source_id", document.source_id)
                    span.set_attribute("delete_stale_chunks.keep_version", content_hash)
                    store.delete_stale_versions(
                        connector.source_type, document.source_id, keep_version=content_hash
                    )

            # Registered only after a successful chunk+upsert, so a failure
            # partway through doesn't leave the registry claiming a document
            # was ingested when it wasn't.
            registry.upsert_document(connector.source_type, document.source_id, content_hash)
            files_processed += 1

        sync_span.set_attribute("ingest.files_processed", files_processed)
        sync_span.set_attribute("ingest.files_skipped", files_skipped)
        sync_span.set_attribute("ingest.files_deleted", files_deleted)
        sync_span.set_attribute("ingest.chunks_upserted", chunks_upserted)

        return IngestStats(
            files_processed=files_processed,
            chunks_upserted=chunks_upserted,
            files_skipped=files_skipped,
            files_deleted=files_deleted,
        )
