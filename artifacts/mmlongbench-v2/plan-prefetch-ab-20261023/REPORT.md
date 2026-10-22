# Evidence plan alongside retrieval: paid A/B

23 October 2026, `gpt-6-luna`, `scripts/experiments/run_adaptive_trace.py --fast-path --evidence-needs`, one run per row and mode, run one at a time. Same branch and code in both modes; the only difference is `--plan-prefetch`. Each row ran with the prefetch off, then on.

| Row | Mode | Total s | Plan wait s | Planner call s | Requests | Input | Output | Answer |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 387 | off | 29.1 | 3.6 | 3.6 | 3 | 9,166 | 898 | Rick Scott |
| 387 | on | 23.1 | 0.0 | 2.8 | 3 | 9,163 | 1,029 | Rick Scott |
| 730 | off | 103.8 | 6.6 | 6.6 | 10 | 54,700 | 6,941 | No Boeing count in the excerpts (gold: not answerable) |
| 730 | on | 78.3 | 0.6 | 3.9 | 5 | 26,877 | 5,494 | `0 (calculation: 0 = 0)` |
| 1079 | off | 40.6 | 6.0 | 6.0 | 6 | 32,416 | 2,634 | 0.627 |
| 1079 | on | 32.5 | 0.0 | 5.4 | 6 | 36,696 | 2,036 | 0.627 |

"Plan wait" is the `research.requirements` span: how long the research run waited for its plan after retrieval. With the prefetch on, it fell to zero on 387 and 1079, and to 0.6 s on 730, where retrieval took 4.7 s and the planner 3.9 s after a late start. Total plan wait went from 16.2 s to 0.6 s over the three rows, about 5 s per question. The request count is unchanged on 387 and 1079. The plan is counted in the same budget, and `research.plan_started_early` is true in every prefetch run.

Total seconds are noisy (the model's latency varies between runs), so the plan wait is the cleaner measure. 730 is not a like-for-like total: the two runs took different paths (10 vs 5 requests).

## Row 730

Both modes produced the same plan: one `count` need for Tweets attributed to Boeing, with the same entity and metric constraints (the off run also kept a `unit` constraint). The paths split after that, in the quantity steps. The off run went on to reader and finalizer calls and explained that the excerpts give no Boeing figure. The on run's checker accepted an empty inventory, and the run released `0`, which scope validation passed. The planner request is the same in both modes (the question alone, the same role settings), so this looks like sampling variance downstream. One pair cannot prove that, though. All four earlier saved runs of 730 abstained. A count over an empty inventory being released as 0 for an unanswerable question is a separate correctness issue, whatever the prefetch does.

Tokens for the six runs: 169,018 input, 19,032 output.
