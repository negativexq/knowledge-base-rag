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
    # Sprint 18: PipelineFingerprint.digest() from the last real ingest —
    # None = "never fingerprinted" (a legacy row, or a document upserted
    # without passing one), same defaulting reasoning as chunk_count
    # above. Lets a future reconciliation check detect "content hash is
    # unchanged but the embedding model/instruction/index schema this was
    # indexed under has changed" — something content_hash alone can never
    # see. See app/ingestion/fingerprint.py.
    pipeline_fingerprint: str | None = None
    # Sprint 23: which tenant owns this document — part of the registry's
    # actual PRIMARY KEY (app/registry/store.py), not just informational.
    # Defaulted to "default" for the same backward-compatibility reason
    # chunk_count/pipeline_fingerprint were — every pre-Sprint-23 row is
    # backfilled to this exact value by
    # _migrate_add_tenant_id_and_rebuild_pk.
    tenant_id: str = "default"
