# Production RAG Pipeline v2 Closure

## Identity

```json
{
  "candidate_k": 20,
  "collection": "kb_eval_phase55_0175aa4a2f9b",
  "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
  "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
  "generator": "qwen3.5:4b",
  "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
  "num_ctx": 4096,
  "prompt": "v3",
  "retrieval_config_fingerprint": "4210b5315b906c5b9b01db126dc1ff7a3aca69a78a8a943c93cbd2e7e276849f",
  "think": false,
  "top_n": 5
}
```

## Implementation

Pipeline v2 is implemented behind `RAG_PIPELINE_V2=false`. The default v1 runtime remains available. V2 uses tenant-scoped section-aware evidence blocks, structured `answer_parts`, per-part strict validation, and a deterministic renderer. Rejected raw candidates remain evaluation-only.

## Corrected run

The first closure artifact was a preflight-defect run in which the provider did not honor the JSON contract. It is preserved historically. `closure-gate-results-budgeted-v1.jsonl` is the canonical corrected run after one permitted implementation correction (provider-native JSON schema plus explicit context budgeting). It used 10 generation calls.

Closure raw fully correct/complete: **7/10**. User-visible full success: **6/10**. Multi-document: **2/3**. Annotated fact evidence present: **16/20**.

## Full smoke

The corrected v2 path also completed the existing 36-query smoke using the cached retrieval inputs. It made 36 generation calls and zero retrieval, embedding, reranker, or semantic-gate calls. Gold-present answerable raw content was fully correct/complete for **15/22**; strict user-visible result was **11/22**; validator pass was **20/36**; raw candidates were observable for **36/36**.

The smoke is not a closure pass: ACL cases have no unauthorized leakage but unsupported answers remain possible under irrelevant authorized context, multi-document remains incomplete in one case, and citation identity/strict validation is not perfect. Development-200, calibration, and frozen test were not run.

## Decision

**PIPELINE_V2_GATE_FAIL_MIXED** / **SMOKE36_FAIL**. Do not promote v2 or lock configuration yet. Stop opening retrieval/model micro-experiments; the remaining blockers are bounded to citation behavior/contract observability, grounded abstention under irrelevant authorized context, and the residual generator quality ceiling.
