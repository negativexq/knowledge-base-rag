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
    # Sprint 17.2/17.3: how many chunks this document produced at its
    # last real ingest. None = "never tracked" (a legacy row, or a
    # document upserted without passing chunk_count) — DISTINCT from 0,
    # which now genuinely means "this document produced zero chunks"
    # (a real, reproduced case: an empty or whitespace-only Markdown
    # file). Sprint 17.2 conflated these two states under a single
    # NOT-NULL-DEFAULT-0 column, which meant a genuinely empty document
    # could never be recognized as correctly, completely indexed — its
    # reconciliation check fell back to presence-only, which can never
    # be satisfied by zero real points, causing an infinite re-ingest
    # loop. Used to detect PARTIAL Qdrant point loss (some but not all
    # points missing), which a presence-only check can't distinguish
    # from a fully-intact index. Defaulted for the same
    # backward-compatibility reason heading_path/document_version were
    # (Sprints 3/13) — every existing DocumentRecord(...) call site
    # keeps working.
    chunk_count: int | None = None
