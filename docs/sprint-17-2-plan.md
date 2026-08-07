# Sprint 17.2 — Index Reconciliation

## Context (read before planning, not assumed)

Sprint 17.1's closing note reported 393 tests green, `ruff` clean, and a
fail-fast index-schema-version migration guard added
(`DocumentRegistry.ensure_index_schema_version()`, called once at
`build_app()` startup). A fifth review points at a broader architectural
gap that guard doesn't close: **the registry and Qdrant are two separate
persistent stores, and nothing ever re-verifies they still agree.**
`ingest_connector`'s skip decision
(`app/ingestion/ingest.py`, `registry.has_changed(...)`) only asks "does
this content's hash differ from what the registry last recorded" — it
never asks "are this document's points actually still in Qdrant." If
Qdrant loses data by any means other than this app's own delete calls —
a manual `DELETE`, a `:memory:`/ephemeral Qdrant restarted without its
volume, an operator running `docker compose down -v` on *only* the
Qdrant service, a partially-restored backup — the registry has no way
to notice. The document is skipped forever (until its content next
changes for real), silently missing from search results with no error,
no log, nothing.

Confirmed directly against code:

- `app/ingestion/ingest.py`'s `check_document` block: `changed =
  registry.has_changed(connector.source_type, document.source_id,
  content_hash)`; `if not changed: files_skipped += 1; continue` — this
  is the entire skip decision. No Qdrant read happens on this path at
  all.
- `QdrantStore` (`app/ingestion/qdrant_store.py`) has no method to check
  whether a given `(source_type, source_id, document_version)` actually
  has any points — `count()` exists but is collection-wide, not
  filtered.
- `DocumentRegistry` (`app/registry/store.py`) tracks `content_hash`,
  `version` (an edit counter, not the index schema version), and now
  `index_schema_version` metadata — but nothing about how many chunks a
  document produced, so there's no way to compare "registry expects N
  chunks" against "Qdrant actually has M."
- `DocumentRegistry.get_index_schema_version()` does `int(row[0])`
  directly on the stored metadata value with no error handling —
  reproduced directly: writing a non-numeric string into
  `registry_metadata.value` for the `index_schema_version` key and
  calling `ensure_index_schema_version()` raises a raw `ValueError`
  ("invalid literal for int()..."), not the intended
  `IndexSchemaMismatchError`.
- `ensure_index_schema_version()`'s only real branch condition is
  `stored == CURRENT_INDEX_SCHEMA_VERSION` (return) vs. everything else
  (raise, after the fresh-empty special case) — a stored version
  *ahead* of `CURRENT_INDEX_SCHEMA_VERSION` (e.g. a registry built by a
  newer version of this code, then the app downgraded) already isn't
  special-cased to be silently accepted; it falls into the same "raise"
  path. This should already work correctly, confirmed by reading the
  logic, but there is no test proving it — only same-or-behind scenarios
  are tested today.
- README's opening paragraph (line 7) still reads "...cross-encoder
  reranking, grounded generation with citations, OpenTelemetry
  tracing)..." — the one place the pre-Sprint-17 "grounded" wording
  survived; every other occurrence was already fixed in Sprints 17 and
  17.1.
- `docker-compose.yml`: confirmed both `qdrant_storage` and
  `registry_data` are named volumes wiped together by `docker compose
  down -v` — the documented migration remediation
  (`IndexSchemaMismatchError`'s own message) already wipes both stores
  in lockstep, not just the registry.

## Scope

### 1. `QdrantStore.has_document_version(...)`

New method: `has_document_version(source_type: str, source_id: str,
document_version: str) -> bool` — a cheap presence check
(`client.scroll(..., limit=1)` against a filter on all three fields,
`len(points) > 0`), not an exact count. This is the primitive the
reconciliation check in item 2 is built on.

### 2. Incremental sync requires content-unchanged AND index-present

`ingest_connector`'s skip condition changes from `if not changed:` to:
content unchanged is necessary but no longer sufficient — the document
is only skipped if `store.has_document_version(...)` *also* confirms
its points are actually still there. If content is unchanged but the
index copy is gone, the document is treated the same as "changed" and
goes through the normal (already-safe, Sprint 13/16/17-hardened)
re-ingest path — no new code path, just a wider trigger condition for
the existing one.

**Performance**: this adds one Qdrant round trip per document *already
being skipped as unchanged* — the common case on every incremental
sync, so the cost is real, not edge-case-only. Mitigated by construction:
the check only runs for documents that already passed the (cheap,
local, no-network) `registry.has_changed()` check — a document whose
content changed already pays for a full re-embed+upsert regardless, so
adding one more Qdrant call to that path would be immaterial; the
reconciliation check is skipped entirely for that branch. `scroll(...,
limit=1)` is a cheap point-lookup style query (bounded result size,
indexed by payload filter), not a collection scan — no attempt is made
here to batch these into one multi-document query, since
`ingest_connector` already makes one Qdrant round trip per changed
document during upsert and this follows the same per-document call
pattern already established, and batching would be a real but separate
optimization out of this sprint's scope (this project's sync runs are
not high-document-count enough today to have measured this as a real
bottleneck — see the Sprint 14 embedding-throughput benchmark's own
finding that Qdrant's write path, not read/metadata calls, was never
the bottleneck).

**Test-first, the review's exact scenario**: real `ingest_connector`
run against a real folder → real (`:memory:`) Qdrant + real SQLite
registry. Then **manually delete the document's points from Qdrant
directly** (`store.delete_by_source(...)`, simulating external data
loss — NOT touching the registry at all, so `content_hash` stays
identical). Run `ingest_connector` again: assert the document is
**not** skipped (real re-embed/re-upsert happens,
`stats.files_processed` includes it, `files_skipped` does not), and
its points are back in Qdrant afterward.

### 3. Bonus: `chunk_count` tracking for partial-index detection

Item 1/2 catches "completely gone" (zero points). It does not catch
"partially gone" (some but not all of a multi-chunk document's points
missing — e.g. a crash during an external/manual cleanup, not this
app's own writes, which are already deferred-cleanup-safe per Sprint
13/16). Implemented since feasible within scope:

- `DocumentRegistry`: new `chunk_count` column on `documents` (a real
  `ALTER TABLE ... ADD COLUMN` migration guarded by a `PRAGMA
  table_info` check, since existing registries predate this column and
  `CREATE TABLE IF NOT EXISTS` alone won't add it to them).
  `DocumentRecord` gains `chunk_count: int = 0` (defaulted, so every
  existing construction call site — tests included — keeps working).
  `upsert_document(...)` gains an optional `chunk_count: int | None =
  None` parameter; `ingest_connector` passes `len(chunks)` when it
  calls `upsert_document` after a successful re-index.
- `QdrantStore.count_for_document_version(...)`: an *exact* count
  (`client.count(..., count_filter=..., exact=True)`), more expensive
  than the presence-only `has_document_version` — only called when
  `has_document_version` already returned `True` (so at least one point
  is confirmed present) **and** the registry has a non-zero
  `chunk_count` on record to compare against (so a pre-migration
  registry row with no tracked count — `chunk_count == 0` by the
  column's default — doesn't trigger a spurious re-index; it's treated
  the same as "no count expectation, presence check is all we have").
  This keeps the expensive exact-count call rare: only on documents
  that are unchanged, present, *and* already being tracked with a real
  expected count.
- Skip condition becomes: unchanged AND present AND (no tracked
  expected count OR actual count matches). A mismatch (present but
  wrong count) is treated the same as "missing" — full re-ingest, not a
  partial patch (consistent with this project's existing "re-embed the
  whole document" philosophy, never partial-chunk patching).

**Test-first**: real ingest, then manually delete only SOME of a
multi-chunk document's points (leaving `chunk_count` in the registry
pointing at a higher number than what's actually in Qdrant) — assert
the next sync detects the mismatch and re-ingests, restoring the full
chunk count.

### 4. The "registry fresh, Qdrant stale" scenario

Answered by tracing through what actually happens, not assumed:
`docker compose down -v` (the one remediation path
`IndexSchemaMismatchError` actually documents) wipes both
`qdrant_storage` and `registry_data` together — confirmed via
`docker-compose.yml`, both are named volumes under the same `volumes:`
top-level key. So the "registry wiped, Qdrant untouched" scenario only
arises from a non-standard operator action (manually deleting just the
registry file, or resetting just the `registry_data` volume) — not the
documented path.

If it *does* happen: a fresh, empty registry has no rows, so
`registry.has_changed(...)` returns `True` for every document on the
next sync (no existing record to compare against) — every document
goes through the full re-ingest path regardless of items 1–3's
reconciliation logic, which only fires on the *unchanged* branch. This
self-heals the specific Sprint 17 point-ID-collision gap (any two
previously-colliding documents get their own distinct new-format point
IDs on this forced re-ingest). **One disclosed residual edge case,
not fixed here**: for a document whose content is unaffected by the
collision (i.e. it wasn't the "losing" side of a collision, its old
points are still genuinely correct), the forced re-ingest's
`delete_stale_versions(keep_version=content_hash)` cleanup does *not*
remove the pre-existing old-format points, because their
`document_version` already equals the new content hash (content didn't
change) — so the newly-upserted new-format points and the surviving
old-format points end up coexisting as harmless duplicates (same text,
two point IDs) rather than being cleanly deduplicated. This is a
data-quality nit (duplicate search results for that one document), not
a correctness or data-loss issue, and is disclosed here rather than
silently left undocumented — matching this project's existing pattern
of naming real, measured tradeoffs instead of hiding them (e.g. the
Sprint 13 duplicate-visibility window). No separate code fix is scoped
for this edge case; it only affects a non-standard partial-wipe
operator action, which the documented remediation doesn't produce.

### 5. Downgrade test

New test: a registry with an explicitly-stored version of
`CURRENT_INDEX_SCHEMA_VERSION + 1` (simulating "this registry was built
by a newer version of the code, then the running app was downgraded")
— assert `ensure_index_schema_version()` raises
`IndexSchemaMismatchError`. Per the Context section, the existing logic
should already handle this (no special-casing of "stored > current"
exists, both directions fall into the same raise branch) — this test
exists to prove that claim rather than leave it as an unverified
assumption.

### 6. Corrupted metadata value

`get_index_schema_version()`: wrap the `int(row[0])` conversion in a
try/except that raises `IndexSchemaMismatchError` (not a raw
`ValueError`) when the stored value isn't a valid integer — same "tell
the human clearly" contract every other schema-mismatch path in this
codebase already follows. Test: write a non-numeric string directly
into `registry_metadata` for the `index_schema_version` key, assert
`ensure_index_schema_version()` raises `IndexSchemaMismatchError` (not
`ValueError`).

### 7. README fix

Line 7: "...cross-encoder reranking, grounded generation with
citations, OpenTelemetry tracing)..." → "...cross-encoder reranking,
citation-aware generation, OpenTelemetry tracing)..." — the last
surviving "grounded" phrasing, made consistent with every other
citation-related heading/description already fixed in Sprints 17 and
17.1.

## Rules carried over

- Test-first throughout; item 2's core test must be the review's exact
  scenario (real ingest, manual Qdrant-only deletion, prove automatic
  re-index on next sync) — not a synthetic substitute.
- No AI co-author line in commits.
- Closing note must state how the reconciliation mechanism works and
  whether/how its performance cost was measured or reasoned about.

## Definition of Done

A document manually deleted from Qdrant (registry untouched, hash
unchanged) is automatically re-indexed on the next sync, proven with a
real scenario test; a downgrade (stored version ahead of current) is
detected and fails fast; corrupted (non-numeric) schema-version
metadata produces `IndexSchemaMismatchError`, not a raw `ValueError`;
README's last "grounded" phrasing is fixed; tests and lint clean.

This is the last sprint — the project freezes after this closes.
