# Embedding Benchmark Sprint 19: Qwen3 Size & Dimension Trade-off

Multi-candidate, single-variable comparison — chunking, sparse encoding, RRF fusion, top_k/top_n, and reranker (off) identical across every config below. Same 68-question golden set as Sprint 18 (tests/fixtures/embedding_benchmark_golden.json), apples-to-apples. See results.json for full per-config, per-question data.

## Configurations tested

| Config | Supported | Dimension (requested/actual) |
|---|---|---|
| nomic@native | yes | 768 / 768 |
| qwen3-0.6b@native | yes | 1024 / 1024 |
| qwen3-4b@native | yes | 2560 / 2560 |
| qwen3-4b@1024 | yes | 1024 / 1024 |
| qwen3-0.6b@1024 | yes | 1024 / 1024 |
| qwen3-0.6b@768 | yes | 768 / 768 |

## Quality summary

| Config | TR→TR R@5 | EN→EN R@5 | TR→EN R@5 | EN→TR R@5 | Cross R@5 | Cross MRR | Mono R@5 | nDCG@5 |
|---|---|---|---|---|---|---|---|---|
| nomic@native | 1.000 | 1.000 | 0.625 | 0.588 | 0.607 | 0.418 | 1.000 | 0.726 |
| qwen3-0.6b@native | 1.000 | 1.000 | 0.938 | 0.882 | 0.910 | 0.696 | 1.000 | 0.864 |
| qwen3-4b@native | 1.000 | 1.000 | 1.000 | 0.941 | 0.971 | 0.782 | 1.000 | 0.910 |
| qwen3-4b@1024 | 1.000 | 1.000 | 1.000 | 0.941 | 0.971 | 0.755 | 1.000 | 0.905 |
| qwen3-0.6b@1024 | 1.000 | 1.000 | 0.938 | 0.882 | 0.910 | 0.710 | 1.000 | 0.869 |
| qwen3-0.6b@768 | 1.000 | 1.000 | 0.938 | 0.941 | 0.939 | 0.723 | 1.000 | 0.883 |

(TR→EN = Turkish query, English content. EN→TR = English query, Turkish content. Both cross-lingual. Cross R@5/MRR = mean of the two cross-lingual cells. Mono R@5 = mean of TR→TR and EN→EN.)

## Operational results

| Config | Dim | Index chunks/s | Index total (s) | Query p50/p95 (ms) | Retrieval p50/p95 (ms) | Load (s) | Storage (bytes, real/estimate) |
|---|---|---|---|---|---|---|---|
| nomic@native | 768 | 29.96 | 1.07 | 32.7/46.1 | 39.2/47.6 | 0.28131562494672835 | 2342912 (real) |
| qwen3-0.6b@native | 1024 | 11.50 | 2.78 | 121.0/134.0 | 99.2/106.8 | 0.40113966702483594 | 2424832 (real) |
| qwen3-4b@native | 2560 | 2.45 | 13.06 | 241.4/251.8 | 125.6/131.7 | 0.6623255830490962 | 2998272 (real) |
| qwen3-4b@1024 | 1024 | 2.46 | 13.01 | 249.2/265.7 | 132.2/142.2 | 0.6806481670355424 | 2555904 (real) |
| qwen3-0.6b@1024 | 1024 | 11.20 | 2.86 | 131.2/141.2 | 107.8/115.5 | 0.4621025420492515 | 2424832 (real) |
| qwen3-0.6b@768 | 768 | 11.48 | 2.79 | 130.0/139.3 | 106.6/112.7 | 0.39479233301244676 | 2375680 (real) |

RAM/VRAM: not measured for any configuration (see module docstring).

## Pareto frontier

A config is Pareto-dominated if another tested config is at least as good on cross-lingual Recall@5, cross-lingual MRR, query p95, AND dimension, and strictly better on at least one.

| Config | Dominated by |
|---|---|
| nomic@native | — (on the frontier) |
| qwen3-0.6b@native | — (on the frontier) |
| qwen3-4b@native | — (on the frontier) |
| qwen3-4b@1024 | — (on the frontier) |
| qwen3-0.6b@1024 | qwen3-0.6b@768 |
| qwen3-0.6b@768 | — (on the frontier) |

## Statistical caution

68 questions is a small sample — per-cell cells are 16-17 questions. No bootstrap confidence intervals were computed this sprint (documented as a limitation, not attempted under time pressure with a small deterministic n — see docs/PLANNING.md's Sprint 19 closing note). Treat deltas smaller than roughly 1 question's worth of a cell (~6%) as noise, not signal.

## Decision

**QUALITY WINNER: qwen3-4b@native**

**EFFICIENCY WINNER: qwen3-4b@1024**

Acceptance thresholds (vs. qwen3-4b@native): cross-lingual Recall@5 loss <= 0.05, cross-lingual MRR loss <= 0.05, mono-lingual Recall@5 regression <= 0.02.

Configs meeting acceptance thresholds: ['qwen3-4b@native', 'qwen3-4b@1024']

**PRODUCTION RECOMMENDATION:** Recommended next migration candidate: qwen3-4b@1024 — stays within acceptance thresholds of qwen3-4b@native (cross-lingual Recall@5/MRR loss <= 0.05, mono-lingual regression <= 0.02) at a real dimension/latency cost saving. nomic remains the current production default — this is a candidate for the next migration decision, not an applied change.

`settings.ollama_embed_model` is unchanged — nomic-embed-text remains the actual production default regardless of the recommendation above; switching it is a separate decision outside this sprint's scope.
