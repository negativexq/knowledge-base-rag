# Phase 5.5 — Local runtime and retrieval optimization

This phase separates local interactive generation settings from controlled
retrieval measurements. It does not change the embedding model, the hybrid
retrieval method, the BGE model, tenant ACL, or the production `20 → 5`
reference configuration.

## Profiles

Historical note: the Phase 5.5 measurements recorded `qwen3:4b` as the
local generation model. The current Phase 7 local generation baseline is
`qwen3.5:4b`; retrieval measurements and the reference retrieval profile are
unchanged.

`DEV_FAST` is the local interactive profile:

- Ollama generation model: `qwen3.5:4b` (current baseline)
- Ollama thinking: `false`
- Qwen3-Embedding-4B at 1024 dimensions
- BGE reranking with `top_n=5`
- candidate count: `15` for faster local iteration

`BENCHMARK_REFERENCE` is used by the candidate sweep. Generation is not
constructed or invoked. It fixes Qwen3-Embedding-4B at 1024, BM25 + dense +
RRF, `BAAI/bge-reranker-v2-m3`, `candidate_k=20`, `top_n=5`, STRICT security,
and the current `kb_active` retrieval path. `15` is now the measured DEV_FAST
local budget; `10` remains rejected for reference comparisons; the
global/reference value is `20`.

Optimization decisions are promoted only after quality and latency
measurement. Phase 5.5 is closed with `DEV_FAST=15` and
`BENCHMARK_REFERENCE=20`; the global/reference default remains 20.

## Candidate sweep

Run a deterministic development-only smoke or full pass against the isolated,
fingerprint-validated Qdrant collection:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.benchmark_candidate_k \
  --split development --candidate-k 20 15 10 --limit 20 \
  --qdrant-url http://localhost:6333 \
  --ollama-url http://localhost:11434 \
  --collection kb_eval_phase55_<corpus-fingerprint-prefix>
```

The default split is `development`. `calibration` requires an explicit split;
`frozen_test` additionally requires `--allow-frozen-test` and is intentionally
not used in this phase. The command is read-only for Qdrant and writes only
`artifacts/phase-5-5/candidate-sweep.json` and its CSV summary.

The JSON reports pre-rerank candidate recall, all/any required evidence for
multi-document questions, post-rerank Recall@5/MRR/nDCG@5, rescue/drop counts,
query-level and case-family-level means, category/language/tenant/
answerability/difficulty slices, and retrieval/reranker/total latency
percentiles. A rescue enters the post-rerank top five after being absent from
the pre-rerank top five; a drop is present before reranking and absent after.
Expected labels are source-level while retrieval returns chunks, so nDCG
de-duplicates repeated chunks from the same source at their first ranked
occurrence before applying the standard logarithmic discount. MRR retains the
existing chunk-rank semantics, and no relevant hit scores zero.

The synchronous CrossEncoder call is isolated with `asyncio.to_thread()` in
`app/reranker/cross_encoder.py::CrossEncoderReranker.async_rerank`, guarded by
`RERANKER_MAX_CONCURRENCY` (default `1`). `app/retrieval/search.py::search`
uses that bounded path. ACL filtering still occurs in Qdrant before the
reranker sees any candidate. The benchmark has no chat-provider call, so there
is no generation model to unload during a retrieval-only run.
