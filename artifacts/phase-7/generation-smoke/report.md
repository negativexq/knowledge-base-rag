# Phase 7 Generation Smoke

Generation used the repository stream_answer path with strict v3 output validation.

Retrieval was cached once for 36 deterministic development queries. The cache contains only authorized top-5 chunks and is bound to corpus `0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7` and dataset `17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f`.

## Scope

- Retrieval identity: `4210b5315b906c5b9b01db126dc1ff7a3aca69a78a8a943c93cbd2e7e276849f`
- Generation model: `qwen3.5:4b`
- Prompt: `v3`
- Thinking: `False`
- Semantic Phase 6 gate: disabled and not invoked
- Calibration/frozen test/full development: not run

## Interpretation

Deterministic fact and citation checks are reported separately. Unsupported claim entailment, authority selection, and language appropriateness remain explicit manual-review dimensions; they are not silently converted into automated passes.

Summary: `MEASURED_SMOKE`

## Measured results

- Gold-present answerable: `22`
- Deterministic correctness: `3/22`
- Authored required-fact completeness: `3/22`
- Gold-present success: `not fully determinable`; claim-level entailment remains in manual review
- Citation-ID validity: `33/36`
- Citation support correctness: `7/25`
- Strict output validation: `29/36`
- Manual review records: `22`
- Generation latency p50/p95/max: `17131.788/49987.912/66069.072 ms`
- Retrieval, embedding, reranker, and semantic-gate calls during generation evaluation: `0`

The three complete multi-document records had all required evidence in the
cached authorized context; the generation result is reported separately from
the Phase 6 semantic-gate result (`0/3 ANSWER`). No old `qwen3:4b` generation
measurement exists, so this smoke establishes `qwen3.5:4b` as the new measured
baseline rather than an improvement claim.
