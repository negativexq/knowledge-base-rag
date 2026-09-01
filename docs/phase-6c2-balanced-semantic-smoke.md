# Phase 6C.2 — Balanced semantic evaluator validation smoke

This smoke validates the selected `qwen3.5:4b` semantic evaluator on a
deterministic 48-query development subset. The subset targets 20
`SHOULD_ANSWER`, 16 `SHOULD_ABSTAIN`, and 12 `SHOULD_CLARIFY` records and
includes standard, hard, cross-lingual, multi-document, version, injection,
ACL, unanswerable, and ambiguous cases.

Retrieval, tenant ACL, and BGE reranking are performed once while building
`artifacts/phase-6/semantic-balanced-smoke/evaluator-inputs.jsonl`. The
evaluator then consumes only the authorized cached top-five context. ACL
negative records are an offline safety slice and are excluded from semantic
model quality metrics; they must remain `ABSTAIN` without an evaluator call.

The smoke uses the fixed `ambiguity_v1` and `sufficiency_v1` prompts with
`think=false`. It does not modify runtime enforcement, prompts, defaults, the
calibration split, or the frozen test split. A high false-clarification rate or
failure on complete multi-document evidence is a blocker for the full 200-query
run, even when false-answer safety is perfect.

```bash
PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_balanced_semantic \
  --build-cache --build-cache-only \
  --collection kb_eval_phase55_0175aa4a2f9b

PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_balanced_semantic \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --model qwen3.5:4b
```
