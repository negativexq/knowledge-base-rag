# Ten unseen questions, mostly easy: frozen sequential diagnostic

All ten questions completed in the selected order on `fix/research-evidence-completion`,
with the same runtime hashes as the successful source-gap recheck. Eight estimated
easy lookups and two medium counting/arithmetic tasks were selected from question
text alone; none had previously been attempted in adaptive diagnostics. No gold
answers or reference pages were used for selection or main generation. No runtime
edits, substitutions or reruns occurred during the batch.

## Outcomes

**Eight source-supported published answers, one incorrect answer, and one
source-consistent abstention with an execution error.** The abstention is not
counted as a clean successful refusal; a reviewer boolean or matching unanswerable
label does not establish a successful evidence-completion path.

| Order | Row | Task | Published result | Source outcome | Main time / calls |
| --- | --- | --- | --- | --- | --- |
| 1 | 383 | Producer of document revised May 2016 | Florida Department of Health | Correct; original page 2. | 26.46 s / 3 |
| 2 | 1082 | Best Buy FY2023 current assets | 8,802 million | Correct; original page 39. | 58.35 s / 9 |
| 3 | 508 | Geographic market for EPS AR03 | Abstained | AR03 is absent from the relevant Arkansas listing, but repair failed with `UnexpectedModelBehavior`. | 61.72 s / 7 |
| 4 | 1019 | Costco FY2021 total liabilities | USD 41,190 million | Correct; original page 38. | 20.41 s / 3 |
| 5 | 476 | Number of USB functions available for data exchange | 5 | Incorrect; original pages 56–57 contain nine functions. | 37.93 s / 5 |
| 6 | 832 | Names of Units 1 and 2 in Semester 1, Quarter 1 | Understanding Economic Systems and Business; Making Ethical Decisions and Managing a Socially Responsible Business | Correct; original pages 2–3. | 22.14 s / 3 |
| 7 | 1083 | Best Buy FY2023 basic earnings per share | USD 6.31/share | Correct; original page 40. | 24.99 s / 3 |
| 8 | 1028 | Costco membership warehouses in 2021 | 815 worldwide | Correct; original page 19. | 14.48 s / 3 |
| 9 | 833 | Unit 8 case-study title | Discrimination in the Workplace Continues | Correct; original page 7. | 18.12 s / 3 |
| 10 | 727 | Germanwings tweets minus Lufthansa tweets | 12 = 24−12 | Correct; original page 16. | 28.42 s / 6 |

Difficulty was estimated before execution, not assigned from outcomes. The frozen
selection copied the original row 476 wording about USB data-exchange steps. The
already configured corrected-label package supplies the actual executed question,
"How many USB functions are available for data exchange?" This correction was
applied by the unchanged runner, not introduced during the batch. Its nine-item
reference was inspected only after generation.

## Source checks beyond the automatic reviewer

Row 832's automatic reviewer received reference images for pages 1 and 2, so it
could not independently verify Unit 2. Direct post-run inspection of original
physical page 3 confirms the complete Unit 2 title. The initial reviewer limitation
is retained; the success is supported by the additional original-page inspection,
not by overriding its boolean to match the label.

Row 508 has no reference images in the separate review packet because its
reference-page list is empty. Direct post-run inspection of the original Arkansas
listing on physical page 8 shows **AR01: Little Rock** and **AR02: Northern Arkansas**,
followed by the New Mexico heading. AR03 is not listed in this source object.
The refusal is therefore consistent with the source, but the runtime did not
produce a clean reviewed absence receipt: it initially selected Alabama page 7,
proposed Mobile/AL03, and incorrectly routed a textual code-to-name lookup as a
numeric conditional comparison. Review rejected the wrong binding and operation.
Repair then failed its output contract (`Exceeded maximum output retries (0)`),
ending with `QUANTITY_REVIEW_UNRESOLVED`. The error was not silently retried and
the incorrect Mobile answer was not published. This remains an unresolved workflow
case rather than a clean refusal success.

## Remaining failures and useful observations

Row 476 exposes a **false completeness judgment**, not a calculation error. The
collector correctly transcribed five functions on page 56, treated the page footer
and blank space as the end of the whole USB inventory, and marked coverage complete.
The independent checker accepted that judgment. Four more functions continue on
page 57. Since no coverage objection was raised, the new source-gap completion
path was never triggered. The application correctly counted its incomplete five-item
inventory, producing the wrong whole-section answer. An actual category/section
boundary must distinguish page completion from inventory completion.

Row 1082 recovered an initially omitted balance-sheet input and answered correctly,
but used nine model calls for a simple lookup. Seven other correct answers used
three calls each, except the arithmetic row 727, which used six. The latter rejected
an indexed Lufthansa value of 42 and used original-image input 12 instead. Successful
cases do not prove that all source selection or visual review is reliable.

## Timing, configuration and coverage

Main time across the ten rows was **313.02 seconds**, averaging 31.30 seconds with
a 25.73-second median. Total sequential wall time including model startup and the
separate after-run reviews was **573.45 seconds**. Main usage was **45 requests,
130,520 input tokens and 15,176 output tokens**. Model pricing is unset, so API
dollar cost is unavailable. Main times include initial retrieval/reranking and
generation, excluding process startup and the separate reviewer.

Same `gpt-6-luna`, effort profile, fast-path/evidence-needs flags, source-document
scope and ten-request/120,000-token/240-second per-question diagnostic ceilings as
the preceding recheck. All main runtime file hashes were frozen before the first
request. Embedding, ingestion, initial retrieval, reranking and production budgets
were unchanged. No source repairs were added during or after this measurement.

The [aggregate question ledger](../../../docs/adaptive-solved-questions.md) now
records **45 distinct questions tried: 40 historical source-supported answers,
one clean correct refusal, and four unresolved questions/workflows**. This batch
adds eight answers; its error-terminated, source-consistent refusal is tracked
separately. Historical totals span revisions and are not a 40/45 current-version
benchmark score. Raw JSON, source renders, captures, usage and spans remain local
and ignored; only this compact report and ledger updates are intended for Git.
