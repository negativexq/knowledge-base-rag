# 0003 — Zero-downtime versioned re-index with deferred cleanup (not atomic)

## Context

Sprint 4's re-index ordering ([0002](0002-incremental-sync-three-phase-registry-diff.md))
deleted a changed document's existing Qdrant points *before*
re-parsing/embedding/upserting the new content. This has a real data-loss
window: if `embed_fn` raises partway through (a network error, an Ollama
timeout — not hypothetical, this project's own `OllamaClient` originally
shipped with a too-short default timeout that hit exactly this class of
failure, see Sprint 9's closing note), the old chunks are already gone
and the new ones are only partially written. The document is unsearchable
until a later sync happens to succeed, or indefinitely if it doesn't.

An external code review flagged this in Sprint 12's scope; fixing it
became Sprint 13.

## Decision

Reorder to **embed and upsert the new version completely first**, tagged
with a new `document_version` payload field (the new content hash — kept
as its own field rather than reusing `doc_id`, since `doc_id`'s job is
"one ingredient of a unique point ID" and `document_version`'s job is
"the filter key deferred cleanup deletes by"; decoupling them means a
future change to point-ID hashing can't silently break re-index cleanup).
Only once every batch of the new version is confirmed upserted does
`QdrantStore.delete_stale_versions(source_type, source_id, keep_version)`
delete the old version's points.

This is explicitly **not** called atomic anywhere in code, tests, or
docs — a true atomic swap needs transactional guarantees Qdrant doesn't
offer. The real, disclosed tradeoff: between the new version's upsert
finishing and the old version's cleanup running, both versions are
simultaneously present and searchable — a query in that window can
return duplicate/stale-alongside-fresh chunks for the same document.

## Consequences

- A failure mid-embed now leaves the *old* version fully intact and
  searchable — proven with a real scenario test that simulates the
  failure directly and confirms the old chunks (same point IDs, same
  text) survive, and that the registry still points at the old hash so a
  retry picks the document back up
  (`tests/test_versioned_reindex.py::test_embed_failure_mid_reindex_leaves_old_version_searchable`).
- The duplicate-visibility window is real, not hypothetical: a test
  subclasses `QdrantStore` to snapshot the collection's actual contents
  at the exact moment before `delete_stale_versions` runs, and confirms
  both versions' `document_version` values and text are present
  simultaneously.
- The window's duration was measured, not estimated, using the OTel
  spans already instrumented since Sprint 8: the real gap between the
  last `upsert_batch` span ending and `delete_stale_chunks` starting was
  ~12 microseconds on a local run — bounded by the time between two
  sequential Qdrant calls, not by embedding time (all embedding happens
  *before* the window opens).
- No attempt was made to eliminate the window (e.g. query-time
  deduplication preferring the newest version) — that would paper over
  the tradeoff this ADR exists to document honestly. See the README's
  "Re-indexing a changed document" section.
