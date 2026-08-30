# TechQA Reranker HOLDOUT50 One-Shot

This run consumed the frozen HOLDOUT50 for one paired ON/OFF experiment and stopped before semantic unblinding. Candidate identities are hidden in the review pack. The experiment has no promotion authority.

## Integrity

- Starting HEAD: `30df0be63349caeac4cb216b9fd2a5f36791eaa2`
- Dataset revision: `97808f3e5fd16ede40bbff6c2949af8139b2eb7b`
- HOLDOUT hash: `2833bc1c638e55f00ed5a58eb57d05382838ccc6ec0a47e39b13a496bc90abaa`
- Corpus fingerprint: `b7cb98f8ab85b40407d37c95b73e2a699d13802a1dfa1bdba8e1913bb194354f`
- Config fingerprint: `9cbc1286e802a526849bfb2e028ae0a570540658f72426bebf693f0d27434e87`
- Preregistration SHA256: `007019eb92ffb1000b65fcdd1692e0c1e32bbece3009d2d761c1ca6bd9c57350`
- Preregistered before HOLDOUT access: yes
- Post-access configuration changes: 0
- One-shot validity: `VALID` (35 genuine retryable rate-limit failures were retried; retrieval/evidence were not rerun)

## Calls

- Shared candidate retrieval executions: 50
- Query embeddings: 50
- BGE ON calls: 50
- BGE OFF calls: 0
- Luna official logical calls: 100 (50 ON + 50 OFF)
- Luna physical attempts: 135 (35 rate-limit retries)
- Preflight: 1 synthetic technical call
- Terra: 0

All latest logical generation records are complete: 50 ON and 50 OFF, with 0 provider failures. The initial 35 `OPENAI_RATE_LIMIT` responses were retained in `04-generation/attempts.jsonl`; only those failed logical keys were retried.

## Evidence completeness

Native holdout sentence annotations were available for 41/50 rows; 9 rows are explicitly unmapped. The scoring fields are derived after assembly and were not used for selection.

| Arm | Annotated | ANY | ALL | Mean recall | Budget exhausted | Mean context tokens |
|---|---:|---:|---:|---:|---:|---:|
| ON / BGE Top5 | 41 | 12 | 0 | 6.786% | 30 | 2257.37 |
| OFF / RRF Top5 | 41 | 11 | 0 | 6.312% | 32 | 2226.34 |

The experiment’s semantic decision must not be inferred from these evidence or visibility counts.

## Deterministic operational results

| Metric | ON | OFF |
|---|---:|---:|
| Valid application contracts | 50 | 50 |
| ANSWER | 6 | 6 |
| ABSTAIN | 44 | 44 |
| Visible | 6 | 6 |
| Self abstain | 43 | 44 |
| Forced abstain | 1 | 0 |
| Support-validation failures | 0 | 0 |
| Critical rejects | 1 | 2 |
| Citation-resolution failures | 0 | 0 |
| Unknown accepted | 0 | 0 |
| Cross-query accepted | 0 | 0 |
| Hidden accepted | 0 | 0 |
| Unauthorized accepted | 0 | 0 |

## Measured latency and cost

True full request E2E was not measured as a separate request. The following are measured stages; shared retrieval is not double-counted in the arm comparison.

| Stage | p50 ms | p95 ms | max ms |
|---|---:|---:|---:|
| Shared query embedding | 1130.414 | 2101.039 | 5799.849 |
| Shared sparse encoding | 8.684 | 40.769 | 68.298 |
| Shared hybrid retrieval | 93.786 | 273.131 | 492.051 |
| ON BGE reranking | 75882.409 | 198245.400 | 287556.297 |
| ON SectionAware | 335.332 | 920.009 | 1146.154 |
| OFF SectionAware | 87.860 | 229.845 | 549.021 |
| ON Luna | 1189.441 | 3013.684 | 4678.327 |
| OFF Luna | 1274.230 | 3210.670 | 3818.619 |

Historical only: BGE p50 was previously approximately 64.34 s/query and historical E2E approximately 68 s/query. This run measured BGE on HOLDOUT at p50 75.882 s/query.

Luna cost was `$0.0949984` ON and `$0.0921732` OFF; synthetic preflight cost was `$0.000132`; total provider cost was `$0.1873036`. Terra cost was `$0`.

## Blinding and stop condition

- Blind mapping seed: `20260831`; arm map is hashed and not exposed in the review pack.
- Blind review rows: 50
- Semantic fields blank: yes
- Arm identity leaked to review pack: no
- Semantic status: `PENDING_BLIND_REVIEW`
- Production configuration changed: no
- HOLDOUT semantic unblind: no

The final semantic decision is intentionally not computed in this run. Human review must fill `07-blind-review/blind-scorecard.csv` in a separate task. The HOLDOUT decision remains not authorized until that blinded scorecard is frozen and unblinded under the preregistered gate.
