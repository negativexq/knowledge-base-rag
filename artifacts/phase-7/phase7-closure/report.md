# Phase 7 Final Closure

## Formal result

The historical 2 better / 2 worse / 4 equivalent result is invalid for the final paired decision because V2.2 did not record `num_predict`, while V2.3 used 1024. The corrected symmetric run retained the frozen eight queries and seeds and used `num_predict=1024` for both arms.

The corrected result is 0 clearly better, 3 clearly worse, and 5 equivalent/unstable. The formal gate is `CLEAR_REGRESSION`; the selected closure pipeline is `pipeline_v2_2_evidence_backed`.

## multi-01-0

All five corrected V2.3 records completed HTTP 200, but no finish/done reason or eval count was persisted. Therefore each seed is `INDETERMINATE`, not proven or supported truncation. The query verdict is unchanged.

## V2.3 limitation

The evaluated V2.3 support-unit implementation produced no correctly-attributed visible answers across the corrected 40-run paired holdout execution and showed materially higher false-abstention and latency. The preregistered debug-set reproduction step was not executed, so this evaluation cannot distinguish whether the observed failure was caused by the support-unit contract itself or by its current implementation/validator interaction. No holdout-driven fix was attempted and no additional architecture experiment was opened.

## Selected V2.2 limitation

Under corrected symmetric execution, V2.2 produced 15/40 correctly attributed and 10/40 misattributed visible answers; 40% of the attributed/misattributed set was misattributed. Citation identity is deterministic and tenant ACLs are enforced, but semantic claim-to-evidence alignment is not guaranteed.

The development split contains 12 multi-document queries. After the initial eight holdout queries and three debug queries, only one eligible unseen development multi-document query remained, so the preregistered +8 extension was impossible without violating split policy. Calibration and frozen test were untouched.

## Provider findings

1. Stale Ollama llama-server runner state caused requests to stall; model unload and controlled service restart restored inference health.
2. Constrained structured generation showed output-length pathology and severe tail latency in V2.3; bounding generation with `num_predict=1024` stabilized execution without changing RAG retrieval.

Smoke36 is run only after the closure commit, with the exact frozen V2.2 fingerprint.
