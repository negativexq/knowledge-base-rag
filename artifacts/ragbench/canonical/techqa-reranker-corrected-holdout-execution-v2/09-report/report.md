# TECHQA_RERANKER_CORRECTED_HOLDOUT_EXECUTION_V2

Status: `CORRECTED_HOLDOUT_EXECUTION_VALID`

This is not an untouched/pristine HOLDOUT. The original HOLDOUT was accessed and invalidated before semantic unblinding because it used a DEBUG50-only corpus. Amendment V2 authorized only correction of corpus scope.

## Integrity

- Starting HEAD: `30df0be63349caeac4cb216b9fd2a5f36791eaa2`
- Amendment V2 SHA256: `22da15d58b5e29bacd3a5593f0d40a14c9c81e84b54f69179341cbdf865326a4`
- Dataset revision: `97808f3e5fd16ede40bbff6c2949af8139b2eb7b`
- HOLDOUT hash: `2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa`
- Corrected corpus: `ragbench_techqa_corrected_holdout_v2_dd28bec092c22172`
- Source documents/chunks: 769 / 1116
- L0/L1: 41/41, 41/41
- Pre-retrieval gate: `PASS`

## Frozen comparison

- ON: shared RRF Top20 → BGE `BAAI/bge-reranker-v2-m3` → Top5 → SectionAware legacy budget 2400.
- OFF: shared RRF Top20 → direct RRF Top5 → SectionAware legacy budget 2400.
- Shared retrieval: 50 executions; query embeddings: 50; BGE OFF calls: 0.
- No chunking, embedding, retrieval weighting, Top-N, budget semantics, prompt, schema, validator, or production configuration changes.

## Evidence funnel (41 annotated rows)

| Stage | ANY | ALL | Mean recall | Budget exhausted |
|---|---:|---:|---:|---:|
| Shared RRF Top20 | 40/41 | 38/41 | 95.905% | — |
| ON BGE Top5 | 33/41 | 30/41 | 77.875% | — |
| OFF RRF Top5 | 37/41 | 32/41 | 85.054% | — |
| ON SectionAware | 33/41 | 30/41 | 77.875% | 21/41 |
| OFF SectionAware | 37/41 | 33/41 | 85.867% | 17/41 |

## Operational and security

| Metric | ON | OFF |
|---|---:|---:|
| Valid application contracts | 50/50 | 50/50 |
| Visible | 36/50 | 32/50 |
| Self abstain | 9/50 | 8/50 |
| Forced abstain | 5/50 | 10/50 |
| Critical rejects | 14 | 21 |
| Citation failures | 0 | 0 |

Unknown/cross-query/hidden/unauthorized support IDs accepted: `0` in both arms.

## Latency and cost

Measured stage timing is persisted in `07-latency-cost/latency-summary.json`; true separate arm E2E was not measured. ON BGE p50/p95/max: 98702.951 / 251399.467 / 293577.038 ms. Luna ON/OFF p50: 2624.953 / 2687.722 ms. Total provider cost: $0.2025214.

## Semantic boundary

All 100 official Luna outputs were frozen. No Terra, LLM judge, Codex semantic scoring, arm-map opening for interpretation, or semantic labels were produced. A new A/B blind map was created and hashed only after outputs were complete.

Semantic status: `PENDING_BLIND_REVIEW`.
