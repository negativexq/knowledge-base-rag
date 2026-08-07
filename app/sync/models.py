from dataclasses import dataclass
from datetime import datetime

from app.ingestion.ingest import IngestStats

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_REJECTED = "rejected_already_running"
# Sprint 17: distinct from STATUS_ERROR — a cancelled run (task.cancel(),
# e.g. from scheduler/ASGI shutdown) isn't a failure the sync itself hit,
# and without this a cancelled run's sync_runs row was left stuck at
# STATUS_RUNNING forever (neither trigger_sync's except nor its else
# branch runs on a CancelledError), indistinguishable in the Sync Status
# UI from a process that silently crashed mid-sync.
STATUS_CANCELLED = "cancelled"

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"


@dataclass(frozen=True)
class SyncRun:
    id: int
    source_type: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    files_processed: int | None
    files_skipped: int | None
    files_deleted: int | None
    chunks_upserted: int | None
    error_message: str | None
    trace_id: str | None


@dataclass(frozen=True)
class SyncRunResult:
    source_type: str
    status: str
    run_id: int | None
    stats: IngestStats | None
    error: str | None
    trace_id: str | None = None
