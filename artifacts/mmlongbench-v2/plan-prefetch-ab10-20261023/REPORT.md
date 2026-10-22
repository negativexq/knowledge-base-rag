# Evidence plan alongside retrieval: paid A/B on ten more rows

23 October 2026, `gpt-6-luna`, `scripts/experiments/run_adaptive_trace.py --fast-path --evidence-needs`. Same branch and code in both modes; the only difference is `--plan-prefetch`. Each row ran once with the prefetch off, then once with it on, one run at a time. The rows are different from the [first three](../plan-prefetch-ab-20261023/REPORT.md), and each comes from a different document.

| Row | Kind | Plan wait off → on (s) | Total off → on (s) | Requests off → on | Off answer | On answer | Gold |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 210 | survey percentage | 10.8 → 1.3 | 67.1 → 79.5 | 9 → 9 | insufficient evidence | 21% | 21% |
| 370 | lookup | 8.8 → 0.0 | 29.2 → 16.6 | 3 → 3 | S.V. Shanbhag | S.V. Shanbhag | S.V. Shanbhag |
| 383 | lookup | 5.0 → 0.0 | 22.5 → 16.7 | 3 → 3 | Florida Dept. of Health | same | same |
| 471 | not answerable | 4.7 → 0.0 | 59.0 → 91.2 | 9 → 9 | insufficient evidence | insufficient evidence | not answerable |
| 472 | lookup | 3.6 → 0.0 | 18.5 → 17.1 | 3 → 3 | 16 | 16 grams | 16 |
| 509 | count | 2.2 → 0.0 | 45.5 → 37.5 | 5 → 5 | 4 | 4 | 4 |
| 659 | visual lookup | 4.3 → 0.0 | 25.6 → 23.9 | 3 → 3 | P1.1 | P1.1 | P1.1 |
| 727 | calculation | 4.3 → 2.4 | 40.2 → 37.5 | 6 → 6 | 12 | 12 | 12 |
| 1013 | lookup | 2.6 → 0.0 | 21.9 → 19.8 | 3 → 3 | 18,078 | 18,078 | 18,078 |
| 1073 | calculation | 2.5 → 0.0 | 68.6 → 37.3 | 8 → 3 | insufficient evidence | evidence does not establish it | 0.488 |

## Findings

- **The wait for the plan is almost gone.** Summed over ten rows it fell from 48.8 s to 3.7 s, about 4.5 s per question. On eight rows the plan was ready before retrieval finished. On 210 and 727 retrieval finished first, so research still waited 1.3 s and 2.4 s. `research.plan_started_early` was true in every prefetch run.
- **Total time follows on rows that took the same path.** The five lookups ran the same three requests in both modes; together they went from 117.7 s to 94.1 s (−20%). On 210, 471 and 1073 the two runs took different paths, so their totals are not comparable.
- **Budget accounting is unchanged.** Request counts match on eight rows. On 1073 the prefetch run stopped after 3 requests instead of 8, because it took a different path, not because of the plan.
- **No answer got worse because of the prefetch.** Off got 8 of 10 right, on got 9 of 10. The difference is 210, where the off run abstained and the on run found 21%. That is run-to-run variance in the research path, as on row 730 earlier, not an effect of the plan. Both 1073 runs missed 0.488.

Planner call times varied from 2.2 s to 10.8 s between runs of the same question, which is why the plan wait, not total seconds, is the measure to trust.

Tokens for the twenty runs: 544,311 input, 47,632 output (off 312,286 / 21,932, on 232,025 / 25,700). That is about twice the estimate made before the run, which came from each row's last saved run. 210, 471, 509 and 1073 took far longer research paths than their last saved runs.
