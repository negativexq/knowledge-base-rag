# Embedding Benchmark: Nomic vs Qwen3-Embedding-4B

Single-variable comparison — chunking, sparse encoding, RRF fusion, top_k/top_n, and reranker (off) identical between rows. See results.json for full per-question data.

## Summary table

| Model | TR→TR Recall@5 | EN→EN Recall@5 | TR→EN Recall@5 | EN→TR Recall@5 | MRR | nDCG@5 | Retrieval p95 (ms) |
|---|---|---|---|---|---|---|---|
| nomic | 1.000 | 1.000 | 0.625 | 0.588 | 0.701 | 0.726 | 46.7 |
| qwen3-4b | 1.000 | 1.000 | 1.000 | 0.941 | 0.884 | 0.910 | 131.3 |

(TR→EN = Turkish query, English content — cross-lingual. EN→TR = English query, Turkish content — cross-lingual. TR→TR and EN→EN are mono-lingual.)

## Per-language-pair detail

| Model | Cell | Recall@1 | Recall@3 | Recall@5 | MRR | nDCG@5 | n |
|---|---|---|---|---|---|---|---|
| nomic | tr_query_tr_content | 0.938 | 1.000 | 1.000 | 0.969 | 0.977 | 16 |
| nomic | en_query_en_content | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 17 |
| nomic | en_query_tr_content | 0.375 | 0.562 | 0.625 | 0.474 | 0.512 | 16 |
| nomic | tr_query_en_content | 0.235 | 0.471 | 0.588 | 0.363 | 0.419 | 17 |
| qwen3-4b | tr_query_tr_content | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 16 |
| qwen3-4b | en_query_en_content | 0.941 | 1.000 | 1.000 | 0.971 | 0.978 | 17 |
| qwen3-4b | en_query_tr_content | 0.500 | 0.938 | 1.000 | 0.721 | 0.792 | 16 |
| qwen3-4b | tr_query_en_content | 0.765 | 0.941 | 0.941 | 0.843 | 0.868 | 17 |

## Operational metrics

| Metric | nomic | qwen3-4b |
|---|---|---|
| Embedding dimension | 768 | 2560 |
| Indexing throughput (chunks/sec) | 25.57 | 2.03 |
| Chunks indexed | 32 | 32 |
| Query embed p50 (ms) | 33.6 | 242.4 |
| Query embed p95 (ms) | 43.6 | 369.0 |
| Total retrieval p50 (ms) | 40.5 | 125.8 |
| Total retrieval p95 (ms) | 46.7 | 131.3 |
| Model load/warmup (s) | 0.537166207912378 | 3.4860997500363737 |
| Qdrant storage estimate (bytes) | 163840 | 393216 |
| RAM/VRAM usage | not measured | not measured |

## Decision

**Recommendation: ADOPT_QWEN3**

Both cross-lingual Recall@5 cells improved, cross-lingual MRR improved, and mono-lingual cells did not regress materially.

Cross-lingual Recall@5 deltas (challenger - baseline): {'tr_query_en_content': 0.3529411764705882, 'en_query_tr_content': 0.375}

Cross-lingual MRR deltas: {'tr_query_en_content': 0.48039215686274506, 'en_query_tr_content': 0.246875}

Mono-lingual Recall@5 deltas: {'tr_query_tr_content': 0.0, 'en_query_en_content': 0.0}
