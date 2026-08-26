# Sprint 26 — Reranker benchmark

Decision rule was pre-committed before the run: a multilingual reranker may replace OFF only when cross-lingual Recall@5 and MRR are at least OFF, mono-lingual Recall@5 regression is <= 0.01, and latency cost is documented and acceptable. Existing English reranking is not a winner by default.

Dataset: `tests/fixtures/embedding_benchmark_golden_v2.json` · questions: 220 · fingerprint: `55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691`
Controls: Qwen3-Embedding-4B@1024 + BM25 sparse + Qdrant RRF · candidate k=20 · output n=5

Production recommendation: **ADOPT_MULTILINGUAL** · latency gate: total retrieval p95 <= 3000ms

## Cross-lingual results

| Config | TR→EN R@5 | EN→TR R@5 | Cross MRR | Cross nDCG@5 |
|---|---:|---:|---:|---:|
| off | 0.9259 | 0.9867 | 0.7448 | 0.7988 |
| existing | 0.2222 | 0.6800 | 0.3670 | 0.3880 |
| multilingual | 1.0000 | 1.0000 | 0.9558 | 0.9672 |

## Rescue / drop

| Config | rescued | dropped from top-5 | rescue rate | drop rate |
|---|---:|---:|---:|---:|
| off | 0 | 0 | None | None |
| existing | 1 | 85 | 0.0 | 0.4228855721393035 |
| multilingual | 63 | 0 | 1.0 | 0.0 |

## Operational notes

Reranker inference uses the local Python sentence-transformers backend. The production call is synchronous inside the async retrieval function, so CPU inference can block the event loop; this sprint measures the cost but does not refactor serving.

Memory/VRAM was not measured. A benchmark result is not a universal security or quality guarantee.
