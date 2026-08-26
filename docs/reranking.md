# Reranking decision — Sprint 26

Sprint 26 measured whether reranking improves the production retrieval path.
Generation, embeddings, chunking, corpus, ACL filters, BM25 sparse retrieval,
Qdrant RRF, candidate `k=20`, and output `n=5` were held constant. The primary
dataset is the unchanged 220-question multilingual golden set with fingerprint
`55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691`.

## Configurations

- `off`: hybrid Qwen3-Embedding-4B@1024 + BM25 + RRF, no reranker.
- `existing`: `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- `multilingual`: `BAAI/bge-reranker-v2-m3`, a multilingual reranker with
  standard Transformer/SentenceTransformer usage and local Python serving.
  Its model card identifies it as a roughly 0.6B-parameter multilingual
  reranker with an 8192-token maximum sequence length; this is materially
  heavier than the existing MiniLM model.

The challenger was selected from its official model card because it explicitly
describes multilingual reranking and recommends this model for multilingual
scenarios. The model is larger than MiniLM and therefore carries a measurable
latency cost. See the [official model card](https://huggingface.co/BAAI/bge-reranker-v2-m3).

## Decision rule and result

Before the full run, the production rule was fixed: adopt multilingual only if
cross-lingual Recall@5 and MRR are at least the OFF baseline, mono-lingual
Recall@5 regression is at most `0.01`, and total retrieval p95 is at most
`3000ms` in the measured serving configuration. Otherwise disable reranking.

The measured recommendation is `ADOPT_MULTILINGUAL`:

| Config | TR→EN R@5 | EN→TR R@5 | Cross MRR | Cross nDCG@5 | Total retrieval p95 |
|---|---:|---:|---:|---:|---:|
| OFF | 0.9259 | 0.9867 | 0.7448 | 0.7988 | 268.4 ms |
| Existing English | 0.2222 | 0.6800 | 0.3670 | 0.3880 | 453.0 ms |
| Multilingual BGE | 1.0000 | 1.0000 | 0.9558 | 0.9672 | 2457.7 ms |

The multilingual reranker had mono-lingual Recall@5 `1.0000` versus OFF
`1.0000`, cross-lingual Recall@5 `1.0000` versus `0.9563`, and 63 rescue
cases with zero drop-out cases. The English reranker dropped 85 expected
top-five cases and rescued one.

Rerank p50/p95 on the local CPU benchmark were `1956.6/2138.9ms` for BGE,
`140.1/162.8ms` for MiniLM, and not measured for OFF because no rerank stage
ran. Memory/VRAM was not measured. The production CrossEncoder call remains a
synchronous CPU/MPS call inside an async retrieval function; event-loop
offloading is a future operational improvement, not part of this sprint.

## Reproduction and artifacts

```bash
python -m scripts.benchmark_rerankers \
  --configs off existing multilingual \
  --output artifacts/reranker-benchmark-sprint26
```

The script builds/reuses a dedicated 51-chunk Qdrant benchmark collection and
never mutates the production collection. It writes `results.json`,
`paired-comparison.json` (5,000 iterations, fixed seed `2601`), `cases.json`,
and `report.md`. Per-question classification is:

- `rescued`: expected rank was outside top five or absent from the pre-rerank
  top five and enters top five after reranking;
- `unchanged`: rank is unchanged;
- `degraded`: expected result remains in top five but moves down;
- `dropped_out_of_top5`: it was in pre-rerank top five and is absent after.

## Limitations

This is a 220-question fixture benchmark, not a universal retrieval guarantee.
The BGE result was measured locally with Python SentenceTransformers on CPU for
consistent cells; production auto-selects the available local device, so live
concurrency and hardware-specific latency need continued monitoring. No
embedding, chunking, generation, or async serving redesign was performed.
