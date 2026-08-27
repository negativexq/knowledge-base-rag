# Phase 6C — Semantic answerability shadow evaluator

Phase 6C adds two independent, structured semantic observations after tenant
ACL, reranking, and top-five selection:

1. The ambiguity evaluator asks whether the query lacks a constraint needed to
   select one applicable rule (`CLEAR` or `AMBIGUOUS`).
2. The evidence-sufficiency evaluator asks whether the authorized context
   explicitly supports every requested part (`SUFFICIENT` or `INSUFFICIENT`).

The evaluator receives only the query and the already authorized top-five
chunks. Retrieval scores, labels, expected source IDs, tenant metadata, and
benchmark metadata are not semantic model inputs. Retrieved text is explicitly
treated as untrusted evidence, so commands or system overrides inside a
document are never instructions to the evaluator.

## Shadow policy

The combined observation is deterministic:

- `NO_RETRIEVAL_CANDIDATES`, `NO_AUTHORIZED_EVIDENCE`, and
  `EMPTY_RERANK_RESULT` produce `ABSTAIN` without an LLM call.
- `AMBIGUOUS` produces `CLARIFY`.
- `CLEAR` plus `SUFFICIENT` produces `ANSWER`.
- `CLEAR` plus `INSUFFICIENT` produces `ABSTAIN`.
- Transport, timeout, malformed JSON, and hallucinated supporting chunk IDs
  fail safe to `ABSTAIN` and are recorded as evaluator errors.

These actions are shadow observations only. `app/api/chat.py` still invokes
the existing generation path for every request, and the SSE retrieval report
gets an additive `semantic_answerability` field. No threshold, abstention, or
clarification is exposed to users in this phase.

The local evaluator defaults to `ANSWERABILITY_EVAL_MODEL=qwen3:4b`,
`think=false`, temperature zero, and one bounded retry. The model is separate
from the answer-generation setting even when both default to the same Ollama
model. Prompt versions are `ambiguity_v1` and `sufficiency_v1`.

## Configuration

The feature is disabled by default for backward-compatible startup:

```dotenv
SEMANTIC_ANSWERABILITY_ENABLED=false
SEMANTIC_ANSWERABILITY_SHADOW=true
ANSWERABILITY_EVAL_MODEL=qwen3:4b
ANSWERABILITY_EVAL_TIMEOUT_SECONDS=30
ANSWERABILITY_EVAL_RETRIES=1
```

Enabling it wires the evaluator into the real runtime, but it does not change
the answer returned by chat. The deterministic Phase 6A reasons remain
available in the existing answerability observation.

## Development-only export

The offline command uses the reference retrieval identity (candidate k=20,
top-n=5, Qwen3-Embedding-4B at 1024, BM25+dense+RRF, and BGE reranking). It
does not call answer generation:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.evaluate_semantic_answerability \
  --split development \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --limit 25 \
  --output artifacts/phase-6/semantic-answerability/smoke/development.jsonl
```

The default split is `development`. Calibration requires
`--allow-calibration`, and frozen test additionally requires
`--allow-frozen-test`; neither is part of Phase 6C development execution.
Outputs contain IDs, labels, safe counts, decisions, and bounded latency/error
metadata, not query text or document content.

The full development command is the same without `--limit 25`. It is a
retrieval plus two local structured-model calls per clear query and can be
slow on local hardware, so a smoke run should be checked first. No calibration
or frozen-test result is valid until a later explicit run.
