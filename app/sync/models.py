from dataclasses import dataclass
from datetime import datetime

from app.ingestion.ingest import IngestStats

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_REJECTED = "rejected_already_running"

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
