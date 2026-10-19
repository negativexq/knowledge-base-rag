# Five unseen questions: frozen sequential diagnostic

Five previously untried rows were selected from question text alone, including two
easy lookups, then run in order on main `fd3d5ec`. Runtime hashes were frozen before
the first request. No runtime edits, reruns or outcome-based replacements occurred
during this batch. Generation could not see benchmark labels or reference pages.

| Row | Task | Published result | Source-reviewed outcome | Main time / calls |
| --- | --- | --- | --- | --- |
| 477 | Coffee quality levels | 7 | Correct; original manual page 39 lists levels 1–7. | 44.49 s / 5 |
| 1078 | Best Buy goodwill on January 28, 2023 | USD 1,383 million | Correct; original balance-sheet row. | 23.92 s / 3 |
| 212 | Compare party attributes, then read the selected party's congressional support | Abstained | Missed an answerable question. Correct support is 92%. | 86.55 s / 6 |
| 635 | Grey-background execution-function names in Figure 1 | Abstained | Label-compatible, but not a clean verified refusal: repair raised `REPAIR_CHANGED_UNTARGETED_STRUCTURE`. | 88.27 s / 7 |
| 1023 | Costco FY2021 debt/assets including all lease liabilities | Abstained | Missed an answerable question; lease note was not inspected. | 75.00 s / 6 |

**Two clean source-supported answers out of five.** Row 635 is not counted as a
successful refusal merely because its operational stop matches an unanswerable label.
Its separate reviewer received no reference image because this row's reference-page
list is empty. Later direct inspection of the original Figure 1 confirms that the
function boxes are blue, pink and green, with no grey-background function.

For rows 212 and 1023, a valid missing-operand objection was incorrectly rejected as
`INCOMPLETE_WITHOUT_SOURCE_GAP`: the application recognized group/item coverage gaps
but omitted operand gaps. This prevented evidence repair and spent a diagnostic call
repeating the objection. Row 212 also lacked the relationship-defining comparison
source. Row 635 exposed the inability to remove rejected items from a list repair.

Main elapsed times include initial retrieval/reranking and generation, excluding
process startup and the separate diagnostic reviewer. Main time totals 318.23 seconds;
whole-batch wall time including startup and reviews was 480.90 seconds. API dollar
cost is unavailable because model pricing is unset; raw usage is retained locally.

All rows used `gpt-6-luna`, fast path, evidence needs and after-run review, with the
same ten-request, 120,000-token and 240-second diagnostic ceilings. Embedding,
ingestion, initial retrieval, reranking and production budgets were unchanged.
This source-document-scoped diagnostic is not an open-corpus benchmark or a stability
estimate. Raw JSON, captures, spans and rendered pages remain local and ignored.

The [three-row recheck](../adaptive-evidence-completion-20261019/REPORT.md) retains
subsequent outcomes separately; it does not replace this initial batch.
