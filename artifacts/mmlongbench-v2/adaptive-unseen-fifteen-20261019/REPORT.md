# Fifteen unseen questions: scope, dispatch and provenance audit

Sequential run started on 19 October 2026 UTC and reviewed on 20 October 2026
Europe/Istanbul. Base/main revision `2c659dc`. All 15 rows were new to the preceding
75-question adaptive ledger and local adaptive row profiles. Selection used only
question text and document identity. The frozen row order was:
1015, 511, 366, 384, 637, 1021, 225, 399, 1086, 660, 381, 206, 1085, 732, 517.

Application and trace-harness hashes were checked before each row and match the
preceding ten-row batch. GPT-6 Luna, fast path, evidence needs, independent review
and the same 10-request / 120,000-token / 240-second limits were retained.
No runtime edits, substitutions, parallel questions or paid reruns occurred.
Generation received no gold answers or reference-page hints. Answers were
inspected only after all 15 finished. Evaluation remains source-document scoped.

**Conservative outcome: three source-supported answers, twelve unresolved
questions/workflows.** The latter comprise eight abstentions, three published
incorrect/constraint-violating answers and one disputed task interpretation.
A label-compatible abstention with an execution error is not a clean refusal.

| Row | Released result | Main seconds / requests | Assessment |
| --- | --- | --- | --- |
| 1015 | Abstention | 74.10 / 7 | Answerable with a stated EBITDA definition; year/header binding and collection remain unresolved. |
| 511 | Abstention | 40.82 / 6 | Answerable: Start new search. Text-in-colored-box task routed to numeric read; null/unreadable result cannot repair. |
| 366 | Abstention | 59.06 / 7 | Forecast/actual values 6.7 and 4.3 found; period binding and repair fail. Relative shortfall versus percentage-point gap also needs adjudication. |
| 384 | Abstention | 69.71 / 8 | May 2018 condition does not match Revised May 2016. Workflow ends with ModelRetry, not a checked mismatch receipt. |
| 637 | Abstention | 42.78 / 6 | Correct accepted count 1 blocked because physical page 5 was not bound to printed page 6985 in final scope evidence. |
| 1021 | 0.715 ratio | 59.66 / 9 | Source-supported: 29441/41190. Initial notation rejection recovered through image re-extraction. |
| 225 | Abstention | 79.71 / 8 | Percentage-to-headcount composition fails. About 738 is a derived estimate, not a printed exact count. |
| 399 | 20 people | 90.59 / 9 | Incorrect category membership: 13 neighboring-column names incorrectly added to four MQA Executive Leadership names. Original headings support 4+3=7. Automated reviewer also accepts the wrong grouping. |
| 1086 | USD 13,929 million | 62.61 / 9 | Source-supported: assets 15803 minus cash 1874. Original page 39 manually checked because automatic review received page 40. |
| 660 | Port 1 / P1.1 | 25.31 / 3 | Fails literal requested port range 10–13. Source describes ports 0–3. Reviewer confirms the pin/function fact but overlooks question scope. |
| 381 | 6 quizzes | 43.95 / 5 | Incorrect incomplete whole-course count; original physical page 10 explicitly lists Quiz #7. |
| 206 | Abstention | 45.57 / 6 | About 541 could be estimated from 1503×36%; source selection drops relevant value/denominator. Exact count is not directly reported. |
| 1085 | 20.7% | 39.91 / 6 | Source-supported: 370/1788×100, rounded to one decimal. |
| 732 | 1 figure | 32.01 / 5 | Interpretation unresolved: one Airbus chart panel versus Airbus Tweet value 5. Original page shows both. Do not treat a label or reviewer interpretation as decisive. |
| 517 | Abstention | 51.72 / 5 | Qualitative map comparison routed to numeric select; absent numeric areas accepted by review but execution fails. No quantitative area result should be invented. |

## Why automatic review is insufficient

**399, manual correction of reviewer approval.** Physical page 7 has four names
under MQA Executive Leadership: Lucy C. Gee, Lola Pouncey, Adrienne Rodgers and
Mark Whitten. Its following first-column headings are DOH Executive Leadership
and MQA Management. The middle/right columns contain continuation of a different
group; they do not all inherit the first heading. The accepted runtime inventory
adds 13 names from these columns to the first four, producing 17. Physical page 9
has three names under Prosecution Services Staff, before Program Staff begins.
Direct full-page inspection therefore supports 4+3=7, not the published 17+3=20.
The automatic reviewer makes the same visual grouping error as the collector.
Its true support boolean was overridden in this audit; row 399 is not a success.

**660, constraint check missing in both runtime and reviewer.** Original physical
page 4 supports P1.1/T2EX for Port 1 and describes ports 0–3. This is the right
fact for earlier row 659, but row 660 asks about ports 10–13. The answer does not
satisfy that literal constraint. The reviewer approves the local pin/function
fact while overlooking the requested range; that approval is not accepted as
question-level success. No port 10–13 function should be fabricated or silently
substituted. A clarifying response may identify the mismatch.

**1086, repair the audit coverage before certification.** Automatic reference
images show earnings physical page 40, not the needed balance sheet. Manual
inspection of original physical page 39 confirms January 28, 2023 total assets
15,803 and cash 1,874, in millions; 15,803−1,874=13,929. This closes the source
verification gap without another paid reviewer or generation call.

**732, keep the interpretation dispute open.** Original physical page 16 shows an
Airbus chart panel and an Airbus Tweet row with value 5. The released answer counts
one panel; the label/reviewer interpret figures as the numeric Tweet figure 5.
The wording alone does not establish which task is intended or prove a whole-
document figure count. This row stays unresolved rather than declaring either
the label or the panel count universally correct.

## Failure families and what should remain unanswered

- **Routing:** 511 needs visual text extraction, not a numeric read. 517 needs
  qualitative spatial comparison, not selection from invented numeric areas.
  Its null/not_found operands are accepted by review but correctly cannot execute
  as numeric values. Type safety alone cannot select the right tool.
- **Provenance and location:** 366 needs period context; 637 already has a completed
  accepted count but final scope cannot connect printed 6985 to physical page 5.
  The result is retained, yet cannot be released. These are not simply retrieval
  misses. Carry verified document/section/page bindings through independent checks.
- **Coverage/membership:** 381 repeats whole-inventory false completeness, now a
  course-wide quiz list rather than USB functions. Direct original page 10 shows
  Quiz #7. 399 exposes sibling-heading and multi-column membership mistakes.
- **Derived headcounts:** 206 and 225 require composing percentages with sample
  size and population scope. About 541 and 738 are estimates from rounded survey
  percentages. The source does not support presenting them as exact observed
  counts. Preserve denominators, population bindings and approximation status.
- **Numerical notation:** 1021 initially labels grouped source strings with an
  incompatible notation and is rejected. Image repair selects the proper notation
  and succeeds. No escaping Decimal exception occurs, but this shows remaining
  contract/metadata sensitivity and an unnecessary repair cost.
- **Mismatched questions:** 384 requests a May 2018 revision, whereas the recorded
  document says Revised May 2016. 660 requests an unsupported port range. Avoid
  unqualified factual answers that ignore these constraints. Row 384 abstains but
  ends in ModelRetry, so its workflow is still unresolved.
- **Ambiguous measurement:** 366 could mean absolute percentage-point gap 2.4 or
  relative forecast shortfall about 35.8%; 732 also needs interpretation. These
  require expressing assumptions or clarification, not forcing the gold label.

These observations do not authorize relaxing source fidelity or creating
per-question rules. Numeric input validity, target membership, requested scope,
verified absence and presentation should remain separate application receipts.
No fixes were made during or after this measurement.

## Measurement and retained artifacts

Main-pipeline time totals 817.51 seconds; sequential wall time including startup and independent reviews is 1,278.73 seconds. Main usage totals 99 requests, 417,072 input tokens, 51,971 output tokens, 34,270 cached input tokens, 25 tool calls and 2 diagnostic retries. Dollar cost is unavailable because price metadata is not configured; separate review calls are excluded from usage totals.

Original PDF renders inspected manually: Best Buy page 39; strategic plan pages
7 and 9; controller page 4; social-media report page 16; course page 10. Poppler
was unavailable locally, so existing PyMuPDF rendered these read-only audit
images. Raw JSON, spans, captures, frozen selection and rendered images remain
local and ignored. This report preserves disagreements with automatic review.

Across this batch and the preceding ten, the same runtime yields ten verified
answers and fifteen unresolved outcomes on 25 new questions. That is a separate
current-runtime sample, not the historical ledger's cumulative success rate.

## Issue audit addendum

Audit addendum, 20 October 2026: the [code-and-state audit](../../../docs/adaptive-issue-audit.md) establishes `REPAIR_CHANGED_UNTARGETED_STRUCTURE` for 366 and `QUANTITY_ITEM_PAGE_INVALID` for 1072. Offline replay shows that 1072's fresh image pages [40,39,39] become [40,null,null] when old untargeted text operands are restored. Recovering 366's merge would expose a separate unsupported named-function/operand expansion failure. These are diagnosis updates, not reruns or corrected answers.
