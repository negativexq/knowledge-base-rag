# Answered questions — source-verified results

Updated: **19 October 2026**. Historical distinct questions with a correct,
source-supported published answer: **56**, across **65 distinct questions tried**.
There are also **four correct refusals** and **five unresolved questions/workflows**, tracked separately below. Each question appears once; rerunning
the same question does not add to the count.

This is a historical success ledger, not a claim that all 56 have passed on the
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
| 477 | Number of coffee quality levels. `User_Manual_1500S_Classic_EN.pdf` | **7**; complete 1–7 list | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-five-20261019/REPORT.md) | 44.49 s / 5 |
| 1078 | Goodwill on January 28, 2023. `BESTBUY_2023_10K.pdf` | **USD 1,383 million** | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-five-20261019/REPORT.md) | 23.92 s / 3 |
| 1023 | FY2021 total debt / assets, including all lease liabilities. `COSTCO_2021_10K.pdf` | **19.246 percent** = (799+6692+3916)/59268×100 | [Report](../artifacts/mmlongbench-v2/adaptive-evidence-completion-20261019/REPORT.md) | 57.96 s / 6 |
| 212 | Compare public party attributes, then read congressional support for the selected party. `05-03-18-political-release.pdf` | **92%**; public comparison 50+42 versus 50+41, then Democratic registered-voter support | [Report](../artifacts/mmlongbench-v2/adaptive-gap-consumption-20261019/REPORT.md) | 123.41 s / 9 |
| 383 | Producer of the document revised May 2016. `e79deb02a0c0e87511080836c5d4347b.pdf` | **Florida Department of Health** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 26.46 s / 3 |
| 1082 | Best Buy FY2023 total current assets. `BESTBUY_2023_10K.pdf` | **USD 8,802 million** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 58.35 s / 9 |
| 1019 | Costco FY2021 total liabilities. `COSTCO_2021_10K.pdf` | **USD 41,190 million** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 20.41 s / 3 |
| 832 | Unit 1 and Unit 2 names in Semester 1, Quarter 1. `f8d3a162ab9507e021d83dd109118b60.pdf` | **Understanding Economic Systems and Business; Making Ethical Decisions and Managing a Socially Responsible Business** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 22.14 s / 3 |
| 1083 | Best Buy FY2023 basic earnings per share. `BESTBUY_2023_10K.pdf` | **USD 6.31/share** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 24.99 s / 3 |
| 1028 | Costco membership warehouse count in 2021. `COSTCO_2021_10K.pdf` | **815 worldwide** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 14.48 s / 3 |
| 833 | Unit 8 case-study title. `f8d3a162ab9507e021d83dd109118b60.pdf` | **Discrimination in the Workplace Continues** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 18.12 s / 3 |
| 727 | Germanwings tweets minus Lufthansa tweets. `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` | **12 Tweets** = 24−12; image corrected indexed 42 to 12 | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) | 28.42 s / 6 |
| 386 | Second Regulatory Efficiency objective. `e79deb02a0c0e87511080836c5d4347b.pdf` | **By December 31, 2018, reduce average facility-license issuance from 60 days (2015) to 45 days** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 25.73 s / 3 |
| 1081 | Best Buy FY2023 Domestic store count. `BESTBUY_2023_10K.pdf` | **978** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 23.21 s / 3 |
| 836 | Unit 14 topic. `f8d3a162ab9507e021d83dd109118b60.pdf` | **Using Financial Information and Accounting** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 15.26 s / 3 |
| 1013 | Costco FY2021 total equity including noncontrolling interests. `COSTCO_2021_10K.pdf` | **USD 18,078 million** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 22.30 s / 3 |
| 515 | Recorded Demonstrations video count. `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf` | **5**; complete original pages 1–2 | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 48.69 s / 8 |
| 1080 | Female employees in new salaried field positions, Best Buy FY2023. `BESTBUY_2023_10K.pdf` | **25%** | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 25.71 s / 3 |
| 373 | Proposed dividend for fiscal 2002 minus fiscal 2003. `afe620b9beac86c1027b96d31d396407.pdf` | **155.980 Rupees in lacs** = 1923.78−1767.8 | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 43.03 s / 6 |
| 835 | Unit 8 learning-outcome count. `f8d3a162ab9507e021d83dd109118b60.pdf` | **10**; complete original pages 6–7 | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md) | 42.54 s / 5 |
| 364 | Godfrey Phillips bankers. `afe620b9beac86c1027b96d31d396407.pdf` | **State Bank of India; Bank of Baroda; Bank of India; Citibank N.A.; State Bank of Hyderabad; State Bank of Travancore; The Hongkong and Shanghai Banking Corporation; Union Bank of India** | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 19.16 s / 3 |
| 516 | Whether CA03 belongs to the San Francisco Bay Area. `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf` | **No**; CA03 is Sacramento County, Bay Area is CA04–CA11 | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 20.46 s / 3 |
| 741 | English-language percentage of Germanwings tweets. `germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf` | **41.667%** = 10/24×100 | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 34.61 s / 6 |
| 1027 | Operations responsible for 86% of net sales and 81% of operating income. `COSTCO_2021_10K.pdf` | **U.S. and Canadian operations** | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 25.42 s / 3 |
| 1071 | Best Buy FY2022 activity type with highest cash flow. `BESTBUY_2023_10K.pdf` | **Operating activities**, USD 3,252 million; investing −1,372, financing −4,297 | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 20.89 s / 3 |
| 513 | Los Angeles Area geographic-market name count. `8dfc21ec151fb9d3578fc32d5c4e5df9.pdf` | **13** | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) | 41.36 s / 5 |

| 1026 | Costco FY2021 common-stock repurchase spending. `COSTCO_2021_10K.pdf` | **USD 495 million**; reviewed magnitude from signed `(495)` | [Report](../artifacts/mmlongbench-v2/adaptive-numeric-pair-20261019/REPORT.md) | 41.80 s / 6 |
| 1025 | Costco FY2021 repurchased common shares. `COSTCO_2021_10K.pdf` | **1,358,000 shares**; reviewed magnitude and thousand-share conversion | [Report](../artifacts/mmlongbench-v2/adaptive-numeric-pair-20261019/REPORT.md) | 39.20 s / 6 |

Row 642's stored gold label is `[64.3, 62.4, 62.2]`. The PDF values 64.35 and
62.46 do not match that label under standard one-decimal rounding. This ledger
records source correctness rather than exact label matching. Row 1018 rejected
three incorrect intermediate calculation drafts before releasing the correct
answer. The linked reports retain the details.

## Latest runs

The [four-question numeric recheck](../artifacts/mmlongbench-v2/adaptive-numeric-four-20261019/REPORT.md)
converts rows 471 and 388 from error-ended abstentions into clean checked refusals.
In that attempt, rows 1026 and 1025 remained unanswered: numeric notation/scale boundary defects
were exposed, and 1026 additionally stopped on a checker API error. The failed
attempt is retained; the [two-question follow-up](../artifacts/mmlongbench-v2/adaptive-numeric-pair-20261019/REPORT.md)
then publishes both financial answers correctly after the shared fix. The two
frozen revisions are recorded separately, not presented as an unchanged four-row
pass. This is targeted failure recovery, not paid regression coverage
of previously successful questions.

The [third frozen ten-question batch](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md)
added **six clearly source-supported answers and one correct refusal**. Two rows
ended with numeric/type failures and one merged-table count remains disputed
(model/reviewer 4, reference 2). Across **30 disjoint questions on identical runtime
hashes**, there are **22 verified published answers, one clean refusal and seven
unresolved workflows/outcomes**. Four rows reproduce numeric-representation or
absence-to-number failures. No patches were applied during those three batches.

The [second mostly-easy ten-question batch](../artifacts/mmlongbench-v2/adaptive-easy-ten-next-20261019/REPORT.md)
added **eight source-supported answers**. Row 1026 remained unanswered despite
extracting the repurchase entry; row 471 returned a source-consistent abstention
through an execution error. Both hit Decimal `InvalidOperation` before the checker
assessment was checkpointed, now tracked as NUM-001. Runtime hashes matched the
preceding ten-question batch; no fixes, substitutions or reruns occurred. The two
complete multi-page counts do not close the earlier false-completeness defect.

The [ten mostly easy unseen questions](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md)
produced **eight source-supported answers**, one wrong USB-function count, and
one source-consistent refusal with a repair/output error. Direct original-page
inspection completed row 832's missing Unit 2 verification and confirmed that
row 508's AR03 entry is absent. The latter remains an unresolved workflow because
its refusal followed a tool-contract error rather than a clean absence receipt.
The sequential batch used one frozen runtime, with no reruns or substitutions.

The [source-gap consumption recheck](../artifacts/mmlongbench-v2/adaptive-gap-consumption-20261019/REPORT.md)
answered row 212 correctly in **123.41 seconds and nine calls**. Missing comparison
evidence was searched, carried into the original-image collection, checked for its
public population, then joined to the separate registered-voter support value.
This is one successful recheck; the wrong grey-background answer remains unresolved.

The [five unseen rows](../artifacts/mmlongbench-v2/adaptive-unseen-five-20261019/REPORT.md)
added two source-supported answers. A [three-row recheck](../artifacts/mmlongbench-v2/adaptive-evidence-completion-20261019/REPORT.md)
then answered row 1023 correctly, left row 212 unanswered, and incorrectly released
Fact Checker for row 635's grey-background condition. Original Figure 1 shows a
blue box; the separate reviewer had no reference image. The earlier label-compatible
abstention for 635 had a repair exception and is not counted as a clean refusal.
These are frozen sequential batches on different revisions, not a current 31/35 score.

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
| 475 | Start time of a red bar in the manual image on page 50. | Correct abstention; original chart has green/blue bars, no red time bar. Nine calls and a diagnostic correction indicate inefficient termination, without an execution exception. | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) |

| 471 | Milk temperature for yellow; the original legend lists green, white and caramel only. | Checked `not_found` receipt completes cleanly; five calls, no conversion exception. Earlier error retained in the preceding batch report. | [Report](../artifacts/mmlongbench-v2/adaptive-numeric-four-20261019/REPORT.md) |
| 388 | Governor named on the document's last page; none appears on Appendix E. | Partial evidence rejected, complete last page inspected, checked absence retained; nine calls. Textual tool routing remains a separate architectural issue. | [Report](../artifacts/mmlongbench-v2/adaptive-numeric-four-20261019/REPORT.md) |

## Unresolved questions

Inventory closure, typed tool routing, and numeric-input/checkpoint defects are
recorded in the [open-issue register](adaptive-open-issues.md), which separates
implemented corrections from unresolved outcomes.

| Row | Required result / evidence | Observed failure | Run |
| --- | --- | --- | --- |
| 661 | Reference answer 0.0 V for the P2.7 ENABLE low/baseline waveform. | Scalar reading routed as multi-input selection; later source inference remained unverified. The voltage is not explicitly annotated on that trace. | [Report](../artifacts/mmlongbench-v2/adaptive-unseen-ten-20261019/REPORT.md) |
| 635 | Grey-background execution functions in Figure 1; none are shown. | Initial repair exception; subsequent run incorrectly accepted a blue Fact Checker box as grey. | [Report](../artifacts/mmlongbench-v2/adaptive-evidence-completion-20261019/REPORT.md) |
| 476 | Complete USB data-exchange function inventory: nine across pages 56–57. | Published five after treating a page footer as the inventory boundary; input and scope review accepted the incomplete collection. | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) |
| 508 | Geographic market for EPS Code AR03; the original Arkansas listing contains only AR01 and AR02. | Source-consistent abstention, but wrong AL03/AR03 binding and numeric operation were followed by an invalid repair output. Not counted as a clean refusal. | [Report](../artifacts/mmlongbench-v2/adaptive-easy-ten-20261019/REPORT.md) |
| 658 | N-prefix part count in the merged PACKAGES table. | Published 4, reference 2; automatic review agrees with 4, but counting unit and merged-cell membership need adjudication. No verified success claimed. | [Report](../artifacts/mmlongbench-v2/adaptive-pattern-ten-20261019/REPORT.md) |

## Adding a result

Add a row only after a correct answer is actually published and original-PDF
review supports it. Security validation or a reviewer's boolean alone is
insufficient; an abstaining response is not counted as an answered question.

Record the row, source document, answer, run/report, elapsed time, and model-call
count. Keep failed attempts in separate run directories. A later success updates
the row's successful-run link without deleting earlier failures. Source hashes
remain in local profiles/capsules. This ledger is not training data or a runtime
source of gold answers.
