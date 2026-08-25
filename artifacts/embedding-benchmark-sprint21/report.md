# Embedding Benchmark Sprint 21: Non-Inferiority & Stability Decision

Dataset fingerprint: `55e857db9c7b9ad1ccb4ca2ee3286498abc818f100cebd24bb94d38e39942691`

Corpus fingerprint: `42b21bb06bb36881b45b507aeb397d5148157e8e16873e7ef10c7e80367e3850`

Only 2 configurations tested this sprint: qwen3-0.6b@768 (efficiency candidate), qwen3-4b@1024 (quality candidate). nomic@768 shown below as a historical reference from Sprint 20 only — not re-benchmarked.

## Embedding nondeterminism (bit-level) vs. ranking impact

Floating-point nondeterminism in the embedding backend is NOT the same thing as retrieval-level instability — a vector can differ slightly between repeated calls while every top-k ranking it produces stays identical. Both are measured and reported separately below.

| Config | Max abs vector delta | Mean abs delta | Mean cosine sim | Top1 flip rate | Top3 set change | Top5 set change | MRR-impacting flips | Recall@5-impacting flips |
|---|---|---|---|---|---|---|---|---|
| qwen3-0.6b@768 | 1.66e-04 | 1.69e-05 | 1.000000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| qwen3-4b@1024 | 8.45e-04 | 1.19e-04 | 0.999988 | 0.000 | 0.000 | 0.020 | 0.000 | 0.000 |

(n=50 stratified queries x 10 repeated live embeddings each.)

## Retrieval determinism (frozen embeddings, Qdrant/RRF only)

| Config | Questions checked | Repeats | Unstable questions | Fully deterministic? |
|---|---|---|---|---|
| qwen3-0.6b@768 | 208 | 5 | 0 | True |
| qwen3-4b@1024 | 208 | 5 | 0 | True |

## Run-to-run distributions (10 independent live runs per config)

| Config | Metric | Mean | Median | Stddev | Min | Max | P5 | P95 |
|---|---|---|---|---|---|---|---|---|
| qwen3-0.6b@768 | cross_lingual_recall_at_5 | 0.9064 | 0.9064 | 0.0000 | 0.9064 | 0.9064 | 0.9064 | 0.9064 |
| qwen3-0.6b@768 | cross_lingual_mrr | 0.6940 | 0.6940 | 0.0000 | 0.6940 | 0.6940 | 0.6940 | 0.6940 |
| qwen3-0.6b@768 | ndcg_at_5 | 0.8001 | 0.8001 | 0.0000 | 0.8001 | 0.8001 | 0.8001 | 0.8001 |
| qwen3-4b@1024 | cross_lingual_recall_at_5 | 0.9630 | 0.9630 | 0.0000 | 0.9630 | 0.9630 | 0.9630 | 0.9630 |
| qwen3-4b@1024 | cross_lingual_mrr | 0.7336 | 0.7336 | 0.0000 | 0.7336 | 0.7336 | 0.7336 | 0.7336 |
| qwen3-4b@1024 | ndcg_at_5 | 0.8362 | 0.8362 | 0.0000 | 0.8362 | 0.8362 | 0.8362 | 0.8362 |

## Operational comparison

| Config | Dim | Query p50/p95 (ms) | Retrieval p50/p95 (ms) | Index chunks/s | Storage (bytes) |
|---|---|---|---|---|---|
| qwen3-0.6b@768 | 768 | 125.8/136.4 | 7.6/8.9 | 12.85 | 2551808 (real) |
| qwen3-4b@1024 | 1024 | 295.8/326.5 | 9.1/11.9 | 2.53 | 2793472 (real) |

Historical reference (Sprint 20, NOT re-benchmarked): nomic@768 query p95 ~43ms, dimension 768. Note: qwen3-4b@1024's smaller dimension reduces Qdrant storage/index footprint vs. qwen3-4b@native, but the underlying model is STILL the 4B-parameter model — its embedding INFERENCE latency does not drop to 0.6B levels just because the output vector was truncated. qwen3-0.6b@768 is a genuinely different, smaller model, so it differs in BOTH inference compute AND vector dimension — these are two independent cost axes, not one.

## Pre-committed non-inferiority results

delta = qwen3-4b@1024 - qwen3-0.6b@768 (positive = large scored higher). Non-inferior iff the CI's UPPER bound stays under the margin.

| Metric | Subset | Margin | Observed delta | CI lower | CI upper | Non-inferior? |
|---|---|---|---|---|---|---|
| recall_at_5 | cross_lingual | 0.04 | 0.0577 | 0.0128 | 0.1026 | False |
| mrr | cross_lingual | 0.04 | 0.0409 | 0.0111 | 0.0726 | False |
| recall_at_5 | mono_lingual | 0.02 | 0.0192 | 0.0000 | 0.0577 | False |

## Power analysis

Current cross-lingual n: 156. Observed paired stddev: 0.2838. Estimated n needed for 80% power: 312. For 90% power: 432.

Normal approximation for a one-sided non-inferiority test: n = ((z_alpha + z_power) * sigma / margin)^2, using the OBSERVED paired per-question delta standard deviation as sigma.

Limitations: Per-question Recall@5 is a near-binary paired outcome, not continuous — this is a standard but approximate normal-approximation formula, not an exact binomial/McNemar power calculation. The observed stddev is itself a single-sample estimate (its own uncertainty is not propagated). Treat the required-n figures as an order-of-magnitude guide, not a precise target.

## Production decision

**Verdict: ADOPT_QWEN3_4B_1024**

qwen3-4b@1024's advantage over qwen3-0.6b@768 on recall_at_5 is both statistically confident (CI lower bound 0.0128 > 0) and practically material (observed delta 0.0577 > 0.04).

`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the actual production default. This is a decision sprint; an actual migration is a separate, later action.
