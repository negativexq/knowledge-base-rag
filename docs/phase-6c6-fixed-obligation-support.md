# Phase 6C.6 — Fixed-Obligation Support Evaluation

Phase 6C.6 separates the previous combined obligation task into two
experimental stages on the immutable 48-query balanced cache:

1. `query_obligation_extraction_v1` receives the user query only and extracts
   the minimal, bounded set of requested answer obligations.
2. `fixed_obligation_support_v1` receives those fixed obligations and the
   authorized top-five chunks, then returns support status per obligation.

The final `SUFFICIENT`/`INSUFFICIENT` result is calculated in Python: every
obligation must be `SUPPORTED`. A supported obligation must cite an authorized
chunk ID; an unsupported obligation must cite none. Scope failures, extraction
failures, support failures, retrieval failures, and deterministic ACL safety
are reported separately.

The existing `sufficiency_v1` implementation remains unchanged and is the
baseline. Query-scope decisions are reused from
`query_scope_query_only_v1`; ACL-negative and non-clear scope rows do not reach
the two new stages. The extractor never receives retrieved content, and the
support evaluator never receives retrieval scores or benchmark labels.

## Measured balanced-cache result

The run used `qwen3.5:4b`, `think=false`, candidate-k 20, top-n 5, and made no
retrieval, embedding, reranker, generation, calibration, or frozen-test calls.

| Metric | `sufficiency_v1` | fixed-obligation support |
|---|---:|---:|
| Sufficiency precision | 1.000 | 0.000 |
| Sufficiency recall | 0.538 | 0.000 |
| False sufficient | 0 | 0 |
| False insufficient | 6 | 1 |
| End-to-end ANSWER | 7 | 0 |
| Gold-present coverage | 7/20 | 0/20 |

Extraction was reliable (`24/24` first-pass, no parse or timeout failures),
but support output was valid on only `11/24` calls. The remaining 13 outputs
violated the support schema/status contract, predominantly by combining
`UNSUPPORTED` with supporting chunk IDs. This makes the candidate
`RELIABILITY_STILL_UNACCEPTABLE`; it is not a basis for runtime promotion.

## Artifacts and reproducibility

The reproducible runner is:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_fixed_obligation_support
```

It reads the fingerprint-validated cache at
`artifacts/phase-6/semantic-balanced-smoke/` and writes the component results,
failure attribution, reliability, latency, slice, transition, and
multi-document reports under `artifacts/phase-6/fixed-obligation-support/`.
The current artifact records the corpus and dataset fingerprints, collection,
retrieval identity, model, and prompt/schema versions.

The extraction component is promising as a separate boundary. The remaining
blocker is reliable support-only structured output and multi-obligation
support mapping; no runtime gate or default configuration was changed.
