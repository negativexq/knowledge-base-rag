# Answered questions — source-verified results

Updated: **19 October 2026**. Historical distinct questions with a correct,
source-supported published answer: **15**. Each question appears once; rerunning
the same question does not add to the count.

This is a historical success ledger, not a claim that all 15 have passed on the
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

Row 642's stored gold label is `[64.3, 62.4, 62.2]`. The PDF values 64.35 and
62.46 do not match that label under standard one-decimal rounding. This ledger
records source correctness rather than exact label matching. Row 1018 rejected
three incorrect intermediate calculation drafts before releasing the correct
answer. The linked reports retain the details.

## Latest runs

The latest implementation passed **7/7 selected questions: two calculations and
five direct lookups**, with the same code/settings. The other eight historical
successes have not been rerun on this version. This is not a 15/15 stability
claim or a complete benchmark score.

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

## Adding a result

Add a row only after a correct answer is actually published and original-PDF
review supports it. Security validation or a reviewer's boolean alone is
insufficient; an abstaining response is not counted as an answered question.

Record the row, source document, answer, run/report, elapsed time, and model-call
count. Keep failed attempts in separate run directories. A later success updates
the row's successful-run link without deleting earlier failures. Source hashes
remain in local profiles/capsules. This ledger is not training data or a runtime
source of gold answers.
