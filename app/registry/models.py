from dataclasses import dataclass
from datetime import datetime

DEFAULT_STATUS = "active"


@dataclass(frozen=True)
class DocumentRecord:
    source_type: str
    source_id: str
    content_hash: str
    last_synced_at: datetime
    version: int
    status: str
    # Sprint 17.2: how many chunks this document produced at its last
    # real ingest — 0 means "never tracked" (a pre-Sprint-17.2 row, or a
    # document upserted without passing chunk_count), not "zero chunks."
    # Used to detect PARTIAL Qdrant point loss (some but not all points
    # missing), which a presence-only check can't distinguish from a
    # fully-intact index. Defaulted for the same backward-compatibility
    # reason heading_path/document_version were (Sprints 3/13) — every
    # existing DocumentRecord(...) call site keeps working.
    chunk_count: int = 0
