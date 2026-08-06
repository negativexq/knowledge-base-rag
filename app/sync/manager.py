from app.connectors.base import Connector
from app.ingestion.ingest import EmbedFn, SparseEncoderProtocol, ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.registry.store import DocumentRegistry
from app.sync.history import SyncHistory
from app.sync.models import (
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
    ):
        self._connectors = connectors
        self._store = store
        self._registry = registry
        self._history = history
        self._embed_fn = embed_fn
        self._sparse_encoder = sparse_encoder
        self._running: dict[str, bool] = dict.fromkeys(connectors, False)

    @property
    def known_source_types(self) -> list[str]:
        return list(self._connectors)

    def is_running(self, source_type: str) -> bool:
        return self._running.get(source_type, False)

    async def trigger_sync(self, source_type: str, trigger: str) -> SyncRunResult:
        if source_type not in self._connectors:
            raise UnknownConnectorError(f"No connector configured for source_type {source_type!r}")

        if self._running[source_type]:
            return SyncRunResult(
                source_type=source_type,
                status=STATUS_REJECTED,
                run_id=None,
                stats=None,
                error=None,
            )

        self._running[source_type] = True
        run_id = self._history.start_run(source_type, trigger)
        try:
            stats = await ingest_connector(
                self._connectors[source_type],
                self._store,
                self._registry,
                self._embed_fn,
                self._sparse_encoder,
            )
        except Exception as exc:
            self._history.finish_run(run_id, status=STATUS_ERROR, error_message=str(exc))
            return SyncRunResult(
                source_type=source_type,
                status=STATUS_ERROR,
                run_id=run_id,
                stats=None,
                error=str(exc),
            )
        else:
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
            )
        finally:
            self._running[source_type] = False
