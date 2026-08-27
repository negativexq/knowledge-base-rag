# Phase 6C.4 query-scope boundary comparison

The exact 48-query authorized cache was reused. Baseline is the existing
`ambiguity_v2` run. Arm A sends only the query to
`query_scope_query_only_v1`. Arm B sends the query plus real
runtime-safe compact metadata to `query_scope_compact_v1`.

No retrieval, embedding, reranker, generation, calibration, or frozen-test
run was performed by the arm evaluator path. Sufficiency remains `sufficiency_v1`.

| Metric | Baseline v2 | Query-only | Compact-scope |
|---|---:|---:|---:|
| Scope/ambiguity F1 | 0.545 | 0.643 | 0.571 |
| False clarifies | 20 | 7 | 18 |
| SHOULD_ANSWER coverage | 8/20 | 7/20 | 1/20 |
| False answers | 0 | 0 | 0 |

Genuine ambiguity retention is reported in the JSON artifact. The current
cache contains `0`
records with compact authority/title/scope metadata, so Arm B falls back to an
empty compact metadata list when those fields are absent.

This is an offline boundary experiment only. Runtime prompt defaults and
runtime enforcement remain unchanged.

## Interpretation

Query-only is the winning input boundary in this experiment: it reduces
evidence-driven clarification on the current cache, while compact metadata
performs worse. The current baseline artifact has 12 `SHOULD_ANSWER` rows with
a baseline `CLARIFY` action, although the earlier summary named 10; both
additional IDs are retained in the transition analysis for auditability.

The boundary redesign does not unlock the complete multi-document cases.
Query-only marks 2/3 as sufficiently scoped, but `sufficiency_v1` marks 0/3
sufficient and the final answer count remains 0/3. The primary diagnosis is
`SUFFICIENCY_BECOMES_BOTTLENECK`.
