# Phase 6C.1 — Cache-first semantic evaluator model smoke

Phase 6C.1 compares local Ollama models without mixing evaluator latency with
retrieval latency. The reference retrieval identity is fixed at candidate
`k=20`, top `5`, Qwen3-Embedding-4B at 1024 dimensions, BM25+dense+RRF,
tenant ACL, and BAAI/bge-reranker-v2-m3.

## Two-stage flow

Stage A runs the real retrieval, ACL, and reranker path once for a deterministic
25-query development smoke set. It writes only authorized top-five context to
`artifacts/phase-6/semantic-model-smoke/evaluator-inputs.jsonl`. Cache metadata
binds those inputs to the corpus and dataset fingerprints, collection, and
retrieval configuration. A mismatch fails closed.

Stage B reads that cache and runs the fixed `ambiguity_v1` and `sufficiency_v1`
structured prompts against each requested evaluator model. It makes no Qdrant,
embedding, reranker, or answer-generation calls. Ambiguous cases short-circuit
the sufficiency call. Retrieved text is untrusted evidence, never instructions.

The smoke benchmark is a model-selection signal, not a production quality
estimate. The first round evaluates the small local candidates
`qwen3.5:4b`, `qwen2.5:3b-instruct`, and `gemma2:2b`. `qwen3:4b` is the
configured default for the semantic evaluator but is not pulled if it is not
installed locally. Larger local models are reserved for a subsequent explicit
round.

## Reproduce the stages

```bash
PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_semantic_models \
  --build-cache --build-cache-only \
  --collection kb_eval_phase55_0175aa4a2f9b

PYTHONPATH=. .venv/bin/python -m scripts.benchmarks.benchmark_semantic_models \
  --collection kb_eval_phase55_0175aa4a2f9b \
  --models qwen3.5:4b qwen2.5:3b-instruct gemma2:2b
```

The generated comparison records model availability, schema reliability,
false-answer safety, ambiguity/sufficiency quality, short-circuit savings,
latency, and the cache identity. This phase does not change
`ANSWERABILITY_EVAL_MODEL`, enable runtime enforcement, run the 200-query
development set, or touch calibration/frozen-test splits.
