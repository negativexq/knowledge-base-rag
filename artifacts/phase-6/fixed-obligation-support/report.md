# Phase 6C.6 fixed-obligation support

This experiment reuses the exact 48-record authorized cache and the exact
`query_scope_query_only_v1` decisions. `sufficiency_v1` is the baseline. The
candidate separates query-only obligation extraction from support-only checking
and deterministically aggregates the fixed support statuses. No retrieval,
embedding, reranking, generation, calibration, or frozen-test call was made.

## Metric comparison

| Metric | sufficiency_v1 | fixed-obligation support |
|---|---:|---:|
| Precision | 1.000 | 0.000 |
| Recall | 0.538 | 0.000 |
| F1 | 0.700 | 0.000 |
| False sufficient | 0 | 0 |
| False insufficient | 6 | 1 |
| End-to-end ANSWER | 7 | 0 |
| End-to-end false answers | 0 | 0 |
| Gold-present coverage | 7/20 | 0/20 |

## Reliability and attribution

The candidate separates `QUERY_SCOPE_FAILURE`, `OBLIGATION_EXTRACTION_FAILURE`,
`SUPPORT_EVALUATION_FAILURE`, `RETRIEVAL_FAILURE`, and deterministic safety.
Detailed counts are in `failure-attribution.json` and
`structured-reliability.json`. Candidate call-level details are split between
`extraction-results.jsonl` and `support-results.jsonl`.

## Multi-document

The complete multi-document cases and their obligation-to-chunk support maps
are in `multidoc-analysis.json`. A support decision is `SUFFICIENT` only when
every fixed obligation is `SUPPORTED`; no model-provided global decision is
trusted.

## Scope and safety

All support inputs are built from the authorized top-five context only. The
extractor receives the query only. ACL-negative records do not reach either
semantic stage. Runtime defaults, user-facing behavior, and `sufficiency_v1`
remain unchanged. This is an experimental Phase 6C.6 artifact.
