# Answered questions — source-verified results

Updated: **19 October 2026**. Historical distinct questions with a correct,
source-supported published answer: **28**, across **30 distinct questions tried**.
There is also **one correct refusal** and **one unresolved question**, tracked separately below. Each question appears once; rerunning
the same question does not add to the count.

This is a historical success ledger, not a claim that all 28 have passed on the
latest code or that the complete benchmark has been evaluated. Runs are scoped
to the question's source document; open-corpus document discovery needs separate
evaluation. Original-PDF review supports the source answer independently of the
runtime release checks.

| Row | Question / document | Source-supported answer | Successful run | Time / model calls |
| --- | --- | --- | --- | --- |
| 210 | Election-news attention for the party with the higher combined good-policy/ethics rating. `05-03-18-political-release.pdf` | **21%**; Democrats / Democratic leaners | [Report](../artifacts/mmlongbench-v2/adaptive-pair-20261019/REPORT.md) | 28.25 s / 3 |
| 642 | ProgramFC / FLAN-T5-small gold-evidence F1, descending. `2023.acl-long.386.pdf` | **64.4, 62.5, 62.2**; HOVER 2-hop, 4-hop, 3-hop | [Report](../artifacts/mmlongbench-v2/adaptive-pair-20261019/REPORT.md) | 66.11 s / 8 |
| 223 | Internet, smartphone, and tablet use among high-income older adults, descending. `PIP_Seniors-and-Tech-Use_040314.pdf` | **90%, 42%, 39%**; income $75,000+ | [Report](../artifacts/mmlongbench-v2/adaptive-pair2-20261019/REPORT.md) | 46.42 s / 9 |
| 1018 | FY2021 debt / EBITDA, including current long-term debt and lease liabilities. `COSTCO_2021_10K.pdf` | **1.344×** = (799+6692+3916)/(6708+1781) | [Report](../artifacts/mmlongbench-v2/adaptive-row1018-targeted-v4-20261019/REPORT.md) | 68.02 s / 9 |
| 1079 | Gross profit / total assets for the year ending January 28, 2023. `BESTBUY_2023_10K.pdf` | **0.627** = 9912/15803 | [Report](../artifacts/mmlongbench-v2/adaptive-row1079-targeted-20261019/REPORT.md) | 29.86 s / 5 |
| 740 | Germanwings event and report dates. `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` | **[2015-03-24, 2015-03-25]**; event, report | [Report](../artifacts/mmlongbench-v2/adaptive-three-20261019/REPORT.md) | 24.90 s / 5 |
| 371 | Other-company directorships held by three directors. `afe620b9beac86c1027b96d31d396407.pdf` | **30**; total and distinct-company counts agree | [Report](../artifacts/mmlongbench-v2/adaptive-entity-repair-v2-20261019/REPORT.md) | 61.63 s / 7 |
| 396 | Appendix C strengths and weaknesses. `e79deb02a0c0e87511080836c5d4347b.pdf` | **[22,21]**; Strengths, Weaknesses | [Report](../artifacts/mmlongbench-v2/adaptive-entity-repair-v2-20261019/REPORT.md) | 45.03 s / 5 |
| 525 | Identify Twitter from metrics; sum two 2013 demographic percentages. `measuringsuccessonfacebooktwitterlinkedin-160317142140_95.pdf` | **32%** = 16+16 | [Report](../artifacts/mmlongbench-v2/adaptive-source-authority-v2-20261019/REPORT.md) | 40.42 s / 6 |
| 729 | Germanwings, Lufthansa, and Airbus tweet total. `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` | **41** = 24+12+5 | [Report](../artifacts/mmlongbench-v2/adaptive-source-authority-v2-20261019/REPORT.md) | 33.03 s / 6 |
| 368 | Two Godfrey Phillips plant locations. `afe620b9beac86c1027b96d31d396407.pdf` | **Andheri (Mumbai), Guldhar (Ghaziabad)**; subsidiary qualification retained | [Report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md) | 33.76 s / 6 |
| 387 | Governor named on the first page. `e79deb02a0c0e87511080836c5d4347b.pdf` | **Rick Scott** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md) | 23.09 s / 3 |
| 472 | Maximum coffee weight in the manual insert. `User_Manual_1500S_Classic_EN.pdf` | **16 grams**; integer answer 16 | [Report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md) | 16.33 s / 3 |
| 507 | Geographic market for EPS Code AR01. `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf` | **Little Rock** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md) | 13.90 s / 3 |
| 1076 | Cash and cash equivalents on January 28, 2023. `BESTBUY_2023_10K.pdf` | **1,874 million USD** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md) | 20.21 s / 3 |
| 1077 | Best Buy merchandise inventory accounting policy. `BESTBUY_2023_10K.pdf` | **Lower of cost or net realizable value; weighted-average costing** | [Report](../artifacts/mmlongbench-v2/adaptive-mixed-five-20261019/REPORT.md) | 25.71 s / 3 |
| 370 | Executive directors attending more than six Board Meetings. `afe620b9beac86c1027b96d31d396407.pdf` | **Mr. S.V. Shanbhag — 7 meetings** | [Report](../artifacts/mmlongbench-v2/adaptive-mixed-five-20261019/REPORT.md) | 21.93 s / 3 |
| 1024 | FY2021 operating cash flow / current liabilities. `COSTCO_2021_10K.pdf` | **0.304** = 8958/29441 | [Report](../artifacts/mmlongbench-v2/adaptive-mixed-five-20261019/REPORT.md) | 34.74 s / 6 |
| 524 | Lower rural-user percentage in 2013–2014 for the platform identified by its tools. `measuringsuccessonfacebooktwitterlinkedin-160317142140_95.pdf` | **2013**, 11% versus 17% | [Report](../artifacts/mmlongbench-v2/adaptive-selection-strict-20261019/REPORT.md) | 40.07 s / 6 |
| 634 | Blue-background execution-function names in Figure 1. `2023.acl-long.386.pdf` | **["Fact Checker"]**; Functions column | [Report](../artifacts/mmlongbench-v2/adaptive-selection-strict-20261019/REPORT.md) | 37.72 s / 6 |
| 478 | Descriptions for error codes 88 and 188. `User_Manual_1500S_Classic_EN.pdf` | **88: Boiler over-temperature; 188: Heater error** | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) | 24.77 s / 3 |
| 382 | Combined quizzes in Units 4, 5 and 6. `f8d3a162ab9507e021d83dd109118b60.pdf` | **2**; Quiz #2 and Quiz #3 | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) | 40.84 s / 5 |
| 385 | Top three rectangle headings on printed page 2. `e79deb02a0c0e87511080836c5d4347b.pdf` | **STRATEGIC PRIORITY AREAS; STRATEGIES; OBJECTIVES**; physical page 5 | [Report](../artifacts/mmlongbench-v2/adaptive-page-catalog-20261019/REPORT.md) | 63.06 s / 10 |
| 639 | Semantic-error category with the lowest total in HOVER. `2023.acl-long.386.pdf` | **Subtask**; 2%, 5%, 2% | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) | 54.32 s / 8 |
| 1020 | FY2021 long-term debt / total liabilities including long-term leases. `COSTCO_2021_10K.pdf` | **25.04%** = (6692+2642+980)/41190; ratio rounded to two decimals 0.25 | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) | 50.67 s / 8 |
| 519 | Audience-data source for the platform identified by its metrics. `measuringsuccessonfacebooktwitterlinkedin-160317142140_95.pdf` | **eMarketer**, Facebook audience | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) | 22.60 s / 3 |
| 372 | All non-executive and independent company directors. `afe620b9beac86c1027b96d31d396407.pdf` | **R.A. Shah; Lalit Bhasin; Anup N. Kothari; C.M. Maniar; O.P. Vaish** | [Report](../artifacts/mmlongbench-v2/adaptive-inventory-window-20261019/REPORT.md) | 58.28 s / 10 |
| 221 | Male 65+ internet use minus home broadband use. `PIP_Seniors-and-Tech-Use_040314.pdf` | **12 percentage points** = 65−53; actual male rows on physical pages 16–17 | [Report](../artifacts/mmlongbench-v2/adaptive-scope-handoffs-20261019/REPORT.md) | 44.07 s / 6 |

Row 642's stored gold label is `[64.3, 62.4, 62.2]`. The PDF values 64.35 and
62.46 do not match that label under standard one-decimal rounding. This ledger
records source correctness rather than exact label matching. Row 1018 rejected
three incorrect intermediate calculation drafts before releasing the correct
answer. The linked reports retain the details.

## Latest runs

The [complete-director recheck](../artifacts/mmlongbench-v2/adaptive-inventory-window-20261019/REPORT.md)
answered row 372 from the original page 9 category table in **58.28 seconds and
10 calls**. Its three-person committee draft was rejected by final scope review,
which sent a grounded objection back to research; the full five-person inventory
then passed input and scope checks. Both receipts remain in state.

The preceding [page-catalog pair](../artifacts/mmlongbench-v2/adaptive-page-catalog-20261019/REPORT.md)
answered row 385 correctly in **63.06 seconds and 10 calls**, while row 372 hit a
source-window guard. The final window patch has an end-to-end offline test, but
the live row 372 success used a two-page scope-research route rather than that
replacement branch. These are two successful case outcomes on separate frozen
revisions, **not an unchanged 2/2 batch**. Other controls have not all been rerun
after the last patch.

Earlier failed rechecks are retained: [operation contracts](../artifacts/mmlongbench-v2/adaptive-operation-contracts-20261019/REPORT.md)
and [review contracts](../artifacts/mmlongbench-v2/adaptive-review-contracts-20261019/REPORT.md).
The source-page catalog is typed application data; it adds no model-generated
summary or extra planning call. No question-specific answers, entities or page
rules were added to runtime code.

The [scope and interpretation recheck](../artifacts/mmlongbench-v2/adaptive-scope-handoffs-20261019/REPORT.md)
produced **3/5 successful task outcomes**: two source-supported answers, one
correct refusal, an unresolved company-wide roster, and a visual-list model-call
timeout. Row 221 is newly answered from the correct male population; row 1020
now displays its percent unit and definition. Row 385 retained a historical
success but did not answer in that recheck; the later catalog pair recovered it. A reviewer boolean does not turn an
unanswered question into a success.

The [ten previously untried questions](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md)
previously produced **7/10 successful task outcomes: six source-supported answers, one
correct refusal, and three unanswered questions**. No runtime code, prompts,
retrieval settings or budgets changed during the sequential batch.

Together with the previous two targeted checks on matching workflow source
hashes, this is **nine successful outcomes out of 12 questions on that earlier strict-output workflow**:
eight published answers, one refusal, and three unresolved cases. The older
**18 historical successes have not been rerun on this workflow**. This is not a
current 26/26 stability claim or a complete benchmark score.

The previous strict-output pair passed **2/2 targeted rechecks**, rows 524 and
634, with six calls, one collection tool, no retries and one passing final scope
check each. No finalizer model was called in that pair.

The [repair report](../artifacts/mmlongbench-v2/adaptive-selection-strict-20261019/REPORT.md)
retains every intermediate version: an alternate diagram-region answer, a false
input rejection over repeated names, and a missing required completeness field.
The final workflow separates typed selection/list operations, source-object
bindings, input accuracy, reviewed list presentation, and strict output shape.
It does not feed gold labels or question-specific values into runtime prompts.

The preceding main revision answered 10/12 selected questions: **7/7** in the
first selection plus **3/5** in the mixed selection. The
[mixed-five report](../artifacts/mmlongbench-v2/adaptive-mixed-five-20261019/REPORT.md)
preserves the two original abstentions, rather than replacing them with later
successes. The earlier observations below remain historical records.

- **729:** 41, 33.03 seconds / 6 calls. Original images supplied the correct 12
  instead of the indexed OCR value 42.
- **525:** 32%, 40.42 seconds / 6 calls. Relationship evidence reached the first
  final scope check; no finalizer loop was needed.
- **Five direct lookups, 5/5:** rows 368, 387, 472, 507, and 1076. Four used no
  tools and three model calls; row 368 needed additional document search and six
  calls. Separate original-PDF reviews supported the published answers.
- The intermediate **0/2** version is retained: an irrelevant count-mode default
  leaked into arithmetic review, and an authorized context page was rejected as
  a numeric input page. Regression tests cover both defects.

[Direct-lookup report](../artifacts/mmlongbench-v2/adaptive-easy-five-20261019/REPORT.md),
[calculation report](../artifacts/mmlongbench-v2/adaptive-source-authority-v2-20261019/REPORT.md),
[intermediate 0/2 report](../artifacts/mmlongbench-v2/adaptive-source-authority-20261019/REPORT.md),
and [initial 1/2 measurement](../artifacts/mmlongbench-v2/adaptive-new-pair-20261019/REPORT.md)
remain separate records. Unsuccessful runs are not replaced by later successes.

Raw JSON/JSONL, spans, captures, source capsules, and images remain local and are
ignored by Git. Repository links point to small Markdown summaries. Detailed
source-review files remain in the local run/row directories identified by those
reports.

## Correct refusals

A justified refusal is a successful unanswerable task outcome, but is not counted
as a source-supported published answer in the table above.

| Row | Question | Outcome | Run |
| --- | --- | --- | --- |
| 220 | Requested 2022 survey headcount from a report published in 2014 using 2013 survey data. | Correct abstention; nine calls and four repeated searches expose a termination-efficiency issue. | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) |

## Unresolved questions

| Row | Required result / evidence | Observed failure | Run |
| --- | --- | --- | --- |
| 661 | Reference answer 0.0 V for the P2.7 ENABLE low/baseline waveform. | Scalar reading routed as multi-input selection; later source inference remained unverified. The voltage is not explicitly annotated on that trace. | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) |

## Adding a result

Add a row only after a correct answer is actually published and original-PDF
review supports it. Security validation or a reviewer's boolean alone is
insufficient; an abstaining response is not counted as an answered question.

Record the row, source document, answer, run/report, elapsed time, and model-call
count. Keep failed attempts in separate run directories. A later success updates
the row's successful-run link without deleting earlier failures. Source hashes
remain in local profiles/capsules. This ledger is not training data or a runtime
source of gold answers.
