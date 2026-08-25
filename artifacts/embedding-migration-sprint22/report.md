# Embedding Migration Sprint 22: Production Migration to qwen3-4b@1024

Real local migration run against Docker Qdrant (`kb-rag-qdrant`) and native Ollama, using the same Sprint 18-21 fixture corpus (`nimbus_handbook.pdf`, `nimbus_cli.md`, `nimbus_api_reference.md`, `nimbus_kurumsal_sss.md`) seeded as the "current production" (nomic-embed-text@768) state before migrating. `migration_id=mig-6963176864ba`.

## 1. Source / target

| | Model | Dimension | Collection | Fingerprint |
|---|---|---|---|---|
| Source (before) | nomic-embed-text | 768 | `kb_chunks` | `0ddc5346c789ca02` |
| Target (after) | qwen3-embedding:4b | 1024 | `kb_qwen3_4b_1024_8ea8f97e` | `8ea8f97e028fc4e1` |

`python -m scripts.migrate_embedding_index plan` correctly identified `full re-index required` (source and target fingerprints differ on model, dimension, and instruction).

## 2. Re-index result

- Documents: 4, Chunks: 51
- `files_processed=4 chunks_upserted=51`, elapsed ≈ 23.5s (real qwen3-embedding:4b inference via native Ollama)
- Old `kb_chunks` collection was verified untouched throughout (51 points before and after indexing) — indexing writes ONLY to the isolated target collection.

## 3. Structural validation

```json
{
  "passed": true,
  "findings": [],
  "document_count": 4,
  "chunk_count": 51,
  "dense_dimension": 1024,
  "duplicate_points": 0
}
```

## 4. Retrieval quality gate (full 220-question Sprint 21 golden set, frozen — not modified)

| Metric | This run | Sprint 21 baseline | Tolerance | Result |
|---|---|---|---|---|
| Cross-lingual Recall@5 | 0.9630 | 0.9630 | 0.03 | within tolerance |
| Cross-lingual MRR | 0.7367 | 0.7336 | 0.03 | within tolerance |
| Mono-lingual Recall@5 | 1.0000 | not available* | — | reported only |
| nDCG@5 | 0.8380 | — | — | reported only |

*Sprint 21's `stability.json` only tracked an absolute mono-lingual Recall@5 per config in its non-inferiority DELTA (not an absolute per-config figure) — see `docs/embedding-migration.md`'s known limitations. The gate does not fabricate a number to compare against; it reports mono-lingual Recall@5 and skips that specific baseline comparison.

`passed=true` — `status=READY_TO_SWITCH`.

## 5. Activation

`python -m scripts.migrate_embedding_index activate` atomically repointed the `kb_active` alias from `kb_chunks` to `kb_qwen3_4b_1024_8ea8f97e` in one `update_collection_aliases` call, then ran a 16-question post-switch smoke check (passed) before recording the new/previous state. Final manifest status: `ACTIVE`.

## 6. Incremental sync verification (post-activation)

A new document (`new_after_migration.md`) was added to the corpus and synced via the unchanged `ingest_connector`, resolving the active collection through `kb_active` exactly as `app/wiring.py` does:

- `resolve_active_collection_name(...)` → `kb_active` (the alias, not a literal name)
- Sync result: `files_processed=1 chunks_upserted=1 files_skipped=4`
- The new chunk's dense vector in `kb_active` is **1024-dimensional** (qwen3-4b) — confirmed by direct point inspection
- `kb_chunks` (old nomic collection) remained at 51 points — the new document's vectors never touched it

## 7. Rollback drill (real)

| Step | Result |
|---|---|
| qwen3-4b active → `rollback` | alias repointed to `kb_chunks`; a real search for "How do I install the CLI?" against `kb_active` returned 5 correct, sensibly-scored nomic results |
| `rollback` again (symmetric swap) | alias repointed back to `kb_qwen3_4b_1024_8ea8f97e` — qwen3-4b active again |

Both collections (`kb_chunks`, `kb_qwen3_4b_1024_8ea8f97e`) remained intact throughout the entire drill — neither was deleted at any point, matching the no-premature-cleanup rule.

## 8. Operational sanity check

| Metric | Sprint 21 (historical) | This run (20-query sample) |
|---|---|---|
| Query embed p50/p95 | 295.8 / 326.5 ms | 258.1 / 265.1 ms |

No regression — this run's embedding latency is in the same range as Sprint 21's (variance expected from machine load, not a methodology-identical comparison; the retrieval-only figure wasn't measured on a directly comparable code path here and is omitted rather than reported misleadingly — see `docs/embedding-migration.md`).

## 9. Failure-injection coverage

Exercised as hermetic automated tests (`tests/test_embedding_migration.py`), not repeated against the real environment (would require deliberately breaking a real Docker/Ollama instance, which the plan documents as a known limitation): embedding/Qdrant failure during indexing, structural validation failures (doc count, chunk count, dimension, fingerprint, missing collection), post-switch smoke failure with automatic rollback, and no-rollback-target/refuse-to-delete-active-collection guards.

## 9.5. Production sync fingerprint patch (post-report follow-up)

The report above disclosed a limitation: `SyncManager` didn't pass a
`pipeline_fingerprint` into production `ingest_connector()` calls, so an
unchanged document synced under a stale (pre-migration) fingerprint
could be wrongly treated as healthy forever. This was fixed and verified
for real via the actual `/sync/filesystem` endpoint (not a direct
`ingest_connector` call):

- 1st post-migration sync: `files_processed=6, chunks_upserted=53` —
  every document still carrying data/registry.db's stale nomic-era
  fingerprint was re-embedded under the active qwen3-4b@1024 pipeline.
- 2nd sync immediately after: `files_processed=0, files_skipped=6` —
  steady state confirmed, no infinite re-embed loop.
- Every registry row's `pipeline_fingerprint` now equals the active
  fingerprint digest `8ea8f97e028fc4e1`.
- Every point in `kb_active` sampled at 1024 dimensions.
- `kb_chunks` (old nomic) point count unchanged at 51 throughout.

See `docs/embedding-migration.md`'s "Production sync fingerprint
enforcement" section and `tests/test_sync_manager_pipeline_fingerprint.py`
(5 new tests, all through `SyncManager.trigger_sync`, not direct
`ingest_connector` calls).

## 10. Final state

- **FINAL ACTIVE EMBEDDING:** qwen3-embedding:4b @ 1024 dimensions, served through `kb_active` → `kb_qwen3_4b_1024_8ea8f97e`
- **ROLLBACK STATE:** available — `kb_chunks` (nomic-embed-text@768) retained, untouched, previous-state pointer intact
- **PRODUCTION MIGRATION VERDICT:** SUCCESS
