# Sprint 22 Plan — Qwen3-4B@1024 Production Embedding Migration

## Decision source

Sprint 21 closed with a pre-committed, statistically-supported
`PRODUCTION DECISION = ADOPT_QWEN3_4B_1024` (see `docs/PLANNING.md`'s
Sprint 21 closing note) — but that was a recommendation, not an applied
change. `settings.ollama_embed_model` stayed `nomic-embed-text`.

## Scope

Only the embedding production migration. Explicitly NOT in scope this
sprint: chunking, sparse encoding, RRF fusion, reranker policy,
generation model, prompt system, citation behavior, document sources, or
an Ollama→vLLM backend migration.

## Architecture

Blue/green via a Qdrant alias (`kb_active`, `app/migration/aliasing.py`).
Qdrant resolves an alias exactly like a real collection name for every
operation, so no change was needed in `app/ingestion`/`app/retrieval` —
only `app/wiring.py`'s resolution of which physical name to pass in.
Before any migration, `kb_active` doesn't exist and every call site falls
back to the literal `settings.qdrant_collection_name` — zero behavior
change for an unmigrated deployment.

Physical collection naming: `kb_<model>_<dimension>_<fingerprint-prefix>`
(`app/migration/naming.py`), derived from
`app/ingestion/fingerprint.py::PipelineFingerprint` (extended this sprint
with an `embedding_backend` field).

## New module: `app/migration/`

- `models.py` — `MigrationManifest`, 8-state `MigrationStatus` enum
  (PLANNED/INDEXING/VALIDATING/READY_TO_SWITCH/SWITCHING/ACTIVE/
  ROLLED_BACK/FAILED). Plain typed dataclass + enum, no workflow engine.
- `naming.py` — deterministic collection naming.
- `aliasing.py` — atomic alias switch (`update_collection_aliases` with
  a delete+create batched into one call), alias resolution with legacy
  fallback.
- `embedding_migration.py` — the engine: `plan_migration`, `run_indexing`,
  `validate_structural`, `activate`, `rollback`, `get_status`,
  `cleanup_old_collection`.
- `quality_gate.py` — reuses Sprint 18-21's rank-metrics infrastructure
  against the frozen 220-question golden set for the pre-activation
  quality gate, plus a small stratified smoke check for post-switch
  verification.
- `readiness.py`, `startup_guard.py` — cheap `/health/ready` semantics
  and a fail-fast dimension-mismatch guard at startup.

## Isolated registry for indexing (key design decision)

Indexing reuses `app/ingestion/ingest.py::ingest_connector` completely
unchanged, but points it at an isolated SQLite registry file per
migration_id rather than the production `registry.db`. Using the
production registry would let an unvalidated, not-yet-activated target
collection silently rewrite production's `pipeline_fingerprint` tracking
while production is still serving the OLD collection. The isolated
registry starts empty, so every document looks "new" on the first index
pass (correct full re-embed) and "already present, fingerprint matches"
on any re-run — real idempotency/resume from `ingest_connector`'s
existing incremental-sync semantics, not new machinery.

## Rules

- Old collection is NEVER deleted automatically — only an explicit,
  separate `cleanup-old` CLI command can do that, and it refuses if that
  collection is still the active one.
- Activation runs a post-switch smoke check; a failure triggers an
  automatic alias rollback before `activate` raises.
- `rollback` is symmetric: running it twice re-activates the collection
  just rolled back from, without ever deleting either collection.
- Production config default changes only after a real, validated
  migration — not as a bare `.env` edit.
- New artifacts: `artifacts/embedding-migration-sprint22/{plan.json,
  validation.json,migration-result.json,report.md}`. Previous artifact
  folders (Sprints 18-21) are never touched.
- A real local migration run against Docker Qdrant + native Ollama is
  required, including an actual rollback drill — not just unit tests.

## Test plan

Hermetic tests (`:memory:` Qdrant, fake/deterministic embed functions)
covering: planning (fingerprint match/mismatch on model, dimension,
instruction), collection naming/isolation, full migration + idempotent
rerun + resume-after-partial-run, structural validation gates (doc
count, chunk count, dimension, fingerprint, missing collection),
atomic activation, rollback (including symmetry), failure handling
(indexing failure leaves old collection untouched, post-switch smoke
failure auto-rolls-back), and config/provider wiring
(`active_embedding_config`, startup schema-mismatch guard, readiness).
