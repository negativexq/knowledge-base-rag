# Sprint 17.3 — Final Correctness Patch (reconciliation symmetry + duplicate cleanup)

## Context (read before planning, not assumed)

Sprint 17.2's closing note reported 406 tests green, `ruff` clean, and
reconciliation logic (`has_document_version` + `count_for_document_version`
+ `chunk_count` tracking) added to detect a document whose Qdrant points
went missing while its registry hash stayed unchanged. That same closing
note *disclosed* a residual edge case as "harmless": a document
unaffected by the Sprint 17 point-ID collision, after a
"registry-wiped-but-Qdrant-untouched" forced re-ingest, could end up
with two points sharing the same `document_version` (an old-format
leftover plus a newly-upserted one) — because
`delete_stale_versions(keep_version=...)` only deletes points whose
`document_version` *differs* from `keep_version`, so a duplicate that
already shares the kept version is invisible to it. A sixth review
found that Sprint 17.2's *own* new reconciliation logic turns this
previously-cosmetic duplicate into a real, unbounded bug.

Confirmed directly against code and by real reproduction:

- **Infinite re-index loop (critical).** With `chunk_count` tracking
  live, an unchanged document whose actual Qdrant point count doesn't
  match the registry's expected count is treated as "changed" and
  re-ingested. If a document has one duplicate extra point (the
  disclosed edge case), a full re-ingest re-upserts the correct N
  points (idempotent — same point IDs, same content, no growth) but
  `delete_stale_versions` still doesn't touch the duplicate (same
  `document_version`, by construction — content never changed). The
  registry then records `chunk_count = N` (correct expected value)
  while Qdrant still holds `N + 1` actual points. The *next* sync sees
  `actual_count (N+1) != expected_chunk_count (N)`, treats it as
  "changed" again, re-ingests again, and the extra point survives
  again — forever. Reproduced directly: a real ingest followed by
  manually inserting one duplicate point under the same
  `document_version`, then running `ingest_connector` twice in a row,
  confirms the document is reprocessed both times with the extra point
  still present after each run.
- **Qdrant-only orphans are invisible to the deletion loop.**
  `ingest_connector`'s deletion phase (`app/ingestion/ingest.py`,
  right after `fetch_documents`) only iterates
  `registry.list_documents(source_type=...)` — a document whose points
  exist in Qdrant but whose registry row is gone (a reset/lost registry,
  a partial restore, or simply a registry that was replaced without
  Qdrant being touched — exactly the scenario Sprint 17.1's migration
  guard and Sprint 17.2's "registry fresh, Qdrant stale" analysis both
  discuss) is never considered for deletion, even after it genuinely
  vanishes from the connector's current listing. Confirmed by reading
  the loop: `for record in registry.list_documents(...)` has no
  Qdrant-side counterpart at all.
- `QdrantStore` has no method to enumerate distinct `source_id`s present
  for a `source_type` — needed to close the gap above.
- `app/ingestion/ingest.py`'s `check_document` block (Sprint 17.2) calls
  both `store.has_document_version(...)` (presence) and, conditionally,
  `store.count_for_document_version(...)` (exact count) — two separate
  Qdrant round trips in the case where a chunk_count *is* tracked. Since
  `count_for_document_version(...) == 0` is exactly equivalent to "not
  present," the presence call is redundant whenever an exact count is
  going to be fetched anyway.
- `ensure_collection()` never calls `create_payload_index` for
  `source_type`, `source_id`, or `document_version` — every filtered
  query this app makes (`delete_by_source`, `delete_stale_versions`,
  `delete_version`, `has_document_version`,
  `count_for_document_version`, and this sprint's new methods) filters
  on some combination of exactly these three fields, and Sprint 17.2
  measurably increased how often those filtered queries run (once per
  unchanged document, every sync). Confirmed `create_payload_index`
  works against the same `:memory:` Qdrant client this test suite uses
  (with a logged warning that local-mode indexes are a no-op — real
  Qdrant honors them; the call is still made unconditionally so
  production deployments get the benefit, and it's harmless in tests).
- `DocumentRecord.chunk_count: int = 0` (Sprint 17.2) cannot distinguish
  "this document's chunk count was never tracked" (a legacy row, or a
  row from a version of this code that didn't pass `chunk_count`) from
  "this document genuinely produced zero chunks" (confirmed by direct
  reproduction: an empty or whitespace-only Markdown file produces
  exactly 0 chunks via `chunk_markdown_text`). Tracing through Sprint
  17.2's reconciliation logic for a real empty document: `expected_chunk_count
  = 0` was written to skip the exact-count comparison entirely (`if
  expected_chunk_count > 0:` gate), falling back to
  `has_document_version` alone — which can never return `True` for a
  document with zero real points, since "present" was defined as "at
  least one point exists." A genuinely empty document can therefore
  never be recognized as correctly, completely indexed — every sync
  treats it as needing re-ingest, forever (a second, independent
  infinite-loop-shaped bug from the same root ambiguity, not the same
  bug as the duplicate-point one above).
- `ingest_connector`'s docstring (`app/ingestion/ingest.py`) still says
  "Unchanged — registry.has_changed() says no: skipped entirely, zero
  Qdrant calls" — false since Sprint 17.2: the unchanged branch now
  makes at least one Qdrant call (`count_for_document_version` /
  `has_document_version`) to verify the index is actually still there.

## Scope, in priority order

### 1. Duplicate-point cleanup within the same version (most critical)

**Fix**: after the embed/upsert loop successfully finishes for a
document (still before `delete_stale_versions`), compute the expected
point-ID set from the actual `chunks` list just written
(`{QdrantStore.point_id_for(c) for c in chunks}`), fetch the real point
IDs currently present in Qdrant for `(source_type, source_id,
document_version=content_hash)` via a new
`QdrantStore.list_point_ids_for_version(...)` method, and delete any
ID present in Qdrant but not in the expected set via a new
`QdrantStore.delete_points(point_ids)` method. This is symmetrical with
what `delete_stale_versions` already does for *different* versions —
this closes the same gap for points that share the *current* version
but shouldn't exist (stale point-ID-scheme leftovers, or any other
future source of same-version duplicates).

**Test-first**: real ingest of a document, then manually insert a
second point sharing the same `document_version` but a synthetic extra
point ID (simulating exactly the disclosed Sprint 17.2 edge case).
Run `ingest_connector` once: assert the extra point is gone and
`store.count_for_document_version(...)` matches `len(chunks)` exactly.
Run it a **second** time (this is the loop-detection part of the
test, not just the cleanup part): assert the document is now skipped
(`files_skipped == 1`, `files_processed == 0`) — proving the loop
actually terminates, not just that one cleanup pass ran.

### 2. Qdrant-only orphan cleanup

**Fix**: add `QdrantStore.list_source_ids(source_type: str) -> set[str]`
(a paginated scroll over the collection filtered by `source_type`,
collecting distinct `source_id` payload values — needed since a
collection can hold many points per document). In
`ingest_connector`'s deletion phase, union the registry's known
`source_id`s for this `source_type` with Qdrant's actual known
`source_id`s, and delete anything in that union no longer present in
the connector's current listing — not just registry-known records.
`registry.delete_document(...)` on a `source_id` the registry never
had is already a safe no-op (a `DELETE ... WHERE` matching zero rows),
confirmed by reading `DocumentRegistry.delete_document`.

**Test-first, the review's exact scenario**: ingest two documents for
real (registry + Qdrant both populated). Construct a **fresh**
`DocumentRegistry` pointed at a *different* db file (simulating "the
registry was reset/replaced, Qdrant was not touched" — not a
`DELETE FROM documents`, a genuinely separate registry instance with
zero knowledge of either document). Remove one of the two files from
the connector's folder. Run `ingest_connector` with the fresh registry
against the same Qdrant store: assert the removed document's Qdrant
points are gone, even though this registry never had a row for either
document to begin with.

### 3. Consolidate the two reconciliation queries into one

**Fix**: `check_document`'s reconciliation block calls
`store.count_for_document_version(...)` unconditionally on the
unchanged branch (whether or not a `chunk_count` is tracked) and
derives both "present" (`actual_count > 0`) and "complete" (`actual_count
== expected_chunk_count` when tracked, else `actual_count > 0`) from
that single number — `has_document_version` is no longer called from
`ingest_connector` at all (the method itself is kept on `QdrantStore`,
since it's a reasonable standalone primitive with its own passing unit
tests from Sprint 17.2, just no longer needed by this particular call
site). This halves the reconciliation query count for every unchanged,
chunk_count-tracked document — from up to two Qdrant round trips to
exactly one.

### 4. Payload indexes

`ensure_collection()`: after creating a brand-new collection, call
`create_payload_index(collection_name, field_name=..., field_schema=
qmodels.PayloadSchemaType.KEYWORD)` for `source_type`, `source_id`, and
`document_version`. Not applied retroactively to an *existing*
collection that already passed schema validation (adding an index to
an existing collection is a real, if usually fast, background
operation on real Qdrant — out of scope for a validate-only path that
already has a strict "don't mutate an existing collection" policy, see
`UnexpectedCollectionSchemaError`'s docstring) — this only benefits
freshly-created collections, which is the common real-deployment case
(Sprint 17.1's migration remediation, `docker compose down -v && up`,
always produces a fresh collection).

**Performance note for the closing note**: no query-latency benchmark
was run against real Qdrant this sprint (this project's own precedent,
Sprint 14's embedding-throughput benchmark, is the template for what a
real measurement would look like, but reconciliation's query volume —
one filtered lookup per unchanged document per sync — hasn't been
identified as an actual measured bottleneck at this project's scale;
the indexes are added because Sprint 17.2 measurably increased
per-sync Qdrant query volume and every one of those queries filters on
exactly these three fields, not because a slowdown was observed).

### 5. Resolve `chunk_count`'s zero/unknown ambiguity

**Fix**: `DocumentRecord.chunk_count` becomes `int | None = None` (`None`
= never tracked / legacy; any non-negative int, including `0` =
tracked, and `0` genuinely means zero chunks). `upsert_document(...)`'s
`chunk_count` parameter becomes `int | None = None`, passed straight
through (no coercion). The SQLite column drops its `NOT NULL DEFAULT
0` in favor of a plain nullable `INTEGER` — `ALTER TABLE ... ADD
COLUMN chunk_count INTEGER` (no default clause) leaves existing rows
`NULL`, which is exactly the desired "unknown" state for anything that
predates this column. **Known, disclosed limitation of this
migration**: a registry that already ran under Sprint 17.2's schema
(`NOT NULL DEFAULT 0`) would have stored literal `0` for rows where a
real chunk count was never explicitly passed, and this migration can't
retroactively distinguish those already-stored zeros from a genuine
empty-document zero after the fact — accepted here rather than adding
a data-migration heuristic, since this project has no real deployed
data to preserve (development-only, per every prior sprint's
verification approach) and the very next real sync for any such
document re-establishes an accurate count regardless.
`ingest_connector` passes `chunk_count=len(chunks)` unconditionally
(already true since Sprint 17.2 — `len(chunks)` can be `0` and that's
now correctly distinguishable from "not tracked"). Reconciliation logic:
`expected_chunk_count is None` → presence-only fallback (`actual_count
> 0`, same as "never tracked, do the best we can"); otherwise → exact
match required, `0 == 0` included.

### 6. Empty-document infinite-loop test

**Test-first, the review's exact scenario**: ingest a real, genuinely
empty (or whitespace-only) Markdown file — confirmed to produce 0
chunks via `chunk_markdown_text` — through `ingest_connector`. Run it a
second time: assert `files_skipped == 1`, `files_processed == 0` (not
reprocessed). This is the direct proof that item 5's fix closes the
loop, not just that the ambiguity was renamed.

### 7. Fix the stale docstring

`ingest_connector`'s docstring: "Unchanged — registry.has_changed() says
no: skipped entirely, zero Qdrant calls" → update to state the real
Sprint 17.2/17.3 behavior — an unchanged document still costs exactly
one Qdrant reconciliation query (`count_for_document_version`) before
being skipped, not zero.

## Rules carried over

- Test-first, especially items 1 and 2 — simulate the review's exact
  scenarios directly, including proving the loop actually terminates
  (a second sync with no further changes), not just that one cleanup
  pass ran.
- Performance reasoning for items 3 and 4 goes into the closing note
  with justification, not just a bullet point.
- No AI co-author line in commits.
- Closing note must cover: the real impact of the infinite-loop bug,
  how orphan cleanup works, and an explicit "this project is now
  frozen" statement — this is the last planned sprint.

## Definition of Done

A scenario with an extra same-version point stops looping after one
cleanup pass (proven: cleaned up on sync N, skipped on sync N+1);
Qdrant-only orphans (registry has no record at all) are cleaned up on
the next sync (proven with a genuinely fresh, disconnected registry
instance); a genuinely empty document does not loop forever (proven
with two consecutive syncs); tests and lint clean.

This is the last planned sprint. No further hardening rounds are
scheduled after this one closes.
