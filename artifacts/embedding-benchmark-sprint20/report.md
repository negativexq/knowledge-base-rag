# Embedding Benchmark Sprint 20: Stability & Production Decision

Multi-candidate, single-variable comparison — chunking, sparse encoding, RRF fusion, top_k/top_n, and reranker (off) identical across every config below. 220-question golden set (Sprint 20 expansion) (tests/fixtures/embedding_benchmark_golden_v2.json), apples-to-apples. See results.json for full per-config, per-question data.

## Configurations tested

| Config | Supported | Dimension (requested/actual) |
|---|---|---|
| nomic@768 | yes | 768 / 768 |
| qwen3-0.6b@768 | yes | 768 / 768 |
| qwen3-4b@1024 | yes | 1024 / 1024 |

## Quality summary

| Config | TR→TR R@5 | EN→EN R@5 | TR→EN R@5 | EN→TR R@5 | Cross R@5 | Cross MRR | Mono R@5 | nDCG@5 |
|---|---|---|---|---|---|---|---|---|
| nomic@768 | 0.840 | 1.000 | 0.707 | 0.432 | 0.569 | 0.416 | 0.920 | 0.555 |
| qwen3-0.6b@768 | 0.960 | 1.000 | 0.973 | 0.840 | 0.906 | 0.699 | 0.980 | 0.803 |
| qwen3-4b@1024 | 1.000 | 1.000 | 1.000 | 0.926 | 0.963 | 0.744 | 1.000 | 0.842 |

(TR→EN = Turkish query, English content. EN→TR = English query, Turkish content. Both cross-lingual. Cross R@5/MRR = mean of the two cross-lingual cells. Mono R@5 = mean of TR→TR and EN→EN.)

## Operational results

| Config | Dim | Index chunks/s | Index total (s) | Query p50/p95 (ms) | Retrieval p50/p95 (ms) | Load (s) | Storage (bytes, real/estimate) |
|---|---|---|---|---|---|---|---|
| nomic@768 | 768 | 39.92 | 1.28 | 34.3/43.3 | 40.7/48.3 | 0.2659406670136377 | 2539520 (real) |
| qwen3-0.6b@768 | 768 | 12.00 | 4.25 | 130.2/140.6 | 107.8/120.2 | 0.5259275420103222 | 2564096 (real) |
| qwen3-4b@1024 | 1024 | 2.48 | 20.61 | 248.6/258.7 | 132.4/140.4 | 0.6994867500616238 | 2793472 (real) |

RAM/VRAM: not measured for any configuration (see module docstring).

## Pareto frontier

A config is Pareto-dominated if another tested config is at least as good on cross-lingual Recall@5, cross-lingual MRR, query p95, AND dimension, and strictly better on at least one.

| Config | Dominated by |
|---|---|
| nomic@768 | — (on the frontier) |
| qwen3-0.6b@768 | — (on the frontier) |
| qwen3-4b@1024 | — (on the frontier) |

## Statistical caution

220 questions is still a modest sample for a small quality gap between two close configs — paired bootstrap confidence intervals (see below) are the primary tool for judging whether an observed delta is distinguishable from noise at this size, rather than a fixed rule-of-thumb threshold.

## Decision

**QUALITY WINNER: qwen3-4b@1024**

**EFFICIENCY WINNER: none met acceptance thresholds**

Acceptance thresholds (vs. qwen3-4b@native): cross-lingual Recall@5 loss <= 0.05, cross-lingual MRR loss <= 0.05, mono-lingual Recall@5 regression <= 0.02.

Configs meeting acceptance thresholds: []

**PRODUCTION RECOMMENDATION:** No configuration met the acceptance thresholds relative to the quality ceiling (qwen3-4b@native) — NEED MORE DATA / no smaller-config recommendation. nomic remains the current production default.

`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the actual production default regardless of the recommendation above; switching it is a separate decision outside this sprint's scope.

## Paired bootstrap confidence intervals

Compared: qwen3-0.6b@768 (a) vs qwen3-4b@1024 (b), delta = a - b

| Subset | Metric | Observed delta | 95% CI lower | 95% CI upper | n | seed | iterations |
|---|---|---|---|---|---|---|---|
| overall | recall_at_1 | -0.0192 | -0.0577 | 0.0192 | 208 | 20200601 | 5000 |
| overall | recall_at_3 | -0.0673 | -0.1106 | -0.0288 | 208 | 20200601 | 5000 |
| overall | recall_at_5 | -0.0481 | -0.0817 | -0.0144 | 208 | 20200601 | 5000 |
| overall | mrr | -0.0363 | -0.0645 | -0.0090 | 208 | 20200601 | 5000 |
| overall | ndcg_at_5 | -0.0396 | -0.0661 | -0.0133 | 208 | 20200601 | 5000 |
| cross_lingual | recall_at_1 | -0.0256 | -0.0705 | 0.0128 | 156 | 20200601 | 5000 |
| cross_lingual | recall_at_3 | -0.0897 | -0.1410 | -0.0385 | 156 | 20200601 | 5000 |
| cross_lingual | recall_at_5 | -0.0577 | -0.1026 | -0.0128 | 156 | 20200601 | 5000 |
| cross_lingual | mrr | -0.0468 | -0.0814 | -0.0145 | 156 | 20200601 | 5000 |
| cross_lingual | ndcg_at_5 | -0.0500 | -0.0837 | -0.0187 | 156 | 20200601 | 5000 |
| mono_lingual | recall_at_1 | 0.0000 | -0.0769 | 0.0769 | 52 | 20200601 | 5000 |
| mono_lingual | recall_at_3 | 0.0000 | 0.0000 | 0.0000 | 52 | 20200601 | 5000 |
| mono_lingual | recall_at_5 | -0.0192 | -0.0577 | 0.0000 | 52 | 20200601 | 5000 |
| mono_lingual | mrr | -0.0048 | -0.0433 | 0.0337 | 52 | 20200601 | 5000 |
| mono_lingual | ndcg_at_5 | -0.0083 | -0.0438 | 0.0213 | 52 | 20200601 | 5000 |

(A CI entirely above or below zero indicates the sign of the difference is not attributable to chance at this sample size — see the Statistical caution section for what this does and doesn't imply at n≈220.)

## Sprint 20 production decision

**QUALITY WINNER: qwen3-4b@1024**

**EFFICIENCY WINNER: qwen3-0.6b@768**

**PRODUCTION WINNER: NEED_MORE_DATA**

The point-estimate loss and the bootstrap CI disagree on whether the quality gap is within tolerance — the 220-question dataset does not give a confident answer either direction for this comparison.

Loss (large - small) vs {'max_cross_recall_at_5_loss': 0.03, 'max_cross_mrr_loss': 0.04, 'max_mono_recall_at_5_loss': 0.01}: {'cross_recall_at_5': 0.056543209876543266, 'cross_mrr': 0.04520164609053512, 'mono_recall_at_5': 0.020000000000000018}

Within tolerance: False. CI confirms material gap: False.
