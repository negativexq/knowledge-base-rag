# Sprint 17 — Identity & Cancellation Safety

## Context (read before planning, not assumed)

Sprint 16's closing note reported 380 tests green, `ruff` clean, and a
multi-batch re-index rollback bug fixed. A third external review of that
work found a more severe, pre-existing bug it exposed: `point_id_for`'s
identity key.

Confirmed directly against code:

- `QdrantStore.point_id_for` (`app/ingestion/qdrant_store.py`) builds its
  UUID5 key from `f"{chunk.source_type}:{chunk.doc_id}:{chunk.page_number}:"
  f"{chunk.paragraph_index}:{chunk.char_range[0]}:{chunk.char_range[1]}"`
  — **`source_id` is not in the key.** `doc_id` is a content hash
  (`app/ingestion/chunker.py::compute_doc_id`), so two documents with
  byte-identical content but different filenames/source_ids (e.g. a PDF
  duplicated as `contract-a.pdf` and `contract-b.pdf`, or two Notion
  pages that happen to share text) produce the exact same
  `(doc_id, page_number, paragraph_index, char_range)` tuple for their
  corresponding chunks, hence the same point ID. The second document's
  `upsert_chunks` call silently overwrites the first's points in Qdrant
  — not an error, not a duplicate, just data loss with no trace of it.
- **The bug was hidden by the test suite itself**, confirmed by reading
  `tests/test_qdrant_store.py::test_delete_by_source_does_not_touch_other_documents`
  closely: it calls `_chunk(source_id="doc1")` and `_chunk(source_id="doc2")`,
  but `_chunk`'s default `doc_id="doc1"` is never overridden in either
  call — so both chunks already collide on point ID *before* the test's
  own `delete_by_source` call ever runs. `store.upsert_chunks([...])`
  silently upserts only ONE point (the second call overwrote the first),
  so the test's `assert store.count() == 1` after deletion passes for
  the wrong reason — it never actually proves two independent documents'
  points survived independently, because there was only ever one point
  to begin with. This is the sprint's central lesson: a green test can
  hide the exact bug it was meant to catch, and the fix here isn't
  complete without confirming the *new* test actually red-then-greens
  around the real fix, not around test-helper coincidence.
- `app/ingestion/ingest.py`'s Sprint 16 rollback block is
  `except Exception:` (line ~275) — `asyncio.CancelledError` inherits
  from `BaseException` directly in Python 3.8+, not `Exception`, so a
  cancellation during the embed/upsert loop bypasses the rollback
  entirely, propagating straight past `delete_version` and leaving
  whatever partial new version had been upserted so far permanently
  stuck (the exact failure mode Sprint 16 fixed for regular exceptions,
  reopened for cancellation). This is a real path, not theoretical:
  `app/sync/scheduler.py` and any ASGI server's graceful shutdown can
  legitimately call `task.cancel()` on an in-flight sync coroutine.
  `app/sync/manager.py::trigger_sync`'s own `except Exception as exc:`
  has the identical gap — a cancelled sync run's `finally:` block still
  flips `self._running[source_type] = False` (correct, `finally` always
  runs), but the run's `sync_runs` row is left forever in `STATUS_RUNNING`
  ("running") since neither the `except` nor the `else` branch executes
  on a `CancelledError` — indistinguishable in the Sync Status UI from a
  process that crashed mid-sync with no record of why.
- `slugify()` (`app/shared/slug.py`) replaces every non-word character
  with `_` — confirmed by reading its regex (`r"[^\w\-]"` → `_`). Two
  different real filenames, e.g. `"foo bar.md"` and `"foo_bar.md"`,
  slugify to the identical `source_id` (`"foo_bar"` with the extension
  stripped, or `"foo_bar.md"` / `"foo_bar_md"`-shaped either way with it
  kept). `ingest_connector` never checks for this — two connector
  documents silently sharing a `source_id` would interleave their
  registry rows and Qdrant points nondeterministically depending on
  iteration order, a second flavor of the same "silent identity
  collision" bug class as the point-ID issue, worth closing in the same
  sprint.
- `ensure_collection()` (post-Sprint-16) does
  `info.config.params.vectors[VECTOR_NAME]` directly after confirming
  `SPARSE_VECTOR_NAME in (info.config.params.sparse_vectors or {})` —
  but `VECTOR_NAME` isn't checked for membership first. A collection
  that has *some* sparse config (however named) but no `"dense"` named
  vector at all — a genuinely possible misconfiguration, not
  hypothetical, since Qdrant collections can have sparse-only or
  differently-named dense vectors — raises a raw `KeyError` instead of
  the intended `UnexpectedCollectionSchemaError`, breaking the "fail
  clearly, tell the human what's wrong" contract this function exists
  for. Separately, the sparse check only verifies the key exists, never
  that `sparse_vectors[SPARSE_VECTOR_NAME].modifier == qmodels.Modifier.IDF`
  — a collection with a sparse vector using a different (or no) modifier
  passes silently, even though `create_collection` always sets IDF
  explicitly, meaning the two code paths (create vs. validate) don't
  actually agree on what "correct schema" means.
- `QdrantStore.upsert_chunks` zips `chunks`, `dense_vectors`, and
  `sparse_vectors` with no length check — `zip()` silently truncates to
  the shortest input. A caller bug that produces mismatched-length lists
  (an off-by-one in a future batching change, a partial embed result
  that isn't caught elsewhere) would silently upsert fewer points than
  chunks exist, with no error and no chunk-count/point-count assertion
  anywhere to catch it before it reaches production data.
- README: `## Known Limitations`'s re-index bullet still says "measured
  at ~12 microseconds locally" — Sprint 16 updated the `### Re-indexing a
  changed document` section's prose with the real multi-batch number
  (~1.5–3ms, measured from the *first* upsert_batch) but missed this
  duplicate mention in Known Limitations, leaving two contradictory
  numbers in the same document. Separately, `## Highlights` has a
  bullet titled **"Grounded, multi-source citations"** — the word
  "Grounded" here reads as a claim of semantic grounding (verifying a
  claim is actually supported by its cited text), which
  `app/llm/grounding.py`'s own docstring explicitly disclaims
  ("NOT semantic grounding... only that the citation itself points to
  something real") and which the `### Citation integrity validation, not
  semantic grounding` section three headings later directly contradicts
  the Highlights heading's framing.

## Scope, in priority order

### 1. Point ID collision (most critical)

**Fix**: add `source_id` to `point_id_for`'s key —
`f"{chunk.source_type}:{chunk.source_id}:{chunk.doc_id}:{chunk.page_number}:"
f"{chunk.paragraph_index}:{chunk.char_range[0]}:{chunk.char_range[1]}"`.
`source_id` placed right after `source_type` (both are stable identity
fields; `doc_id` is the content hash that changes on edit, so it stays
grouped with the position fields that also describe "where in this
specific version of this specific document").

**Test-first, in the order that actually catches the bug**:
1. A new unit test in `tests/test_qdrant_store.py` asserting
   `point_id_for` produces DIFFERENT ids for two chunks sharing
   identical `doc_id`/`page_number`/`paragraph_index`/`char_range` but
   different `source_id` — run BEFORE the fix, confirm it fails (proving
   the test catches the real bug, not a strawman).
2. Fix `tests/test_delete_by_source_does_not_touch_other_documents`
   itself: give its two `_chunk(...)` calls distinct, explicit `doc_id`s
   (not relying on the default) SO its "2 documents, 1 deleted, 1
   survives" story is actually true again — but this alone isn't
   sufficient evidence the general bug is fixed, since it only exercises
   one specific doc_id/source_id combination.
3. New scenario test: two chunks built with the SAME doc_id, SAME
   page/paragraph/char_range, but different source_id, `upsert_chunks`'d
   together. Assert `store.count() == 2` **before any deletion** (the
   review's explicit ask — this is the assertion that was missing and
   let the original bug hide). Then delete one by source, assert the
   other survives with its own text intact.
4. Real e2e test (bonus, per the review): two files with byte-identical
   content, `a.md`/`b.md`, both fed through `LocalFilesystemConnector` +
   `ingest_connector` into a real (`:memory:`) Qdrant collection + real
   SQLite registry. Assert both end up with independent registry rows
   AND independent, non-colliding Qdrant points (`store.count()`
   reflects both documents' full chunk counts, not one overwritten by
   the other) — proving the fix holds through the full real pipeline,
   not just at the `point_id_for` unit level.

### 2. Cancellation rollback bypass

**Fix**: in `ingest_connector`'s try/except (the Sprint 16 rollback
block), add a sibling `except asyncio.CancelledError:` that runs the
identical `store.delete_version(...)` rollback, then re-raises
(`raise` alone, preserving `CancelledError` — never swallow a
cancellation, that breaks the calling task's ability to actually stop).
Add `STATUS_CANCELLED = "cancelled"` to `app/sync/models.py`.
`SyncManager.trigger_sync`: add an `except asyncio.CancelledError:`
branch alongside the existing `except Exception as exc:` that calls
`self._history.finish_run(run_id, status=STATUS_CANCELLED,
error_message="Sync was cancelled")` before re-raising — so a cancelled
run's `sync_runs` row reads "cancelled," not silently stuck at
"running" forever.

**Test-first**: a real `asyncio.Task` wrapping `ingest_connector` (or
`trigger_sync`), with an `embed_fn` that signals "batch 1 upserted, now
in batch 2" (e.g. via an `asyncio.Event` or a counter check) at which
point the test calls `task.cancel()` on the running task — a REAL
cancellation delivered by asyncio's own machinery, not a manually
raised `CancelledError` standing in for one (the two are not always
equivalent in where they get delivered). Assert: (a) awaiting the
cancelled task raises `CancelledError`, (b) the rollback ran — zero
points survive under the new document_version, old version intact, (c)
for the `SyncManager`-level test, `sync_runs` shows `status="cancelled"`
for that run, not stuck at `"running"`.

### 3. Duplicate source_id fail-fast guard

**Fix**: at the top of `ingest_connector`, right after
`current_documents = await connector.list_documents()`, check for
duplicate `source_id`s among them (e.g. `len(seen_source_ids) !=
len(current_documents)`, computed from the same set already built for
the deletion phase) and raise a new `DuplicateSourceIdError` (in
`app/ingestion/ingest.py`, alongside `IngestStats`) naming the
colliding `source_id`(s), before any registry/Qdrant work happens for
this sync run — fail-fast, no partial damage. This is deliberately a
connector-output check, not a `slugify()` fix: `slugify` collisions are
one real cause but not the only possible one (a connector could return
duplicates for its own reasons), and checking at the `ingest_connector`
boundary catches all of them uniformly.

**Test-first**: a fake `Connector.list_documents()` returning two
`ConnectorDocument`s with the same `source_id`, assert `ingest_connector`
raises `DuplicateSourceIdError` before touching the registry or store
(verified via a spy/counter — zero `registry.upsert_document` or
`store.upsert_chunks` calls happened).

### 4. Complete Qdrant schema validation

**Fix, two parts**:
- Before `info.config.params.vectors[VECTOR_NAME]`, check
  `VECTOR_NAME in (info.config.params.vectors or {})`; raise
  `UnexpectedCollectionSchemaError` (not a raw `KeyError`) if absent,
  with a message naming what's missing.
- After confirming `SPARSE_VECTOR_NAME` is present, also check
  `info.config.params.sparse_vectors[SPARSE_VECTOR_NAME].modifier ==
  qmodels.Modifier.IDF`; raise the same error type if it doesn't match.

**Test-first**: a collection created with a dense vector under some
OTHER name (not `"dense"`) plus a correctly-named sparse vector — assert
`ensure_collection()` raises `UnexpectedCollectionSchemaError` (not
`KeyError`). A second collection with the right dense AND sparse vector
names but a non-IDF (or no) sparse modifier — assert the same.

### 5. `upsert_chunks` length guard

**Fix**: at the top of `upsert_chunks`, assert
`len(chunks) == len(dense_vectors) == len(sparse_vectors)`, raise
`ValueError` with the three lengths in the message if not.

**Test-first**: call `upsert_chunks` with mismatched-length lists (e.g.
2 chunks, 1 dense vector), assert `ValueError` is raised and
`store.count()` is still 0 afterward (nothing partially written).

### 6. README fixes

- `## Known Limitations`'s re-index bullet: replace "measured at ~12
  microseconds locally" with the same real Sprint 16 number already in
  `### Re-indexing a changed document` (~1.5–3ms for a real multi-batch
  document, measured from the first upsert), so the document doesn't
  contradict itself.
- `## Highlights`: rename **"Grounded, multi-source citations"** to
  **"Source-scoped citation validation"** (or equivalent language that
  doesn't imply semantic grounding), keeping the bullet's existing body
  text (the cross-source-spoofing-proof description) — it already
  correctly describes citation *integrity*, only the heading word
  oversells it.

## Rules carried over

- Test-first, especially items 1 and 2 — and for each new test, verify
  it actually fails before the fix (not just that it passes after) so
  the test's own validity is confirmed, not assumed. This sprint's whole
  premise is that a passing test can hide a real bug.
- No AI co-author line in commits.
- Closing note must include: the real, concrete impact of the point-ID
  collision (what data loss looks like, confirmed via the reproduction
  test), and a description of how the cancellation test delivers a real
  `task.cancel()`, not a substitute.

## Definition of Done

Two documents with identical content but different sources no longer
collide (proven with a real test that asserts point count before any
deletion happens); cancellation during a sync rolls back correctly and
records `status="cancelled"`, never leaving a run stuck at "running";
duplicate source_id fails fast before touching the registry/store;
Qdrant schema validation raises its own error type (not `KeyError`) and
checks the sparse modifier too; `upsert_chunks` rejects mismatched
input lengths; README's two re-index-window numbers agree and the
Highlights heading doesn't overclaim; tests and lint clean.
