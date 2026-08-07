# 0002 — Incremental sync: three-phase diff against the registry

## Context

Sprint 3 gave `ingest_connector` a working but non-incremental sync: every
run re-parsed, re-embedded, and re-upserted every document the connector
listed, regardless of whether it had changed. Sprint 4's job was to make
this incremental using the document registry (Sprint 2) as the source of
truth for "what did we already know."

Two related design questions had to be answered: how to detect a document
that vanished from its source entirely (not just "unchanged" or
"changed"), and how to guarantee no orphaned Qdrant points when a
document's chunk count shrinks (or the document is deleted) — the
registry only stores one content hash per document, not the set of point
IDs that hash produced.

## Decision

Split each `ingest_connector` run into three phases, using
`registry.list_documents(source_type)` compared against the connector's
current `list_documents()` as the diff:

1. **Deletions** — a registry row whose `source_id` the connector no
   longer lists means the document vanished from its source. Its Qdrant
   points and registry row are both removed.
2. **Unchanged** — `registry.has_changed(source_type, source_id,
   content_hash)` says no: skipped entirely, zero Qdrant calls (no
   re-parse, re-embed, or re-upsert), and the registry row is left
   untouched too (no `last_synced_at` refresh — accepted simplification,
   not needed until Sprint 7's sync history needed "when did this last
   actually run").
3. **New/changed** — re-ingested. Any existing points for
   `(source_type, source_id)` are deleted first (Sprint 4's original
   ordering; superseded by [0003](0003-deferred-cleanup-versioned-reindex.md)
   in Sprint 13), then the document is fully re-embedded and re-upserted.

The key choice: deletion (both phase 1's real deletion and phase 3's
stale-chunk cleanup) is keyed on the connector-stable
`(source_type, source_id)` identity, not on the content-hash `doc_id`.
`doc_id` changes on every edit, so a doc_id-keyed delete would need the
*previous* hash read back from the registry before deleting — an extra
read, and an easy place to get the ordering wrong. `(source_type,
source_id)` is stable for the life of the document, so "delete everything
this document currently owns" is correct regardless of how many chunks it
used to have, whether the count grew or shrank, or whether it's brand new
(deletes zero points, safe to call unconditionally).

## Consequences

- A document whose chunk count changes between syncs (grows or shrinks)
  never leaves orphaned points — proven directly by
  `tests/test_sync_scenarios.py::test_shrinking_a_document_leaves_no_orphan_chunks`.
- The "unchanged" fast path is a real, measured zero-Qdrant-call skip
  (`tests/test_sync_scenarios.py::test_noop_sync_issues_zero_qdrant_write_calls`
  uses a call-counting store wrapper to prove it, not just that the end
  state looks the same).
- The registry's `has_changed()` and the connector's own listing are the
  only two things `ingest_connector` needs to reconcile — no separate
  point-ID bookkeeping is required anywhere.
