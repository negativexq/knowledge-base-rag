# Phase 6C.5 — Obligation-based evidence sufficiency

Phase 6C.5 evaluates an experimental sufficiency boundary that decomposes a
query into explicit obligations and requires every obligation to have
authorized, explicit support. It reuses the exact 48-query Phase 6C.4 cache
and the existing `query_scope_query_only_v1` decisions. Retrieval, embedding,
reranking, generation, calibration, and frozen-test execution are not part of
this run.

## Candidate contract

`obligation_sufficiency_v2` returns at most six obligations. Each obligation is
`SUPPORTED` or `UNSUPPORTED` and may cite only authorized top-k chunk IDs.
The final result is deterministic:

- all obligations `SUPPORTED` → `SUFFICIENT`;
- any `UNSUPPORTED` obligation → `INSUFFICIENT`;
- parse, timeout, or invalid citation → fail-safe `ABSTAIN`.

The model’s own final decision is retained for audit, but contradictions are
normalized from obligation statuses. `sufficiency_v1` remains unchanged and
is the comparison baseline.

## Result

| Metric | `sufficiency_v1` | Obligation v2 |
|---|---:|---:|
| Sufficiency precision / recall / F1 | 1.000 / 0.538 / 0.700 | 0.750 / 0.600 / 0.667 |
| All-gold-present sufficiency recall | 7/13 | 3/5 |
| End-to-end gold-present coverage | 7/20 | 3/20 |
| False sufficient | 0 | 1 |
| False answer | 0/48 | 1/48 |
| False clarify | 7/40 | 7/40 |

The v2 evaluator made 24 calls: 16 first-pass schema successes, 8 final parse
failures, 14 timeout events, 8 retries, and 2 invalid-obligation failures. The
v2 sufficiency p50/p95 was 13,068/60,030 ms, compared with
12,139/20,164 ms for v1.

The three complete multi-document records still produced 0/3 final answers.
One did not reach sufficiency because the reused query-scope result was
`REQUIRES_USER_INPUT`; the other two reached sufficiency but v2 failed safely
with evaluator errors. Therefore the proposed redesign did not demonstrate a
multi-document improvement.

## Decision

Status: **`SUFFICIENCY_TOO_PERMISSIVE`**.

The obligation structure is useful for explicit support maps and deterministic
aggregation, but this model/prompt combination is not safe enough to promote:
it introduced a false sufficient/false answer, over-decomposed some requests,
and had substantial timeout/parse instability. Runtime enforcement, default
sufficiency, query-scope behavior, and retrieval identity remain unchanged.

The next step should be a separately scoped sufficiency design iteration that
addresses obligation extraction discipline and structured-output reliability
before any runtime composition or calibration confirmation.

Artifacts are in `artifacts/phase-6/obligation-sufficiency/`.
