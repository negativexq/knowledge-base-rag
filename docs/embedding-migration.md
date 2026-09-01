# Embedding Migration Operator Guide

Sprint 18-21 benchmarked embedding models against this app's real
retrieval pipeline and reached a pre-committed, statistically-supported
decision: **`ADOPT_QWEN3_4B_1024`** — replace the original
`nomic-embed-text@768` production default with `Qwen3-Embedding-4B`
truncated to 1024 dimensions (see `docs/PLANNING.md`'s Sprint 18-21
closing notes for the full benchmark history — that history is never
rewritten or removed just because a later model won).

Sprint 22 turns that decision into a real, validated, rollback-tested
Qdrant index lifecycle operation — this document is written so an
operator can execute a migration without reading any other doc first.

## Why a migration, not a config edit

Editing `EMBEDDING_MODEL_KEY`/`EMBEDDING_OUTPUT_DIMENSION` alone is
**never** sufficient. Every existing document's vectors are still
768-dimensional nomic vectors; a config-only change means the app either
fails outright (`app/migration/startup_guard.py`'s dimension guard) or,
worse, silently searches a collection full of vectors from the wrong
model. A real migration re-embeds the entire corpus under the new model
into an **isolated, new physical Qdrant collection**, validates it, and
only then flips production traffic over.

## Architecture: blue/green via a Qdrant alias

```
                    +-- kb_chunks (nomic@768, existing)
kb_active (alias) --|
                    +-- kb_qwen3_4b_1024_<fingerprint> (new)
```

Qdrant treats an alias exactly like a real collection name for every
search/upsert/delete call — nothing in `app/ingestion` or
`app/retrieval` needs to know an alias is involved. `kb_active` is
created only once a migration activates; before that, every code path
transparently falls back to the literal `QDRANT_COLLECTION_NAME`
(`kb_chunks` by default) — an unmigrated deployment is entirely
unaffected. See `app/migration/aliasing.py`.

Physical collection names are deterministic:
`kb_<model>_<dimension>_<fingerprint-prefix>` (`app/migration/naming.py`)
— readable at a glance, and guaranteed unique per exact pipeline
configuration (model, dimension, instruction, index schema version).

## The pipeline fingerprint is the migration boundary

`app/ingestion/fingerprint.py::PipelineFingerprint` covers embedding
model, revision, backend, dimension, query/document instruction, and the
index schema version. `python -m scripts.operations.migrate_embedding_index plan`
compares the fingerprint of what's currently active against the
fingerprint implied by `EMBEDDING_MODEL_KEY`/`EMBEDDING_OUTPUT_DIMENSION`
right now — if they match, it prints `NO MIGRATION REQUIRED` and does
nothing.

## Command reference

Every command talks to the REAL Qdrant/Ollama in your `.env` — there is
no mock mode.

```bash
# Read-only: what would change, and what documents/chunks are involved.
python -m scripts.operations.migrate_embedding_index plan

# Re-index the full corpus into a new, isolated target collection.
# Production keeps serving the OLD collection throughout — this never
# touches the active alias/collection. Safe to re-run after a crash —
# already-completed documents are skipped, not re-embedded.
python -m scripts.operations.migrate_embedding_index migrate
python -m scripts.operations.migrate_embedding_index migrate --dry-run   # plan only

# Structural checks (counts, dimension, schema, no duplicates) + the
# full frozen 220-question golden-set quality gate against the target
# collection. Refuses to let you activate if either fails.
python -m scripts.operations.migrate_embedding_index validate

# Atomically repoints kb_active at the (now-validated) target collection,
# then runs a fast post-switch smoke check. If the smoke check fails,
# the alias is AUTOMATICALLY switched back before this command exits
# non-zero — production is never left pointed at an unverified target.
python -m scripts.operations.migrate_embedding_index activate

# Atomically repoints kb_active back at whatever it pointed to before
# the last activate/rollback. Symmetric: running this twice in a row
# re-activates the collection you just rolled back from. Neither
# collection is ever deleted by this command.
python -m scripts.operations.migrate_embedding_index rollback

# What's active right now, what the rollback target is, and the latest
# migration's status — safe to run any time, including after a restart.
python -m scripts.operations.migrate_embedding_index status

# EXPLICIT, human-invoked only — never called automatically by any other
# command. Deletes the collection currently recorded as the rollback
# target and clears that slot. Refuses if that collection is somehow
# still the active one.
python -m scripts.operations.migrate_embedding_index cleanup-old
```

## Failure and cancellation semantics

- **Indexing failure** (Ollama/Qdrant error, Ctrl+C): the target
  collection may be left partially built, but the active alias/collection
  is never touched — production is unaffected. Manifest status becomes
  `FAILED` (or stays `INDEXING`/resumable on a plain interrupt); re-run
  `migrate` to resume.
- **Validation failure**: manifest status becomes `FAILED`, `activate`
  refuses to run (it checks for `READY_TO_SWITCH` explicitly).
- **Post-switch smoke failure**: the alias is switched back
  automatically before `activate` raises — this is a tested code path
  (`tests/test_embedding_migration.py::test_activate_with_failing_smoke_check_rolls_back_automatically`),
  not just a documented intention.
- **Old collection retention**: a successfully activated migration NEVER
  deletes the previous collection. Only `cleanup-old`, run explicitly by
  a human, does that.

## Idempotency and resume

`migrate` is safe to re-run: it reuses the SAME `migration_id` and target
collection as long as the manifest at
`artifacts/embedding-migration-sprint22/migration-result.json` hasn't
reached a terminal state and still targets the same fingerprint.
Indexing itself uses the unchanged `app/ingestion/ingest.py::ingest_connector`
incremental-sync logic against an isolated per-migration registry file —
a document already fully indexed under the target fingerprint is
skipped, not re-embedded, so a crash-and-rerun only completes the
remaining work.

## Known limitations

- Sprint 21's `stability.json` only tracked cross-lingual Recall@5/MRR
  and nDCG@5 per config in its run-to-run distributions — it never
  recorded an absolute mono-lingual Recall@5 baseline per config (only
  the paired delta between two configs). `run_quality_gate` reports
  mono-lingual Recall@5 for the target but skips comparing it against a
  baseline that doesn't exist in a reusable form, rather than fabricating
  one.
- Failure-injection scenarios (a real mid-migration Ollama/Qdrant outage)
  are covered by hermetic automated tests
  (`tests/test_embedding_migration.py`), not repeated against a real
  Docker/Ollama instance — deliberately breaking a real local service to
  prove this was judged not worth the operational risk for this sprint.
- This design is "no serving interruption by construction" (old index
  keeps serving throughout indexing/validation; the alias switch is a
  single atomic Qdrant call) — it is not a load-tested zero-downtime
  claim under real concurrent production traffic.
- ~~`SyncManager` does not pass a `pipeline_fingerprint` to
  `ingest_connector` for ordinary production syncs~~ — **fixed as part
  of this sprint** (see "Production sync fingerprint enforcement"
  below). `app/wiring.py::build_app()` now builds a `PipelineFingerprint`
  from the same `active_embedding_config(settings)` single source of
  truth the migration itself uses, and passes it into
  `SyncManager(...)`, which threads it through to every
  `ingest_connector()` call it makes.

## Production sync fingerprint enforcement

Every production sync (`POST /sync/{source_type}`, the scheduler, or a
manual trigger) now carries the currently active pipeline's fingerprint
into `ingest_connector`. This closes a real gap: a document whose
`content_hash` hasn't changed but whose registry row still records an
OLDER pipeline's fingerprint (e.g. a document synced before a migration
activated) is treated as stale and re-embedded under the CURRENTLY
active model — exactly the same reconciliation logic
`scripts/operations/migrate_embedding_index.py`'s own indexing phase already
relies on (Sprint 18), now also protecting ordinary production syncs.

Verified for real: after activating `qwen3-4b@1024`, the first
production sync via the real `/sync/filesystem` endpoint re-embedded
every document still carrying a stale (pre-migration) fingerprint —
`files_processed=6, chunks_upserted=53` — bringing every registry row's
`pipeline_fingerprint` in line with the active model. A second sync
immediately after correctly skipped all 6 documents
(`files_processed=0, files_skipped=6`) — steady state, not an infinite
re-embed loop. Every point written landed at 1024 dimensions; the old
`kb_chunks` (nomic) collection's point count was unaffected throughout.

## Cleaning up the old collection

Only do this once you're confident you'll never need to roll back:

```bash
python -m scripts.operations.migrate_embedding_index cleanup-old
```

This permanently deletes the previous collection and clears the
rollback slot. There is no undo.
