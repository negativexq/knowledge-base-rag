# Phase 6C.1 semantic evaluator model smoke

Evaluated models: qwen3.5:4b, qwen2.5:3b-instruct, gemma2:2b

Skipped models: {}

Retrieval was cached once; evaluator-only runs performed zero retrieval, embedding, reranker, and generation calls. The evaluator prompts and schemas were unchanged across models.

## Results

| model | ambiguity F1 | sufficiency F1 | false answers | false abstains | gold-present coverage | total p95 ms | parse failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3.5:4b | 0.581 | 1.000 | 0/25 | 0/25 | 3/6 | 17478.5 | 0 |
| qwen2.5:3b-instruct | 0.000 | 0.526 | 9/25 | 0/25 | 5/6 | 18514.5 | 0 |
| gemma2:2b | 0.143 | 0.000 | 1/25 | 5/25 | 0/6 | 18131.9 | 0 |

## Recommendation

{"model": "qwen3.5:4b", "status": "SELECT_MODEL"}

The selection is a 25-query smoke recommendation only. It does not establish production accuracy and does not change ANSWERABILITY_EVAL_MODEL. qwen3:4b was not available locally and no model was pulled. The 7B/9B candidates were not evaluated in this first small-model round.
