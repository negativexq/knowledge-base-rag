import asyncio
import logging
from collections import Counter
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

logger = logging.getLogger(__name__)

EmbedFn = Callable[[str], Awaitable[list[float]]]

# Chosen from a real benchmark against native Ollama (nomic-embed-text on
# an M2), not guessed (scripts/benchmark_embedding_concurrency.py; see
# docs/PLANNING.md Sprint 14 closing note and the README's throughput
# section for the full table). The real result was a plateau, not
# unbounded scaling: concurrency=1 -> ~30 chunks/sec, concurrency=2 ->
# ~74 (the big real jump), concurrency=4 -> ~74-87 (still slightly
# ahead, esp. at scale — 87.4 vs 80.9 chunks/sec at 1000 chunks),
# concurrency=8 -> ~79-88, i.e. NO further real gain over 4 (within
# measurement noise, sometimes lower at small chunk counts). 4 is the
# last point with a genuine marginal improvement — 8 just holds more
# connections open for zero measured benefit.
DEFAULT_EMBEDDING_CONCURRENCY = 4


class SparseEncoderProtocol(Protocol):
    def embed_document(self, text: str) -> SparseVector: ...


async def embed_texts_concurrently(
    texts: list[str], embed_fn: EmbedFn, concurrency: int
) -> list[list[float]]:
    """Embeds every text via embed_fn, at most `concurrency` calls in
    flight at once (asyncio.Semaphore), all launched together via
    asyncio.gather — which preserves input order in its results, so
    result[i] always corresponds to texts[i] regardless of which call
    actually finished first. A failing embed_fn call propagates (gather's
    default, not return_exceptions=True) — same "let it raise" behavior
    the previous sequential list comprehension had, which Sprint 13's
    deferred-cleanup re-index relies on to leave the old version intact.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(text: str) -> list[float]:
        async with semaphore:
            return await embed_fn(text)

    return list(await asyncio.gather(*(_bounded(text) for text in texts)))


class DuplicateSourceIdError(Exception):
    """Raised when a connector's list_documents() returns two or more
    documents sharing the same source_id — checked at ingest_connector's
    boundary, fail-fast before any document points or registry rows are
    written for the run (store.ensure_collection() may still have
    created an empty collection schema on a fresh Qdrant instance before
    this check runs — the guarantee is zero document DATA written, not
    that the collection object itself was never touched).
    slugify() collisions (e.g. "foo bar.md" and "foo_bar.md" both
    slugging to "foo_bar") are one real cause but not the only possible
    one — a connector could return duplicates for its own reasons — so
    this is a general connector-output check, not a slugify() fix. See
    docs/sprint-17-plan.md.
    """


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
    upsert_batch_size: int = 64,
    embedding_concurrency: int = DEFAULT_EMBEDDING_CONCURRENCY,
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

            for batch_start in range(0, len(chunks), upsert_batch_size):
                batch = chunks[batch_start : batch_start + upsert_batch_size]

                with tracer.start_as_current_span("embed_batch") as span:
                    span.set_attribute("embed.chunk_count", len(batch))
                    span.set_attribute("embed.concurrency", embedding_concurrency)
                    dense_vectors = await embed_texts_concurrently(
                        [chunk.text for chunk in batch], embed_fn, embedding_concurrency
                    )
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
    upsert_batch_size: int = 64,
    embedding_concurrency: int = DEFAULT_EMBEDDING_CONCURRENCY,
    tracer: trace.Tracer | None = None,
) -> IngestStats:
    """Connector-driven, multi-format, INCREMENTAL ingestion (ingest_path
    above is the PDF-only, folder-glob, registry-less entry point).

    Three-phase sync, using the registry as the source of truth for "what
    did we already know" — see
    docs/adr/0002-incremental-sync-three-phase-registry-diff.md for why
    this shape:

    1. Deletions — a registry row whose source_id the connector no longer
       lists means the document vanished from its source. Its Qdrant
       points and registry row are removed.
    2. Unchanged — registry.has_changed() says no: skipped, but NOT with
       zero Qdrant calls since Sprint 17.2 — a single
       count_for_document_version() reconciliation query confirms the
       document's points are actually still in Qdrant (and, if a
       chunk_count was tracked, that none are missing) before trusting
       the registry's hash alone; a mismatch is treated the same as
       "changed" and forces a real re-ingest (Sprint 17.3 closes the
       gap where a leftover duplicate point could make this loop
       forever — see docs/sprint-17-3-plan.md). Registry row left
       untouched when genuinely skipped (no last_synced_at refresh).
    3. New/changed — re-embedded and re-upserted under a NEW
       document_version (the new content_hash) FIRST; only once every
       batch is confirmed upserted are the OLD version's points deleted,
       keyed on (source_type, source_id, document_version) — see
       docs/adr/0003-deferred-cleanup-versioned-reindex.md. Keying on
       (source_type, source_id) rather than doc_id alone is what
       guarantees no orphans even if the chunk count shrank. Safe to call
       on a brand new document too (deletes zero points).

    Typed against the generic, async Connector Protocol — see
    docs/adr/0001-connector-interface-is-async.md. content_type ==
    "notion" fetches bytes over the network via connector.fetch_content()
    instead of reading document.path (no local path for that connector).

    The whole call is wrapped in one "ingest_connector" span so every
    document's work shares a single trace_id — see
    docs/adr/0004-single-trace-per-sync-run.md.
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

        if len(seen_source_ids) != len(current_documents):
            counts = Counter(document.source_id for document in current_documents)
            duplicates = sorted(source_id for source_id, count in counts.items() if count > 1)
            raise DuplicateSourceIdError(
                f"connector {connector.source_type!r} returned duplicate source_id(s): "
                f"{duplicates} — refusing to ingest, would silently interleave registry/Qdrant "
                "identity between the colliding documents"
            )

        # Sprint 17.3: union the registry's known source_ids with what's
        # ACTUALLY in Qdrant for this source_type — a registry-only scan
        # misses a document whose Qdrant points still exist but whose
        # registry row is gone entirely (a reset/lost/replaced registry
        # that never touched Qdrant; see docs/sprint-17-2-plan.md's
        # "registry fresh, Qdrant stale" analysis and
        # docs/sprint-17-3-plan.md). registry.delete_document() on a
        # source_id it never had is a safe no-op.
        registry_source_ids = {
            record.source_id
            for record in registry.list_documents(source_type=connector.source_type)
        }
        with tracer.start_as_current_span("fetch_qdrant_source_ids") as span:
            qdrant_source_ids = store.list_source_ids(connector.source_type)
            span.set_attribute("fetch.qdrant_source_id_count", len(qdrant_source_ids))
        known_source_ids = registry_source_ids | qdrant_source_ids

        for source_id in sorted(known_source_ids - seen_source_ids):
            with tracer.start_as_current_span("delete_document") as span:
                span.set_attribute("delete.source_type", connector.source_type)
                span.set_attribute("delete.source_id", source_id)
                store.delete_by_source(connector.source_type, source_id)
                registry.delete_document(connector.source_type, source_id)
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

                # Sprint 17.2: content_hash unchanged is necessary but no
                # longer sufficient to skip — the registry and Qdrant are
                # two separate persistent stores that can silently drift
                # apart (a manual point deletion, external tooling, lost
                # data — anything other than this app's own delete
                # calls). Only checked on the unchanged branch: a changed
                # document already pays for a full re-embed+upsert
                # regardless, so this adds no extra Qdrant call there.
                # See docs/sprint-17-2-plan.md.
                #
                # Sprint 17.3: consolidated into a SINGLE Qdrant call
                # (count_for_document_version) instead of two — an exact
                # count of 0 already means "not present," so a separate
                # has_document_version presence check is redundant
                # whenever a count is going to be fetched anyway.
                #
                # Sprint 17.4: an untracked (None) chunk_count is now
                # ALWAYS treated as incomplete, forcing exactly one
                # re-ingest — Sprint 17.3's `actual_chunk_count > 0`
                # fallback let a document with real, intact points but
                # an untracked count be skipped forever, which meant
                # registry.upsert_document(...) (the only call site that
                # ever writes a real chunk_count) was never reached and
                # chunk_count could never leave None — partial loss
                # could then never be caught for that document. Forcing
                # one real re-ingest writes a trustworthy count, after
                # which ordinary exact-match reconciliation applies. No
                # Qdrant call is needed on this branch — there's nothing
                # to compare a count against yet.
                index_present_and_complete = True
                if not changed:
                    record = registry.get_document(connector.source_type, document.source_id)
                    expected_chunk_count = record.chunk_count if record else None
                    if expected_chunk_count is None:
                        index_present_and_complete = False
                    else:
                        actual_chunk_count = store.count_for_document_version(
                            connector.source_type, document.source_id, content_hash
                        )
                        index_present_and_complete = actual_chunk_count == expected_chunk_count
                    check_span.set_attribute(
                        "check.index_present_and_complete", index_present_and_complete
                    )

            if not changed and index_present_and_complete:
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
                # that). The real, disclosed tradeoff: between the first
                # upsert_batch below and delete_stale_chunks, BOTH
                # versions are simultaneously searchable — see
                # docs/sprint-13-plan.md and the README's re-index
                # section for the measured window and why it isn't
                # eliminated here.
                #
                # The try/except below (Sprint 16) closes a gap that
                # guarantee didn't cover: with multiple batches, an
                # earlier batch can already be upserted under the NEW
                # version when a later batch's embed_fn raises. Without
                # rollback that partial new version would sit in Qdrant
                # forever (delete_stale_chunks never runs after a raise)
                # — see docs/sprint-16-plan.md. On failure, every point
                # upserted so far under this content_hash is deleted
                # before the exception is re-raised, restoring the
                # collection to "only the OLD version, nothing from the
                # new one" for the whole document, not just its first
                # batch.
                #
                # Sprint 17.5: that rollback assumed content_hash always
                # names a version Qdrant has never seen before — true for
                # a real A->B content change, but false since Sprint 17.2
                # added reconciliation repair: an unchanged document
                # (content_hash == the CURRENT version) can re-enter this
                # same try block when its index is detected incomplete,
                # meaning some points under this exact content_hash are
                # ALREADY healthy before this attempt starts. A "before"
                # snapshot of this version's point IDs lets rollback
                # delete only what THIS attempt added (after - before)
                # instead of wiping the whole version — see
                # docs/sprint-17-5-plan.md. For a real A->B change this
                # snapshot is always empty, so rollback behavior there is
                # unchanged.
                points_before_attempt = store.list_point_ids_for_version(
                    connector.source_type, document.source_id, document_version=content_hash
                )
                try:
                    for batch_start in range(0, len(chunks), upsert_batch_size):
                        batch = chunks[batch_start : batch_start + upsert_batch_size]

                        with tracer.start_as_current_span("embed_batch") as span:
                            span.set_attribute("embed.chunk_count", len(batch))
                            span.set_attribute("embed.concurrency", embedding_concurrency)
                            dense_vectors = await embed_texts_concurrently(
                                [chunk.text for chunk in batch], embed_fn, embedding_concurrency
                            )
                            sparse_vectors = [
                                sparse_encoder.embed_document(chunk.text) for chunk in batch
                            ]

                        with tracer.start_as_current_span("upsert_batch") as span:
                            span.set_attribute("upsert.chunk_count", len(batch))
                            store.upsert_chunks(batch, dense_vectors, sparse_vectors)

                        chunks_upserted += len(batch)
                except asyncio.CancelledError:
                    # Sprint 17: CancelledError inherits from
                    # BaseException, not Exception (since Python 3.8), so
                    # the `except Exception` block below never caught a
                    # real task.cancel() delivered mid-loop — a real path,
                    # not theoretical: SyncScheduler shutdown or an ASGI
                    # server's graceful shutdown can cancel an in-flight
                    # sync coroutine. Without this block, a cancellation
                    # left the same stranded-partial-version state Sprint
                    # 16 fixed for raised exceptions. Same rollback,
                    # separate branch — never swallow a cancellation, so
                    # `raise` here (not `raise` after catching as `exc`)
                    # re-raises CancelledError itself, preserving the
                    # calling task's ability to actually stop.
                    with tracer.start_as_current_span("rollback_partial_version") as span:
                        span.set_attribute("rollback.source_id", document.source_id)
                        span.set_attribute("rollback.document_version", content_hash)
                        span.set_attribute("rollback.reason", "cancelled")
                        # Sprint 17.1: delete_version itself can fail (a
                        # real possibility — the same shutdown sequence
                        # that triggered this cancellation may have
                        # already started tearing down the Qdrant
                        # connection). Log it, but never let it replace
                        # the CancelledError the caller needs to see —
                        # this bare `raise` below must always re-raise
                        # the ORIGINAL cancellation, not a rollback
                        # failure.
                        try:
                            points_after_attempt = store.list_point_ids_for_version(
                                connector.source_type,
                                document.source_id,
                                document_version=content_hash,
                            )
                            added_by_this_attempt = points_after_attempt - points_before_attempt
                            span.set_attribute(
                                "rollback.points_deleted", len(added_by_this_attempt)
                            )
                            store.delete_points(list(added_by_this_attempt))
                        except Exception:
                            logger.exception(
                                "rollback delete_points failed during cancellation for "
                                "%s:%s — original CancelledError still propagates",
                                connector.source_type,
                                document.source_id,
                            )
                    raise
                except Exception:
                    with tracer.start_as_current_span("rollback_partial_version") as span:
                        span.set_attribute("rollback.source_id", document.source_id)
                        span.set_attribute("rollback.document_version", content_hash)
                        span.set_attribute("rollback.reason", "error")
                        points_after_attempt = store.list_point_ids_for_version(
                            connector.source_type, document.source_id, document_version=content_hash
                        )
                        added_by_this_attempt = points_after_attempt - points_before_attempt
                        span.set_attribute("rollback.points_deleted", len(added_by_this_attempt))
                        store.delete_points(list(added_by_this_attempt))
                    raise

                doc_span.set_attribute("ingest.chunk_count", len(chunks))

                # Sprint 17.3: delete_stale_versions only removes points
                # whose document_version DIFFERS from the one just
                # written — an unexpected point that already shares the
                # CURRENT version (a stale point-ID-scheme leftover, or
                # any other source of same-version duplicates) is
                # invisible to it. Left uncleaned, Sprint 17.2's own
                # chunk_count reconciliation would see the mismatch
                # forever and re-ingest this document on every single
                # sync without the extra point ever going away — a real
                # infinite loop, not just a cosmetic duplicate. Compare
                # what's actually in Qdrant against what THIS upsert
                # just wrote and delete anything extra.
                with tracer.start_as_current_span("cleanup_duplicate_points") as span:
                    expected_ids = {QdrantStore.point_id_for(chunk) for chunk in chunks}
                    actual_ids = store.list_point_ids_for_version(
                        connector.source_type, document.source_id, document_version=content_hash
                    )
                    extra_ids = actual_ids - expected_ids
                    span.set_attribute("cleanup.extra_point_count", len(extra_ids))
                    if extra_ids:
                        store.delete_points(list(extra_ids))

                with tracer.start_as_current_span("delete_stale_chunks") as span:
                    span.set_attribute("delete_stale_chunks.source_id", document.source_id)
                    span.set_attribute("delete_stale_chunks.keep_version", content_hash)
                    store.delete_stale_versions(
                        connector.source_type, document.source_id, keep_version=content_hash
                    )

            # Registered only after a successful chunk+upsert, so a failure
            # partway through doesn't leave the registry claiming a document
            # was ingested when it wasn't.
            registry.upsert_document(
                connector.source_type, document.source_id, content_hash, chunk_count=len(chunks)
            )
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
