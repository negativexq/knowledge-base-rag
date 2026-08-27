# Phase 5.5 — Cross-Lingual Slice Closure

Only existing development and calibration artifacts were analyzed; no benchmark was rerun.

## Cross-lingual membership

The calibration `cross_lingual` category contains 20 queries.
It has 10 `tr->en` and 10 `en->tr` members; no other/mixed pair is present.
The category slice is not the same population as a global `language_pair` slice, which includes every category using that pair.

| Category/pair | k20 | k15 |
|---|---:|---:|
| cross_lingual / en->tr | 4/10 | 4/10 |
| cross_lingual / tr->en | 7/10 | 6/10 |
| cross_lingual total | 11/20 = 0.55 | 10/20 = 0.50 |

The apparent inconsistency is therefore population mismatch: the global `tr->en`/`en->tr` slices include non-cross-lingual records. In calibration, k15 loses one cross-lingual TR→EN hit but gains one non-cross-lingual TR→EN hard-answerable hit, keeping the global TR→EN value unchanged.

## Corrected comparison

| Metric | Dev k20 | Dev k15 | Δ | Cal k20 | Cal k15 | Δ |
|---|---:|---:|---:|---:|---:|---:|
| candidate recall | 0.973333 | 0.96 | -0.013333 | 0.963855 | 0.951807 | -0.012048 |
| all evidence recall | 0.973333 | 0.96 | -0.013333 | 0.963855 | 0.951807 | -0.012048 |
| R@5 | 0.88 | 0.88 | 0.0 | 0.819277 | 0.819277 | 0.0 |
| MRR | 0.601889 | 0.604889 | 0.003 | 0.665462 | 0.66747 | 0.002008 |
| nDCG@5 | 0.678009 | 0.681342 | 0.003333 | 0.705879 | 0.708522 | 0.002643 |
| family R@5 | 0.895299 | 0.895299 | 0.0 | 0.833333 | 0.873016 | 0.039683 |
| cross-lingual R@5 | 0.777778 | 0.777778 | 0.0 | 0.55 | 0.5 | -0.05 |
| TR→EN R@5 | 0.810811 | 0.810811 | 0.0 | 0.666667 | 0.666667 | 0.0 |
| EN→TR R@5 | 0.846154 | 0.846154 | 0.0 | 0.4 | 0.4 | 0.0 |
| multi-doc R@5 | 0.75 | 0.75 | 0.0 | 1.0 | 1.0 | 0.0 |
| hard R@5 | 0.9 | 0.9 | 0.0 | 0.888889 | 0.925926 | 0.037037 |
| version R@5 | 1.0 | 1.0 | 0.0 | 0.75 | 0.75 | 0.0 |
| injection R@5 | 1.0 | 1.0 | 0.0 | 1.0 | 1.0 | 0.0 |
| reranker p95 ms | 4119.52 | 3162.124 | -957.396 | 4498.699 | 3092.892 | -1405.807 |
| total p95 ms | 4128.292 | 3170.15 | -958.142 | 4505.472 | 3100.745 | -1404.727 |
| actual pairs | 4000 | 3000 | -1000 | 2240 | 1680 | -560 |

## Changed queries

Development: 1 k20-hit/k15-miss and 1 k20-miss/k15-hit.
Calibration: 1 k20-hit/k15-miss and 1 k20-miss/k15-hit.
See `changed-query-analysis.json` for IDs, ranks, source IDs, and family impact.

## nDCG integrity

The old approximately 0.99 values were invalid because duplicate chunks from one source received duplicate DCG credit. Corrected source-level first-occurrence nDCG is development k20 `0.678009`, k15 `0.681342`; calibration k20 `0.705879`, k15 `0.708522`. All corrected values are <= 1.

| Query | Unique ranked top-5 | DCG | IDCG | nDCG |
|---|---|---:|---:|---:|
| cross-19-0 (k20) | regional-returns-tr, returns-manual-tr, regional-returns-eu | 0.5 | 1.0 | 0.5 |
| cross-19-0 (k15) | regional-returns-tr, returns-manual-tr | 0 | 1.0 | 0.0 |
| hard-activation-evidence (k20) | long-policy-tr | 0 | 1.0 | 0.0 |
| hard-activation-evidence (k15) | long-policy-tr, digital-goods-policy | 0.63093 | 1.0 | 0.63093 |

## Decision

QUALITY_REFERENCE = candidate_k 20. DEV_FAST = candidate_k 15 is supported for local iteration because it reduces reranker p95 by approximately 31% while preserving overall R@5, but it is not suitable as the global quality reference because calibration cross-lingual R@5 falls from 11/20 to 10/20.
Family aggregation is family-balanced: the six-query `fact-19` family loses 1/6 while the one-query `hard-activation-evidence` family gains 1/1. Across 21 answerable families, that net change is (1 - 1/6) / 21 = 0.039683, explaining the family-level increase.

Phase 5.5 is closed: QUALITY_REFERENCE=20, DEV_FAST=15.

The global/reference default remains 20; only the DEV_FAST profile uses 15. Frozen test and generation were not run.
