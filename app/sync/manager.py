import asyncio
import logging

from opentelemetry import trace

from app.connectors.base import Connector
from app.ingestion.chunking_config import ChunkingConfig
from app.ingestion.fingerprint import PipelineFingerprint
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

logger = logging.getLogger(__name__)


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
        pipeline_fingerprint: PipelineFingerprint | None = None,
        tenant_ids: dict[str, str] | None = None,
        chunking_config: ChunkingConfig | None = None,
    ):
        # pipeline_fingerprint identifies the embedding
        # model/revision/backend/dimension/instruction/index-schema
        # combination `embed_fn` and `store` were actually built from —
        # app/wiring.py builds it via
        # app/ingestion/fingerprint.py::build_pipeline_fingerprint(
        # app/llm/embedding_models.py::active_embedding_config(settings)),
        # the same source of truth used by index migration
        # reads. Passed straight through to every ingest_connector() call
        # below so production sync gets the same content_hash-can't-see-
        # a model swap — content hashes alone cannot detect that. It is
        # optional only for test callers; real wiring always supplies it.
        self._connectors = connectors
        self._store = store
        self._registry = registry
        self._history = history
        self._embed_fn = embed_fn
        self._sparse_encoder = sparse_encoder
        self._tracer = tracer or get_tracer(__name__)
        self._embedding_concurrency = embedding_concurrency
        self._pipeline_fingerprint = pipeline_fingerprint
        self._chunking_config = chunking_config
        # Which tenant owns each connector's documents —
        # server-side configuration (app/wiring.py::connector_tenant_ids),
        # NEVER derived from a sync request. A source_type missing from
        # this mapping falls back to "default" (the same default
        # app/ingestion/models.py::Chunk.tenant_id itself uses) rather
        # than raising — every existing test/caller that never heard of
        # tenancy keeps working under one consistent, real tenant value,
        # not silently under "no tenant restriction."
        self._tenant_ids = tenant_ids or {}
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
            run_id: int | None = None
            try:
                # Keep run creation inside the guarded region so a failed
                # SQLite insert cannot leave the source marked as running.
                run_id = self._history.start_run(source_type, trigger, trace_id=trace_id)
                stats = await ingest_connector(
                    self._connectors[source_type],
                    self._store,
                    self._registry,
                    self._embed_fn,
                    self._sparse_encoder,
                    embedding_concurrency=self._embedding_concurrency,
                    tracer=self._tracer,
                    pipeline_fingerprint=self._pipeline_fingerprint,
                    tenant_id=self._tenant_ids.get(source_type, "default"),
                    chunking_config=self._chunking_config,
                )
            except asyncio.CancelledError:
                # CancelledError is a BaseException, not an
                # Exception, so the `except Exception as exc:` branch
                # below never caught a real task.cancel() — the
                # sync_runs row was left stuck at STATUS_RUNNING forever,
                # indistinguishable from a process that crashed mid-sync.
                # Record it as cancelled, then re-raise (never swallow a
                # cancellation — the calling task must still stop).
                span.set_attribute("sync.status", STATUS_CANCELLED)
                # finish_run itself can fail (a real
                # possibility — the same shutdown sequence that
                # triggered this cancellation may already be tearing
                # down the sqlite connection). Log it, but never let it
                # replace the CancelledError the caller needs to see.
                # run_id can be None (start_run itself
                # was cancelled before ever returning) — nothing was
                # recorded as started, so there's nothing to finish.
                if run_id is not None:
                    try:
                        self._history.finish_run(
                            run_id, status=STATUS_CANCELLED, error_message="Sync was cancelled"
                        )
                    except Exception:
                        logger.exception(
                            "finish_run(status=cancelled) failed for run_id=%s — original "
                            "CancelledError still propagates",
                            run_id,
                        )
                raise
            except Exception as exc:
                span.set_attribute("sync.status", STATUS_ERROR)
                # run_id is None only when start_run itself
                # raised exc — there's no run row to finish, and the
                # caller needs to see this failure directly rather than
                # a swallowed SyncRunResult(status=ERROR), since (unlike
                # an ingest_connector failure) it isn't a normal "the
                # sync ran and failed" outcome.
                if run_id is None:
                    raise
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
