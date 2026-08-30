# TECHQA HOLDOUT Measurement Validity Audit V1

## Status

`EXECUTION_COMPLETED / MEASUREMENT_VALIDITY_UNDER_INVESTIGATION`

HOLDOUT content was accessed in the original one-shot run. Semantic review has not started, the arm map has not been opened, and no corrected HOLDOUT execution was run.

## Primary discriminating test

The HOLDOUT scorer/matcher was replayed on frozen DEBUG evidence without retrieval, embedding, reranking, generation, or judging.

| Condition | Canonical ANY | Replay ANY | Canonical ALL | Replay ALL | Canonical recall | Replay recall | Mapping differences |
|---|---:|---:|---:|---:|---:|---:|---:|
| ON | 36/38 | 36/38 | 29/38 | 29/38 | 87.95% | 87.95% | 0 |
| OFF | 37/38 | 37/38 | 32/38 | 32/38 | 92.05% | 92.05% | 0 |

Result: `MATCH`. The HOLDOUT scorer path reproduces the known DEBUG scorer; a generic scorer defect is not supported.

### Annotation-key audit

The prior named DEBUG key cases are not equivalent: `Q016:1f` has a sentence object but is absent from both persisted arm evidence payloads (an evidence-presence miss), while `Q270:1zaa` is absent from the sentence-object map. The replay follows the canonical denominator and maps both arms identically; this does not indicate a scorer mismatch. The HOLDOUT sample has 9 rows without usable native annotation keys.

## HOLDOUT corpus coverage

The original index contains 246 source documents and 372 chunks. The HOLDOUT rows reference 248 unique source documents, but only 2 non-gold source documents intersect the DEBUG index. For the 41 annotated HOLDOUT rows:

- Gold relevant source/document in indexed corpus: **0/41**
- Annotation mapped to indexed corpus chunk: **0/41**
- RRF Top20 ANY/ALL: **14/41 / 0/41**
- BGE Top5 ANY/ALL: **12/41 / 0/41**
- RRF Top5 ANY/ALL: **11/41 / 0/41**
- ON SectionAware ANY/ALL: **12/41 / 0/41**
- OFF SectionAware ANY/ALL: **11/41 / 0/41**

The first failure stage is `CORPUS_MISSING` for all 41 annotated rows. The apparent nonzero ANY counts are incidental text matches against unrelated indexed documents and cannot establish gold-source retrieval survival when L0 is false.

Five budget-exhausted / zero-recall examples with source and evidence excerpts are in `03-holdout-corpus-coverage/zero-recall-samples.md`.

## Root cause and validity

This is an outcome-independent, arm-symmetric `HOLDOUT_DATA_OR_CORPUS_SCOPE_MISMATCH`. The original HOLDOUT evidence metrics are invalid for ON-vs-OFF architecture comparison. The original semantic blind review should not proceed as an architecture verdict because both arms were generated over the wrong corpus scope.

Unrelated instrumentation remains technically usable, with scope limits: measured BGE latency, Luna latency, provider cost/retry observations, and deterministic security counters do not depend on gold annotation recognition. They do not rescue the evidence or semantic architecture decision.

## Amendment

Because the invalidating defect is proven, a correction amendment was created at `05-amendment/preregistration-amendment-v1.json` and hashed before any corrected rerun. No corrected rerun was executed. The amendment requires the exact pinned TechQA source scope needed by HOLDOUT, while retaining candidate_k=20, top_n=5, legacy budget=2400, identical ON/OFF downstream behavior, and the no-tuning/blinded-review protocol.

## Guardrails

- New retrieval/embedding/BGE/Luna/Terra calls: 0
- Blind arm map opened: no
- Blind scorecard filled: no
- Production or RAG architecture changed: no
- Historical artifacts modified: no
- Corrected HOLDOUT execution: no
