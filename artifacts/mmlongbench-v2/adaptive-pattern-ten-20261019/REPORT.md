# Third frozen ten-question batch and recurring failure patterns

Ten previously untried rows completed sequentially on the identical runtime used
for the preceding two ten-row batches. Question text alone informed selection:
eight estimated easy and two medium cases, spanning names, numeric reads, key
membership, a percentage, a visual time, document-position scope, comparison and
category counting. Gold values/reference pages were excluded from selection and
generation. No runtime edits, substitutions or repeated paid runs occurred.

## Outcomes

**Six clearly source-supported published answers, one verified correct refusal,
two error-terminated abstentions, and one unresolved published count discrepancy.**
The disputed count is not promoted to success merely because the independent
reviewer agreed with the generator, nor marked wrong solely because gold differs.

| Row | Task | Published result | Source outcome | Main time / calls |
| --- | --- | --- | --- | --- |
| 364 | Godfrey Phillips bankers | Eight named banks | Correct; original page 8. | 19.16 s / 3 |
| 1025 | Costco FY2021 repurchased shares | Abstained | Missed an answerable question: 1,358,000 shares. | 35.43 s / 5 |
| 516 | Whether CA03 belongs to San Francisco Bay Area | No; CA03 is Sacramento County, Bay Area CA04–CA11 | Correct; original pages 9–10. | 20.46 s / 3 |
| 741 | English-language share of Germanwings tweets | 41.667% = 10/24×100 | Correct; original page 16. | 34.61 s / 6 |
| 658 | Parts with prefix N in the PACKAGES table | 4 | Disputed merged-table membership/counting unit; reference is 2. Not counted as verified. | 54.98 s / 6 |
| 388 | Governor named on the last page | Abstained | Last page contains no governor name; tool nevertheless failed numeric conversion. | 37.86 s / 5 |
| 1027 | Operations responsible for stated Costco sales/income proportions | U.S. and Canadian operations | Correct; original page 9. | 25.42 s / 3 |
| 475 | Start time of a red bar on manual page 50 | Abstained | Correct refusal: original chart has green/blue bars, not a red bar. | 79.64 s / 9 |
| 1071 | Highest Best Buy FY2022 cash flow among activity types | Operating activities, USD 3,252 million | Correct; original page 42. | 20.89 s / 3 |
| 513 | Los Angeles Area market names | 13 | Correct; original page 10. | 41.36 s / 5 |

## Repeated numeric/type failures

**1025 repeats NUM-001.** The collector read accounting display `(1,358)` with
unit `thousand shares` from the equity statement. Review accepted the source
transcription, but execution recorded `A canonical decimal value is required`.
The draft and review survived this ValueError; this differs from the uncaught
Decimal exceptions in rows 471/1026. Original page 29 directly confirms 1,358,000
shares. The initial answer had stated that count but was rejected as
`CRITICAL_VALUE_INDETERMINATE`/`NO_VALID_SUPPORT_BACKED_CLAIMS`; the fallback did not
complete sign/scale/value normalization. Source display, canonical number, scale
and requested positive transaction count must remain distinct responsibilities.

**388 repeats NUM-001 and ROUTE-001.** A question seeking a person's name was
routed to numeric read. Its complete operand value was `Not mentioned`, supported
by an image witness identifying Appendix E on the last physical page, 17. Decimal
conversion raised `InvalidOperation`; the typed receipt retained the draft but
not the returned assessment. Direct original-image inspection confirms the page
is Environmental Scan Resources and contains no governor name. The content of
the refusal is consistent, but the execution is not a clean absence decision.

Across these **30 same-runtime questions**, numeric-representation/absence failures
appear in **four distinct rows: 471, 1026, 1025 and 388**. They involve unrelated
source objects and both numbers and nonnumeric absence statements. This is the
strongest reproduced implementation pattern; it is not evidence of an embedding
quality problem or a reason to keep tightening answer wording.

## Other boundaries: failures, controls and uncertainty

Text-to-numeric routing was seen in row 508's code-to-name lookup and recurs in
388's person-name read. Row 516 is a useful successful control: an ordinary
code-membership question remained on the text fast path and passed without tools.
The problem is therefore conditional dispatch/contract compatibility, not every
question containing a code or name.

The incomplete-inventory failure from row 476 was **not reproduced** here. Rows
513 and 658 completed their count execution; row 513's thirteen source items are
verified. Earlier rows 515 and 835 also successfully covered continuation pages.
INV-001 remains open because those successes do not establish that false closure
judgments are prevented when a reviewer accepts a page footer as inventory end.

For **658**, the generator and independent reviewer interpret the merged PACKAGES
table as four N-associated part names: 8052AH, 8032AH, 8752BH* and 8751BH. The
reference label is 2. Direct original-page inspection shows two explicit N entries
and merged/grouped part/package cells. Counting explicit N entries versus named
parts, and the membership implied by those merged cells, requires adjudication.
The audit cannot confidently certify four or assert that the reference is wrong.
This remains an unresolved counting-unit/source-binding finding, separate from
an arithmetic error or a proven page-continuation defect.

For **475**, the checker rejected a proposed 07:00 reading because it belonged to
a green bar, not the requested red bar. The after-run reviewer had no reference
image because that row's reference-page list is empty. Direct post-run inspection
of original manual page 50 confirms green/blue bars and no red time bar. This is
a correct refusal without an execution exception, though inefficient: nine calls,
three tool attempts and one diagnostic correction. It does not close row 635's
earlier blue-versus-grey false acceptance.

## Thirty-question comparison on one runtime

| Frozen batch | Verified answers | Clean correct refusal | Wrong published answer | Answerable but unanswered | Error-ended source-consistent refusal | Disputed published count |
| --- | --- | --- | --- | --- | --- | --- |
| [First ten](../adaptive-easy-ten-20261019/REPORT.md) | 8 | 0 | 1 | 0 | 1 | 0 |
| [Second ten](../adaptive-easy-ten-next-20261019/REPORT.md) | 8 | 0 | 0 | 1 | 1 | 0 |
| This ten | 6 | 1 | 0 | 1 | 1 | 1 |
| Total | **22** | **1** | **1** | **2** | **3** | **1** |

These are 30 disjoint questions with identical runtime hashes, not 30 repeated
attempts or a full benchmark. A reviewer boolean, source-consistent error stop or
gold match is not automatically a verified successful workflow.

## Timing and historical coverage

This batch used **369.81 seconds** main time, averaging 36.98 seconds with a
35.02-second median. Whole-batch wall time including startup and separate reviews
was **618.65 seconds**. Main usage was **48 model requests, 140,818 input tokens
and 18,747 output tokens**. Main time includes retrieval/reranking and generation;
separate after-run review is excluded. Model pricing is unset, so dollar cost is
unavailable.

Same `gpt-6-luna`, effort profile, fast-path/evidence-needs flags, source-document
scope and ten-request/120,000-token/240-second per-question ceilings. Embedding,
ingestion, initial retrieval/reranking and production budgets stayed unchanged.
No fixes were implemented during or after this measurement. Raw source renders,
JSON, captures and spans remain local and ignored.

The [historical ledger](../../../docs/adaptive-solved-questions.md) now records
**65 distinct questions tried: 54 source-supported published answers, two clean
correct refusals, and nine unresolved questions/workflows** across development
revisions. The [open-issue register](../../../docs/adaptive-open-issues.md) separates
confirmed defects, the disputed merged-table count and the source-limited waveform
case. These historical totals are not a 54/65 current-version benchmark score.
