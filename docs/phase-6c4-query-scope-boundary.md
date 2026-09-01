# Phase 6C.4 — Query-scope boundary redesign

Phase 6C.4 tests whether scope clarification should be decided from the user
query, rather than from retrieved evidence. It is an offline, shadow-only
experiment; runtime enforcement and the default evaluator prompt remain
unchanged.

## Boundary

The query-scope evaluator answers only:

> Does the user need to provide additional information before the intended
> request or scope can be selected?

It does not decide evidence sufficiency, authority, retrieval quality, or the
final answer. `REQUIRES_USER_INPUT` is reserved for a missing user constraint
such as `plan`, `region`, `channel`, `product`, `contract`, `date_or_version`,
`user_or_account`, `purchase_type`, `policy_scope`, or `other`.

The two new prompt versions are:

- `query_scope_query_only_v1`: query text only;
- `query_scope_compact_v1`: query text plus only runtime-safe applicability
  metadata when such metadata is actually available.

Neither arm receives retrieved chunk text, scores, source/chunk identifiers,
ground-truth labels, category, case family, or gold-presence fields. Missing
evidence, multiple documents, multi-part questions, and authority-resolvable
version coexistence are downstream concerns, not scope ambiguity.

## Reproducible comparison

The comparison reuses the exact 48-query balanced development cache from
Phase 6C.2. Retrieval, embedding, reranking, and answer generation are not
called while evaluating either arm. `sufficiency_v1` is unchanged and runs
only after a scope result of `SUFFICIENTLY_SCOPED`.

The current cache has no title, authority, or applicability fields. Therefore
the compact arm received an empty metadata list for all 48 records; this is an
intentional safe fallback, not benchmark-specific scope information.

Observed results:

| Metric | `ambiguity_v2` baseline | Query-only | Compact-scope |
|---|---:|---:|---:|
| Scope precision / recall / F1 | 0.375 / 1.000 / 0.545 | 0.563 / 0.750 / 0.643 | 0.400 / 1.000 / 0.571 |
| False clarifies (40 non-ACL rows) | 20 | 7 | 18 |
| Genuine ambiguities retained | 12/12 | 9/12 | 12/12 |
| SHOULD_ANSWER false clarifies | 12/20 | 7/20 | 17/20 |
| Gold-present answer coverage | 8/20 | 7/20 | 1/20 |
| False answers | 0/48 | 0/48 | 0/48 |

Query-only makes the boundary substantially less evidence-driven, but the
three complete multi-document cases still produce zero final answers because
`sufficiency_v1` rejects them. It also misses three genuine ambiguous cases.
Compact scope is not a winner: with no reliable compact metadata available it
behaves worse than query-only on usability and retains the same over-
clarification pattern.

The current committed baseline artifact contains 12 `SHOULD_ANSWER` rows whose
baseline action is `CLARIFY` (including `injection-03-0` and `version-01-1`).
The earlier Phase 6C.3 summary and the ten IDs called out for transition review
listed 10. The comparison preserves the artifact truth; the requested ten are
all present in `transition-analysis.json`, and the two additional rows are
reported rather than silently discarded.

## Decision

The winning input boundary is **query-only**. The primary diagnosis is
`SUFFICIENCY_BECOMES_BOTTLENECK`: the scope boundary improves on the baseline,
but downstream sufficiency limits gold-present coverage and complete
multi-document handling. This artifact does not promote a default prompt,
enable runtime gating, or start calibration. The next experiment should
address sufficiency behavior while preserving this boundary as a candidate.

Run the comparison with:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_query_scope_boundary \
  --cache-dir artifacts/phase-6/semantic-balanced-smoke \
  --output-dir artifacts/phase-6/query-scope-boundary \
  --collection kb_eval_phase55_0175aa4a2f9b
```

The machine-readable comparison and input-boundary audit are in
`artifacts/phase-6/query-scope-boundary/`.
