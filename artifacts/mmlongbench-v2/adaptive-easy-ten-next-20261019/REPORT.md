# Ten more unseen questions on the unchanged runtime

All ten completed sequentially in the selected order. Eight were estimated easy
direct/section/table/visual lookups and two medium arithmetic/enumeration tasks,
based on question text before generation. Each was new among the 45 previously
attempted adaptive questions. Main runtime hashes matched the preceding
[ten-question batch](../adaptive-easy-ten-20261019/REPORT.md) before and after this
run. No implementation of INV-001 or ROUTE-001, runtime edit, substitution or rerun
occurred during this measurement. Gold answers and reference pages were excluded
from selection and main generation.

## Outcomes

**Eight source-supported published answers, one unanswered answerable question,
and one source-consistent abstention with an execution error.** There were no
incorrect published answers in this batch. The error-terminated abstention is not
counted as a clean refusal success.

| Order | Row | Task | Published result | Source outcome | Main time / calls |
| --- | --- | --- | --- | --- | --- |
| 1 | 386 | Second Regulatory Efficiency objective | Reduce facility-license issuance from 60 to 45 days by December 31, 2018 | Correct; physical page 5, printed page 2. | 25.73 s / 3 |
| 2 | 1081 | Best Buy FY2023 Domestic stores | 978 | Correct; original page 19. | 23.21 s / 3 |
| 3 | 836 | Unit 14 topic | Using Financial Information and Accounting | Correct; original page 10. | 15.26 s / 3 |
| 4 | 1013 | Costco FY2021 total equity including noncontrolling interests | USD 18,078 million | Correct; original page 38. | 22.30 s / 3 |
| 5 | 471 | Milk temperature represented by yellow | Abstained | No yellow entry in the original legend, but numeric conversion failed. | 28.11 s / 5 |
| 6 | 515 | Recorded Demonstrations video count | 5 | Correct; original pages 1–2, including continuation. | 48.69 s / 8 |
| 7 | 1026 | Costco FY2021 common-stock repurchase spending | Abstained | Missed an answerable question: approximately USD 495 million. | 54.40 s / 5 |
| 8 | 1080 | Women in new salaried field positions, Best Buy FY2023 | 25% | Correct; original page 7 explicitly reports the FY2023 achievement. | 25.71 s / 3 |
| 9 | 373 | Proposed dividend, 2002 minus 2003 | 155.980 Rupees in lacs = 1923.78−1767.8 | Correct; original page 19. | 43.03 s / 6 |
| 10 | 835 | Unit 8 learning-outcome count | 10 | Correct; original pages 6–7. | 42.54 s / 5 |

The unchanged runner applied the existing corrected-question package. Its executed
row 1013 asks for total equity including noncontrolling interests, and row 373
specifies the fiscal years ended March 31, 2002 and March 31, 2003. Both original
and executed question texts were recorded in the frozen selection, without gold
values or reference-page inspection.

## New shared runtime defect: NUM-001

The two abstentions share an unhandled Decimal `InvalidOperation`, now recorded in
the [open-issue register](../../../docs/adaptive-open-issues.md).

For **471**, the collector emitted `Not stated; yellow is not listed` as the value
of a complete numeric-read operand. The checker marked inputs and operation
supported. Provisional execution tried to convert that sentence to a number and
failed. The original physical page 19 legend contains green (up to 8 °C), white
(8–16 °C) and caramel (above 16 °C), with no yellow entry. Direct post-run inspection
of the original image confirmed that legend; the separate reviewer had no image
because the reference-page list is empty. The refusal is content-consistent but
was not produced by a clean source-grounded absence path.

For **1026**, source selection reached the equity statement on physical page 39.
The collector supplied accounting display `(495)` as the numeric value. Independent
review recognized the distinction between a signed equity reduction and positive
spending magnitude, issuing an operation objection. Before saving that assessment,
the application attempted provisional numeric conversion and raised `InvalidOperation`.
The draft survived, but its typed receipt still had `check=null` and no assessments;
the raw checker output remains in captures. Independent original-page review of
the repurchase note on physical page 29 confirms approximately USD 495 million.
This is a numeric-input/checkpoint failure after extraction, not proof of missing
source data or a budget exhaustion.

The runtime catches `ValueError` around provisional execution but does not handle
this Decimal exception there. A display string, a canonical number and an absent
value need distinct states, and review must survive execution failure. No patch
was introduced during or after this diagnostic.

## Inventory observations and limits

Row 515 initially selected a heading without the full recordings. The incomplete
review led to additional source inspection, and the final count covered both
original pages and the section boundary. Row 835 also counted a two-page inventory
correctly. These successes coexist with the earlier row 476 false completeness
judgment: gap completion works when incompleteness is identified, but INV-001
remains open when a page footer is incorrectly accepted as inventory closure.

Five correct direct lookups required only three model requests and no tools; the
two medium arithmetic/count questions used six and five respectively. Row 515
needed eight calls and three tool attempts despite being estimated easy. Difficulty
labels are selection estimates, not claims about actual runtime cost or guarantees
that a question is answerable.

## Timing and coverage

Main elapsed time summed to **328.98 seconds**, averaging 32.90 seconds with a
26.92-second median. Whole-batch wall time including startup and separate reviews
was **599.83 seconds**. Main usage was **44 requests, 146,222 input tokens and
16,544 output tokens** across the ten questions. Pricing is unset, so API dollar
cost is unavailable. Main elapsed time includes initial retrieval/reranking and
generation, excluding startup and the separate diagnostic reviewer.

Same `gpt-6-luna`, effort profile, fast-path/evidence-needs flags, source-document
scope and ten-request/120,000-token/240-second per-question diagnostic ceilings.
Embedding, ingestion, initial retrieval/reranking settings and production budgets
were unchanged. All raw JSON, captures, source renders, usage and spans remain
local and ignored.

The [aggregate ledger](../../../docs/adaptive-solved-questions.md) now contains
**55 distinct attempted questions: 48 historical source-supported published
answers, one clean correct refusal and six unresolved questions/workflows**.
That historical total spans development revisions, not a 48/55 current-version
benchmark score. This report retains failures independently of reviewer booleans
and unanswerable-label matches.
