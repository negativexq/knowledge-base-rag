# Sprint 17.1 — Migration Safety & Test False-Positive Cleanup

## Context (read before planning, not assumed)

Sprint 17's closing note reported 386 tests green, `ruff` clean, and a
real point-ID collision bug fixed (`QdrantStore.point_id_for` now
includes `source_id`). A fourth external review found that fix, while
correct for *new* re-indexes, does nothing for data that already
collided under the old formula.

Confirmed directly against code:

- **The migration gap is real, not theoretical.** Two documents that
  collided under the pre-Sprint-17 point-ID formula (same content, e.g.
  `contract-a.pdf`/`contract-b.pdf` duplicated) had one's Qdrant points
  silently overwritten by the other's — but their `content_hash` values
  are unaffected by the point-ID formula change (the hash is computed
  from file bytes, `app/connectors/filesystem.py::get_content_hash`,
  completely independent of `point_id_for`). `ingest_connector`'s
  incremental-sync logic (`registry.has_changed(source_type, source_id,
  content_hash)`) therefore still reports these documents as
  "unchanged" on every future sync and skips them — the new point-ID
  formula is only ever exercised on a document's *next real content
  edit*, which may never come. A deployment upgraded straight from
  Sprint 16/before-17 to Sprint 17+ keeps its already-corrupted index
  (one document's points silently missing) forever unless something
  forces a full re-index.
- `app/registry/store.py` has no versioning/metadata mechanism at all —
  confirmed by reading its full schema (`documents` table only, no
  `schema_version` or metadata table) — so there is currently no way for
  the app to know "was this registry/index built before or after the
  point-ID formula changed."
- The two Sprint 16 tests
  `test_ensure_collection_fails_fast_on_wrong_dense_vector_size` and
  `test_ensure_collection_fails_fast_on_wrong_distance_metric`
  (`tests/test_qdrant_store.py`) build their fixture's sparse config
  with `qmodels.SparseVectorParams()` — no `modifier` argument.
  Confirmed by direct reproduction (`python -c ...` against a real
  `:memory:` Qdrant client) that Qdrant's own default for an
  unspecified sparse modifier is `None`, not `IDF`. Since Sprint 17
  added a sparse-modifier check to `ensure_collection()` that runs
  *before* the dense-schema checks, both tests now raise
  `UnexpectedCollectionSchemaError` for the sparse-modifier reason
  ("modifier=None") — reproduced directly: the actual exception message
  is `"...sparse vector has modifier=None — this app requires
  modifier=IDF..."`, never mentioning size or distance at all. Both
  tests' `match=COLLECTION` assertion only checks the collection name
  appears (true of every error this function can raise), so neither
  test actually exercises the dense-size or dense-distance branch it
  claims to test. This is the exact "green test hides the real bug"
  failure mode Sprint 17 itself was about — now found in Sprint 17's
  own test additions.
- `ensure_collection()`'s dense-vector check does
  `dense_vectors = info.config.params.vectors or {}` then
  `VECTOR_NAME not in dense_vectors`. Reproduced directly: Qdrant
  supports creating a collection with a single *unnamed* vector
  (`vectors_config=qmodels.VectorParams(...)` passed directly, not
  wrapped in a `{name: ...}` dict) — in that case
  `info.config.params.vectors` is a `VectorParams` **object**, not a
  dict. Testing `"dense" in vectors_instance` does not raise `TypeError`
  today only because Pydantic `BaseModel` supports `__iter__` (yielding
  `(field_name, value)` pairs, the same mechanism `.dict()`-style
  iteration relies on) — Python's `in` operator falls back to that
  iterator protocol when `__contains__` is absent, comparing `"dense"`
  against each `(field_name, value)` tuple, which is always `False`.
  The code happens to reach the "missing dense vector" branch and raise
  the intended `UnexpectedCollectionSchemaError` — but only by accident,
  relying on an undocumented Pydantic iteration quirk neither this
  code's comments nor its tests ever asserted or explained. A future
  Pydantic/qdrant-client version is free to change `BaseModel.__iter__`
  behavior (or drop it) without warning, at which point this silently
  becomes a real `TypeError` crash instead of the intended clear error.
  Making the check `isinstance(dense_vectors, dict)`-explicit removes
  the reliance on that accident and states the actual intent.
- `app/ingestion/ingest.py`'s Sprint 17 `except asyncio.CancelledError:`
  rollback block calls `store.delete_version(...)` with no error
  handling of its own. If that call itself raises (a real possibility:
  Qdrant unreachable mid-shutdown, a connection already torn down by
  the same shutdown sequence that triggered the cancellation in the
  first place) inside an `except` block, in Python the new exception
  propagates from the bare `raise` and — critically — supersedes the
  original `CancelledError` as what the caller actually sees (the
  original becomes `__context__`, chained but secondary). A caller that
  specifically checks `isinstance(exc, asyncio.CancelledError)` to
  confirm a task actually honored its cancellation would see the wrong
  exception type. `app/sync/manager.py`'s equivalent
  `except asyncio.CancelledError:` branch has the identical shape with
  `self._history.finish_run(...)`.
- README: `## Status` says "Sprints 0–16 complete" (Sprint 17 already
  shipped) and its first bullet says "reranking, grounded citations)"
  — inconsistent with the `## Highlights` bullet already renamed in
  Sprint 17 to "Source-scoped citation validation" specifically to
  avoid the semantic-grounding implication `grounding.py`'s own
  docstring disclaims. Separately, `DuplicateSourceIdError`'s docstring
  (`app/ingestion/ingest.py`) and its test's docstring
  (`tests/test_ingest_connector.py`) both say the duplicate check runs
  "before any registry/Qdrant work happens" / "fails fast... nothing
  touched" — but `ingest_connector` calls `store.ensure_collection()`
  (line 188) *before* the duplicate-source_id check (line ~198–203).
  On a genuinely fresh Qdrant instance, `ensure_collection()` does
  create the collection (schema only, zero points) before the duplicate
  check can fire — so "nothing touched" overstates it. The test's own
  assertions are already precise (`store.count() == 0` and
  `registry.list_documents(...) == []` — both correctly check for zero
  *document data*, not zero *schema objects*), only the prose is loose.

## Scope, in priority order

### 1. Point-ID schema migration detection (most critical)

**Decision: fail-fast at startup, not automatic re-index.** Two options
were on the table; fail-fast is chosen for reasons consistent with this
project's existing risk posture:
- An automatic full re-index at app startup would need real, possibly
  slow, possibly-failing network calls per connector (Notion
  especially) before the app can even start serving `/health` — a
  correctness-critical operation hidden inside what looks like an
  ordinary boot sequence, the same category of implicit,
  irreversible-feeling action `QdrantStore.ensure_collection()` already
  explicitly refuses to do for schema mismatches ("this collection was
  left untouched... delete it yourself if that's genuinely safe" — see
  `UnexpectedCollectionSchemaError`'s docstring). A migration deserves
  the same treatment: don't guess, tell the human.
- The Docker Compose fresh-install pattern (`docker compose down -v` +
  `up`) already exists and is already documented (Sprint 11's real
  fresh-install verification) — reusing it for a schema migration is a
  known, already-tested operator action, not a new concept to learn.
- Fail-fast is trivially testable (a pure function/method call); an
  automatic re-index's correctness would need a much heavier
  integration test (real connectors, real network mocking) for a
  one-time, rare event.

**Mechanism**: a new `registry_metadata` table in `DocumentRegistry`'s
existing SQLite db (`key TEXT PRIMARY KEY, value TEXT NOT NULL`) storing
`index_schema_version`. `CURRENT_INDEX_SCHEMA_VERSION = 2` in
`app/registry/store.py` (constant, with a comment: version 2 = Sprint
17's point-ID formula that includes `source_id`; version 1 implicitly
means "everything before that, including registries with no version row
at all"). New method `DocumentRegistry.ensure_index_schema_version()`:
- If the stored version equals `CURRENT_INDEX_SCHEMA_VERSION`: no-op,
  return.
- If no version is stored AND the registry has zero document rows
  (`list_documents()` empty): this is a genuinely fresh install with
  nothing to migrate — write `CURRENT_INDEX_SCHEMA_VERSION` and return.
  Self-healing: after an operator runs `docker compose down -v` + `up`,
  the next boot's registry is empty, so this branch fires automatically
  and the version gets stamped without any operator action beyond the
  wipe they already had to do.
- Otherwise (no version stored but documents exist — a registry that
  predates this tracking mechanism entirely and therefore predates
  Sprint 17's point-ID fix too — OR an explicitly stored version below
  current): raise `IndexSchemaMismatchError` with a message naming the
  stored vs. required version and the exact remediation command
  (`docker compose down -v && docker compose up`).

Called once, early, in `app/wiring.py::build_app()` right after
`DocumentRegistry(...)` is constructed — before any connector or sync
wiring — so a mismatch stops the app before it starts serving traffic
on a known-corrupt index, matching "refuse to start" semantics.

**Test-first** (`tests/test_document_registry.py`, new tests):
1. A fresh `DocumentRegistry` with zero documents: `ensure_index_schema_version()`
   does not raise, and `get_index_schema_version() ==
   CURRENT_INDEX_SCHEMA_VERSION` afterward (self-stamped).
2. A `DocumentRegistry` with an `upsert_document(...)` call made
   directly (simulating a pre-Sprint-17 real registry that has data but
   was built before this tracking mechanism existed, so it has never
   had a version row written): `ensure_index_schema_version()` raises
   `IndexSchemaMismatchError`.
3. A `DocumentRegistry` with an explicitly-written stale version row
   (simulating a hypothetical future registry state one migration
   behind, once this mechanism itself has a version 3+): raises
   `IndexSchemaMismatchError`.
4. Calling `ensure_index_schema_version()` twice on an already-current
   registry is idempotent (no error, no change).

### 2. Fix the dense-schema test false positives

The fixture's `sparse_vectors_config={SPARSE_VECTOR_NAME:
qmodels.SparseVectorParams()}` in both
`test_ensure_collection_fails_fast_on_wrong_dense_vector_size` and
`test_ensure_collection_fails_fast_on_wrong_distance_metric` gets
`modifier=qmodels.Modifier.IDF` added, so the sparse check passes and
the dense check is what actually fires. Each test's assertion changes
from the generic `match=COLLECTION` to something that can only match
the intended branch — `match="size=384"` for the size test,
`match="EUCLID"` for the distance test — so a future validation branch
reordering or a masking regression like this one gets caught
immediately instead of silently passing for the wrong reason.
Per the sprint's own rule: before fixing, confirm — by temporarily
running the *unfixed* fixture with a `match` on the dense-specific
text — that it currently fails (proving the false-positive is real,
not assumed), then apply the fixture fix and confirm it passes for the
right reason.

### 3. Explicit `isinstance` guard for unnamed-vector collections

`ensure_collection()`: after `dense_vectors = info.config.params.vectors
or {}`, add `if not isinstance(dense_vectors, dict): raise
UnexpectedCollectionSchemaError(...)` before the `VECTOR_NAME not in
dense_vectors` check — states the actual requirement (a NAMED dense
vector, so it can coexist with the named sparse vector in the same
collection) instead of relying on Pydantic `BaseModel.__iter__`'s
accidental `in`-returns-`False` behavior. Test: create a real
`:memory:` collection with `vectors_config=qmodels.VectorParams(...)`
(unnamed, single vector) and a *correct* sparse config (with
`modifier=IDF`, so the sparse checks don't mask this like item 2's bug)
— assert `UnexpectedCollectionSchemaError` is raised with a message
that actually names the unnamed-vector problem (not the old accidental
"missing 'dense' dense vector" phrasing), proving the fix changed
behavior rather than coincidentally matching the pre-fix message.

### 4. Cancellation rollback's own failure must not mask `CancelledError`

Both `ingest.py`'s `except asyncio.CancelledError:` block's
`store.delete_version(...)` call and `sync/manager.py`'s equivalent
block's `self._history.finish_run(...)` call get wrapped in their own
inner `try/except Exception:` that logs (`logger.exception(...)`, new
`logging.getLogger(__name__)` in each module) but does not re-raise the
inner failure — the outer `raise` (still reached, since the inner
except swallowed its own exception) then re-raises the *original*
`asyncio.CancelledError` untouched. Test-first: an
`ingest_connector`/`trigger_sync` cancellation scenario (real
`task.cancel()`, same pattern as Sprint 17's existing cancellation
tests) where the rollback call (`delete_version`/`finish_run`) is
monkeypatched/subclassed to raise its own exception — assert the
caller still sees `asyncio.CancelledError` (not the rollback's
exception type) when awaiting the cancelled task.

### 5. README fixes

- `## Status`: "Sprints 0–16 complete" → "Sprints 0–17 complete" (the
  only occurrence of this specific count phrase, confirmed via grep —
  the sprint description's plural "tüm geçen yerlerde" is satisfied
  since there is exactly one place this claim is made).
- Same bullet: "reranking, grounded citations) ported from
  production-rag-platform" → "reranking, citation-aware generation)
  ported from production-rag-platform" — consistent with Highlights'
  already-renamed "Source-scoped citation validation" bullet, avoiding
  the same semantic-grounding implication in the one place it was
  missed.
- `app/ingestion/ingest.py`'s `DuplicateSourceIdError` docstring and
  `tests/test_ingest_connector.py`'s
  `test_duplicate_source_ids_from_a_connector_fail_fast` docstring:
  "before any registry/Qdrant work happens" / "nothing touched" →
  "before any document points or registry rows are written" (or
  equivalent) — precise about what's actually guaranteed
  (`ensure_collection()` may still create an empty collection schema
  first on a fresh Qdrant instance; the guarantee is zero *document
  data* written, which is exactly what the test's own assertions
  already check).

## Rules carried over

- Test-first throughout.
- Item 2 specifically: reproduce the false-positive for real (already
  done above, confirmed via direct reproduction against `:memory:`
  Qdrant) before editing the fixtures — prove, don't assert.
- No AI co-author line in commits.
- Closing note must state the migration strategy decision (fail-fast,
  not automatic re-index) and its reasoning.

## Definition of Done

A stale/untracked registry with existing document rows is detected and
`build_app()` refuses to start with a clear remediation message
(proven with a real registry-state test, not just a code read); the two
dense-schema tests fail for the dense reason specifically (asserted via
message content, not just error type); an unnamed-vector Qdrant
collection produces a clear `UnexpectedCollectionSchemaError`, not a
`TypeError`, via an explicit check rather than accidental Pydantic
iteration behavior; a rollback failure during cancellation still
surfaces `CancelledError` to the caller, not the rollback's own
exception; README's sprint count, citation-heading wording, and
duplicate-guard documentation are accurate; tests and lint clean.

This is the last sprint before the project freezes — no new features
after this, only closing out this hardening round.
