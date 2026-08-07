import asyncio

from opentelemetry import trace

from app.connectors.base import Connector
from app.ingestion.ingest import (
    DEFAULT_EMBEDDING_CONCURRENCY,
    EmbedFn,
    SparseEncoderProtocol,
    ingest_connector,
)
from app.ingestion.qdrant_store import QdrantStore
from app.registry.store import DocumentRegistry
from app.shared.tracing import get_tracer
from app.sync.history import SyncHistory
from app.sync.models import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_REJECTED,
    STATUS_SUCCESS,
    SyncRunResult,
)


class UnknownConnectorError(Exception):
    """Raised when trigger_sync is called for a source_type SyncManager
    wasn't configured with."""


class SyncManager:
    """Owns the one Connector instance per source_type and makes sure two
    syncs of the SAME connector never run concurrently.

    Concurrency guard is a plain per-source_type bool, not an asyncio.Lock:
    the check-and-set (`if self._running[x]: return; self._running[x] = True`)
    has no `await` between the two statements, so under asyncio's
    single-threaded cooperative scheduling no other coroutine can interleave
    between them — this is atomic without needing lock semantics. A second
    concurrent call is REJECTED immediately (not queued) — see
    docs/sprint-07-plan.md for why reject-not-queue was chosen (an HTTP
    caller shouldn't block for an unknown duration waiting on someone
    else's sync).
    """

    def __init__(
        self,
        connectors: dict[str, Connector],
        store: QdrantStore,
        registry: DocumentRegistry,
        history: SyncHistory,
        embed_fn: EmbedFn,
        sparse_encoder: SparseEncoderProtocol,
        tracer: trace.Tracer | None = None,
        embedding_concurrency: int = DEFAULT_EMBEDDING_CONCURRENCY,
    ):
        self._connectors = connectors
        self._store = store
        self._registry = registry
        self._history = history
        self._embed_fn = embed_fn
        self._sparse_encoder = sparse_encoder
        self._tracer = tracer or get_tracer(__name__)
        self._embedding_concurrency = embedding_concurrency
        self._running: dict[str, bool] = dict.fromkeys(connectors, False)

    @property
    def known_source_types(self) -> list[str]:
        return list(self._connectors)

    def is_running(self, source_type: str) -> bool:
        return self._running.get(source_type, False)

    async def trigger_sync(self, source_type: str, trigger: str) -> SyncRunResult:
        if source_type not in self._connectors:
            raise UnknownConnectorError(f"No connector configured for source_type {source_type!r}")

        # Wraps the WHOLE attempt, rejection included, so even a rejected
        # trigger leaves trace evidence it happened — and so this span's
        # trace_id is the one and only trace_id for the entire sync run
        # (ingest_connector's own top-level span, opened while this one is
        # current, becomes its child automatically via context
        # propagation — no need to thread a shared tracer object through).
        with self._tracer.start_as_current_span("sync_run") as span:
            span.set_attribute("sync.source_type", source_type)
            span.set_attribute("sync.trigger", trigger)
            trace_id = format(span.get_span_context().trace_id, "032x")

            if self._running[source_type]:
                span.set_attribute("sync.status", STATUS_REJECTED)
                return SyncRunResult(
                    source_type=source_type,
                    status=STATUS_REJECTED,
                    run_id=None,
                    stats=None,
                    error=None,
                    trace_id=trace_id,
                )

            self._running[source_type] = True
            run_id = self._history.start_run(source_type, trigger, trace_id=trace_id)
            try:
                stats = await ingest_connector(
                    self._connectors[source_type],
                    self._store,
                    self._registry,
                    self._embed_fn,
                    self._sparse_encoder,
                    embedding_concurrency=self._embedding_concurrency,
                    tracer=self._tracer,
                )
            except asyncio.CancelledError:
                # Sprint 17: CancelledError is a BaseException, not an
                # Exception, so the `except Exception as exc:` branch
                # below never caught a real task.cancel() — the
                # sync_runs row was left stuck at STATUS_RUNNING forever,
                # indistinguishable from a process that crashed mid-sync.
                # Record it as cancelled, then re-raise (never swallow a
                # cancellation — the calling task must still stop).
                span.set_attribute("sync.status", STATUS_CANCELLED)
                self._history.finish_run(
                    run_id, status=STATUS_CANCELLED, error_message="Sync was cancelled"
                )
                raise
            except Exception as exc:
                span.set_attribute("sync.status", STATUS_ERROR)
                self._history.finish_run(run_id, status=STATUS_ERROR, error_message=str(exc))
                return SyncRunResult(
                    source_type=source_type,
                    status=STATUS_ERROR,
                    run_id=run_id,
                    stats=None,
                    error=str(exc),
                    trace_id=trace_id,
                )
            else:
                span.set_attribute("sync.status", STATUS_SUCCESS)
                self._history.finish_run(
                    run_id,
                    status=STATUS_SUCCESS,
                    files_processed=stats.files_processed,
                    files_skipped=stats.files_skipped,
                    files_deleted=stats.files_deleted,
                    chunks_upserted=stats.chunks_upserted,
                )
                return SyncRunResult(
                    source_type=source_type,
                    status=STATUS_SUCCESS,
                    run_id=run_id,
                    stats=stats,
                    error=None,
                    trace_id=trace_id,
                )
            finally:
                self._running[source_type] = False
