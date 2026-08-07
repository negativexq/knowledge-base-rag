# Sprint 13 Plan — Safe Versioned Re-index

## Goal

Close the data-loss window in `ingest_connector`'s re-index path (Sprint
4): a changed document currently gets its old chunks deleted *before* the
new ones are parsed/embedded/upserted, so a failure mid-embed leaves it
unsearchable — temporarily if the next sync retries successfully, or
indefinitely if it doesn't.

## Current behavior, confirmed by reading the code (not the task description alone)

`app/ingestion/ingest.py::ingest_connector`, inside the per-document loop
for changed/new documents:

```python
with tracer.start_as_current_span("delete_stale_chunks") as span:
    store.delete_by_source(connector.source_type, document.source_id)

for batch_start in range(0, len(chunks), batch_size):
    ...
    dense_vectors = [await embed_fn(chunk.text) for chunk in batch]  # <-- can raise
    ...
    store.upsert_chunks(batch, dense_vectors, sparse_vectors)
```

`delete_by_source` runs unconditionally before a single embed call. If
`embed_fn` raises on any batch (network error, Ollama timeout, OOM), the
old chunks are already gone and the new ones are only partially written —
the document is unsearchable until a later sync succeeds, and
`registry.upsert_document()` (further down) never runs, so the registry
correctly still thinks it's stale — but that doesn't put the deleted
chunks back.

## Fix: deferred cleanup, not strict atomic

Reorder to embed+upsert the new version completely first, then delete the
old version — **only after** the new one is confirmed written. This is
explicitly **not** presented as atomic (a true atomic swap would need a
transactional store or a two-phase commit Qdrant doesn't offer) — it's a
**zero-downtime versioned re-index with deferred cleanup**, and gets
called that exact thing everywhere it's mentioned (code comments, tests,
README, this doc). The real, disclosed tradeoff: during the gap between
"new version's chunks are upserted" and "old version's chunks are
deleted," both versions are simultaneously present and searchable — a
query can return duplicate/stale-alongside-fresh results for that
document. This sprint doesn't eliminate that window; it measures it and
documents it, because eliminating it would require the atomicity Qdrant
doesn't provide.

### Mechanism: a `document_version` payload field

Every chunk already carries `doc_id` (the content hash — Sprint 0/3), and
the point ID itself is derived partly from `doc_id`, so old- and
new-version chunks already get distinct point IDs today (no accidental
overwrite risk). A **new**, dedicated `document_version` payload field is
added anyway (same value as `doc_id`, set alongside it in
`chunk_document`/`chunk_markdown_text`) rather than overloading `doc_id`
for this — `doc_id`'s job is "one ingredient of a unique point ID,"
`document_version`'s job is "the filter key deferred cleanup deletes by."
Giving the deferred-cleanup mechanism its own explicitly-named field
keeps that intent legible in the Qdrant payload itself, and decouples it
from whatever `doc_id`'s hashing scheme does in the future.

New `QdrantStore.delete_stale_versions(source_type, source_id, keep_version)`:
deletes every point matching `(source_type, source_id)` whose
`document_version` is **not** `keep_version`. Called only after the new
version's chunks are fully upserted. `QdrantStore.delete_by_source`
(deletes *everything* for a source, no version filter) is unchanged and
stays the right tool for the "document vanished from its connector
entirely" case (`ingest_connector`'s phase 1) — that's a real full
deletion, not a version transition.

### New `ingest_connector` order for a changed/new document

1. Parse + chunk (unchanged) — each `Chunk` now carries
   `document_version=content_hash`.
2. Embed + upsert every batch (unchanged logic, just no longer preceded
   by a delete) — chunks for the OLD version are untouched throughout.
3. Only once every batch upserts successfully:
   `store.delete_stale_versions(source_type, source_id, keep_version=content_hash)`.
4. `registry.upsert_document(...)` (unchanged position — after the whole
   document's Qdrant work, so a failure anywhere above still leaves the
   registry correctly claiming "still stale," and a retry is safe: the
   same `content_hash` becomes `keep_version` again, so re-running step
   2 with identical vectors is idempotent, not a leak).

If step 2 raises, steps 3–4 never run — the OLD version's chunks are
still there (never deleted) and still searchable. This is the concrete
fix the DoD asks to prove.

If step 3 itself fails (e.g. a network blip on the delete call), the
document is left with **both** versions searchable rather than the old
one lost — strictly better than today, and self-heals on the next sync
(registry wasn't updated, so it's still "changed," and step 3 is
re-attempted with the same `keep_version`, safe to repeat).

## Real verification plan (not just structural)

- **Data-loss window closed**: a real scenario test that changes a
  document, then re-runs `ingest_connector` with `embed_fn` raising
  partway through a real multi-batch document. Confirms the exception
  propagates (as it does today — no new swallowing) *and* that the OLD
  version's chunks are still in the store, `text` intact, unaffected by
  the aborted re-index. This is the direct contrast with Sprint 4's
  "delete first" behavior, which this same test would fail against the
  old code.
- **Duplicate-visibility window is real, not just claimed**: a store
  subclass hook captures Qdrant's actual state (both `document_version`s
  present, via a raw scroll) at the exact moment *between* the last
  successful upsert and the `delete_stale_versions` call, in a real
  (`:memory:`) Qdrant — proving the window isn't just a comment, it's an
  observable intermediate state.
- **Window duration, measured, not estimated**: `delete_stale_chunks` is
  already its own span (Sprint 8) immediately following the last
  `upsert_batch` span for that document — the real gap between the last
  `upsert_batch` span's end time and `delete_stale_chunks`'s start time
  (both real OTel timestamps, nanosecond precision, captured via
  `InMemorySpanExporter`) is the actual measured window for a real run,
  reported in the closing note rather than guessed.
- **Existing Sprint 4/5 assumptions re-verified, not just re-run**: read
  `tests/test_sync_scenarios.py` and
  `tests/test_citation_cross_source_leak_e2e.py` against the new flow
  before touching anything — neither depends on the OLD delete-first
  ordering specifically (they assert end states: no orphans, correct
  final content, no cross-source leakage), so they're expected to keep
  passing unchanged; run them to confirm rather than assume.

## Scope boundary

No attempt to deduplicate search results during the visibility window
(e.g. preferring the newest `document_version` at query time) — that
would paper over the very tradeoff this sprint is supposed to surface
honestly. `app/retrieval/search.py`/`hybrid_search.py` are untouched.
