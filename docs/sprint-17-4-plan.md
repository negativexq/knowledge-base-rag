# Sprint 17.4 — Migration Fix (Sprint 17.2→17.3 upgrade path) — FINAL sprint

## Context (read before planning, not assumed)

Sprint 17.3's closing note reported 420 tests green, `ruff` clean, and
`chunk_count` split into `None` (never tracked) vs. `0` (genuinely
empty) to close an infinite-loop bug. A seventh review found that
fix's own migration path is broken for a **real** Sprint 17.2 database
— not a hypothetical one.

Confirmed directly against code and by real reproduction:

- `_migrate_add_chunk_count_column` (`app/registry/store.py`) is
  `if "chunk_count" not in columns: ALTER TABLE ... ADD COLUMN
  chunk_count INTEGER`. A genuinely pre-Sprint-17.2 database (the
  column doesn't exist at all) is handled correctly by this — `ADD
  COLUMN` with no default leaves every row `NULL`. But a genuine
  **Sprint 17.2** database already has the column, created by that
  sprint's schema: `chunk_count INTEGER NOT NULL DEFAULT 0`. The
  membership check (`"chunk_count" not in columns`) is `False` for
  such a database, so the migration is a complete no-op — the physical
  `NOT NULL` constraint survives untouched.
- Reproduced directly: constructing a real SQLite table with `chunk_count
  INTEGER NOT NULL DEFAULT 0` (the actual Sprint 17.2 schema, not the
  simplified "column missing" fixture Sprint 17.3's own migration test
  used) and attempting an `INSERT ... chunk_count = NULL` raises
  `sqlite3.IntegrityError: NOT NULL constraint failed:
  documents.chunk_count`. `DocumentRegistry.upsert_document`'s public
  signature is `chunk_count: int | None = None` — nothing in the class
  prevents a future call site (or a caller outside `ingest_connector`,
  which today always happens to pass a real `len(chunks)` int) from
  triggering this against a real 17.2-vintage database.
- Sprint 17.3's own migration test,
  `test_a_pre_sprint_17_2_registry_file_gets_the_chunk_count_column_migrated`,
  only proves the "column missing entirely" case — its raw-SQL fixture
  creates the `documents` table *without* a `chunk_count` column at
  all, which is the pre-17.2 shape, not the 17.2 shape. It has never
  exercised, and therefore never could have caught, the real 17.2
  upgrade path this sprint fixes. This is stated plainly, not
  glossed over: the existing test was accidentally testing the easy
  case.
- Independently, `ingest_connector`'s reconciliation logic
  (`app/ingestion/ingest.py`) currently does `if expected_chunk_count is
  None: index_present_and_complete = actual_chunk_count > 0`. Traced
  through: a document with an untracked (`None`) `chunk_count` that
  happens to have at least one real point in Qdrant is treated as
  "complete" and **skipped** — `registry.upsert_document(...)` (the
  only call site that ever writes a real `chunk_count`) is never
  reached on the skip path. `expected_chunk_count` therefore has no
  path to ever leave `None` for such a document; it stays untracked
  forever, and partial point loss for it can never be detected by the
  count-comparison logic Sprint 17.2/17.3 built specifically to catch
  that.

## Scope

### 1. Fix the migration to actually reach a nullable column (most critical)

**Test-first, proving the existing test's blind spot first**: a new
fixture builds the *actual* Sprint 17.2 schema via raw SQL —
`chunk_count INTEGER NOT NULL DEFAULT 0`, exactly as that sprint's
`_SCHEMA` defined it, with a row inserted carrying the ambiguous legacy
value `chunk_count = 0`. Constructing `DocumentRegistry` against this
file and then calling `PRAGMA table_info(documents)` directly confirms
— *before any fix* — that the column is still reported `notnull=1`,
proving the current migration is a no-op for this real shape (not
assumed, checked). A second assertion attempts
`registry.upsert_document(..., chunk_count=None)` against this
unfixed database and confirms it raises `sqlite3.IntegrityError`,
reproducing the real crash risk directly.

**Fix**: SQLite has no `ALTER COLUMN` to relax a `NOT NULL` constraint,
so the migration rebuilds the table when it detects the column exists
*and* is still `NOT NULL` (checked via `PRAGMA table_info`'s `notnull`
flag, not just column presence): rename `documents` to a temp name,
create a fresh `documents` table with the nullable definition, copy
every row across — converting `chunk_count = 0` specifically to `NULL`
(not every value: a real non-zero count written by Sprint 17.2's
`ingest_connector` is already unambiguous and is preserved as-is; only
`0` was ever ambiguous between "genuinely empty" and "the column's own
default, never really set") — then drop the temp table. Wrapped in the
same transaction as schema setup so a partial rebuild can't be
observed. After the fix, the same test's `PRAGMA table_info` check
confirms `notnull=0`, and the same `upsert_document(...,
chunk_count=None)` call that used to raise now succeeds.

### 2. Legacy `chunk_count=None` must be promoted, not skipped forever

**Fix**: `if expected_chunk_count is None:` now sets
`index_present_and_complete = False` unconditionally — a document with
an untracked count is always treated as needing re-ingest, exactly
once. That re-ingest calls the real embed/upsert path and then
`registry.upsert_document(..., chunk_count=len(chunks))`, which writes
a real, trustworthy count — from that point on, ordinary reconciliation
(exact count comparison) applies to this document like any other. The
`store.count_for_document_version(...)` call is skipped entirely on
this branch (there's nothing to compare it against, and forcing
re-ingest doesn't need it) — a small, free efficiency gain alongside
the correctness fix.

**Test-first**: a document with `chunk_count IS NULL` in the registry
but real, fully-intact Qdrant points. Before the fix, this scenario is
skipped (`files_skipped == 1`, `files_processed == 0`) even though
`chunk_count` never gets a chance to become trustworthy — confirmed by
running the unfixed code. After the fix: first sync forces
re-ingest (`files_processed == 1`) and the registry's `chunk_count` is
now a real integer, not `None`; second sync (content still unchanged,
now genuinely tracked and matching) is skipped normally.

### 3. Combined scenario: real Sprint 17.2 upgrade with existing Qdrant data

**Test-first, the review's exact scenario**: a document is ingested for
real (so it has a real `content_hash` and real Qdrant points). Its
registry row is then rewritten, via raw SQL against a table built with
the actual Sprint 17.2 `NOT NULL DEFAULT 0` schema, to carry the exact
same `content_hash` but `chunk_count = 0` (the ambiguous legacy value —
this simulates "this row was written back when Sprint 17.2 was live,
whether or not it was ever explicitly tracked, both look identical:
`0`"). A fresh `DocumentRegistry` is constructed against that file
(triggering item 1's migration: the column becomes nullable, and this
row's `0` becomes `NULL`). Running `ingest_connector` with this
registry against the same Qdrant store (still holding the real,
untouched points from the original ingest): first sync must force a
real re-ingest (content unchanged, but the now-`NULL` chunk_count
per item 2 always forces one) and afterward the registry carries a
real tracked count; a second sync is then a genuine no-op
(`files_skipped == 1`). This proves items 1 and 2 together resolve
the real upgrade path end to end, not just in isolation.

### 4. Documentation-only notes (no code change)

- README's `## Known Limitations`: `QdrantStore.list_source_ids(...)`
  scans every point's payload for a `source_type` (paginated
  `scroll`), so its cost is `O(total chunks across every document of
  that source_type)`, not `O(document count)` — it runs once per sync
  (Sprint 17.3's orphan-cleanup addition). Documented as a real,
  disclosed cost, not silently assumed cheap.
- Same section: `ensure_collection()`'s payload indexes (Sprint 17.3)
  are only created for a **brand-new** collection — an existing
  collection that already passed schema validation is never mutated,
  so a collection created before Sprint 17.3 shipped does not
  retroactively gain these indexes after an upgrade. Documented
  alongside the index-schema-version migration note it's adjacent to
  in spirit (a schema/behavior change that doesn't retroactively apply
  to already-provisioned infrastructure).

## Rules carried over

- Test-first; item 1's fixture must mirror the real Sprint 17.2 schema
  exactly (the `NOT NULL DEFAULT 0` constraint included), not the
  simplified "column absent" shape the existing migration test already
  covers.
- No AI co-author line in commits.
- Closing note must include: proof the migration now actually produces
  a nullable column against a real 17.2-shaped database, proof legacy
  `None` documents get promoted, and an explicit, final "the project is
  now frozen" statement — this is the last planned commit.

## Definition of Done

A database built with the real Sprint 17.2 schema is proven (via
`PRAGMA table_info`, not just behavior) to end up with a genuinely
nullable `chunk_count` column after opening it with current code; a
legacy `chunk_count IS NULL` document with intact Qdrant points is
proven to be re-ingested exactly once and then correctly skip on the
next sync; the combined real-upgrade-plus-existing-data scenario is
tested end to end; README documents the two disclosed, no-fix-needed
costs; tests and lint clean.

This is the project's final planned sprint. No further commits are
scheduled after this one lands.
