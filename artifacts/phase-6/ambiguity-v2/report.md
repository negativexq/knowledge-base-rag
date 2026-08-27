# Phase 6C.3 ambiguity v2 comparison

The comparison reuses the exact 48-query authorized cache from Phase 6C.2.
Only the ambiguity prompt changed: `ambiguity_v1` versus
`ambiguity_v2`. Sufficiency remains `sufficiency_v1`.
No retrieval, embedding, reranker, generation, calibration, or frozen-test call
was made during the v2 run.

## Results

| Metric | v1 | v2 |
|---|---:|---:|
| Ambiguity precision | 0.387 | 0.375 |
| Ambiguity recall | 1.000 | 1.000 |
| Ambiguity F1 | 0.558 | 0.545 |
| False clarifies | 19 | 20 |
| Missed ambiguities | 0 | 0 |
| False answers | 0 | 0 |
| Gold-present coverage | 7/20 | 8/20 |


## SHOULD_ANSWER false-clarify transitions

The v1 baseline has 11 such records. Action transitions:
`{"CLARIFY->ANSWER": 1, "CLARIFY->CLARIFY": 10}`.
The full ID-level transition list is in `false-clarify-transitions.json`.
The SHOULD_ANSWER false-clarify count therefore changes from
11 to
10; the broader
combined false-clarify count changes from 19 to
20 because two non-answerable rows changed from
ABSTAIN to CLARIFY.

## Genuine ambiguity retention

v1 retained 12/12 genuine clarifications;
v2 retained 12/12.

## Multi-document complete cases

| | Ambiguity CLEAR | Sufficiency SUFFICIENT | Final ANSWER |
|---|---:|---:|---:|
| v1 | 0/3 | 0/3 | 0/3 |
| v2 | 0/3 | 0/3 | 0/3 |

The v1 prompt remains the default. This artifact is a comparison only; it does
not enable runtime enforcement or promote ambiguity_v2.
