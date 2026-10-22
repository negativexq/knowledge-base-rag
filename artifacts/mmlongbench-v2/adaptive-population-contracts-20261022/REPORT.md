# Aggregate population calculations and source limitations

22 October 2026. This work continues the [original-source audit](../adaptive-composition-audit-20261022/REPORT.md) and [four-question runtime baseline](../adaptive-population-four-20261022/REPORT.md). It changes source-operation contracts and handoffs, not embedding, retrieval ranking, model choice, effort or global request/time/token limits. Runs are sequential; each batch freezes application and harness hashes before its first row and verifies them before and after each row. No paid answer judge is added.

## Implementation

- A typed aggregate-population need selects a numeric read or arithmetic operation, rather than an inventory of individual respondents. Application code executes independently reviewed formulas.
- Arithmetic operands retain population, rate denominator and period. An approximate result is distinct from an exact respondent count; the source's printed digits remain unchanged. Qualification travels through repair, scope validation and final publication.
- A typed source limitation explains a source-bound missing or incompatible input. It requires independent scope approval and retains the ordinary numeric/citation checks. It cannot certify whole-document absence from a partial read. An unverified final limitation falls back to ordinary insufficiency without another answer-generation loop.
- Checked partial inputs retain their grounded objections. Source handoff prioritizes authorized same-version, same-page text units that actually contain those values. These IDs are navigation hints, never automatic citation authority.
- Numeric-review correction schemas expose only notation formats syntactically compatible with the original display. If an existing format is already valid, a correction cannot change its value. Ambiguous punctuation remains a source-review decision: the application does not infer a locale. An invalid no-op correction is rejected.
- Extraction, numeric review and final scope checks share source-category granularity and qualified-estimate semantics. Explicit exclusive subsets and incompatible denominators remain distinct.
- A witnessed material intent ambiguity can use the existing reviewed clarification disposition. The collector returns it before another extraction repair only when the operation objection is grounded, the disposition is verified, and existing successful work does not invalidate it. Missing inputs alone are not grounds for early clarification.

New observations include `quantity.notation.correct` and `quantity.clarify`, with quantity/disposition IDs. Existing normalization, review, execution, scope and finalization spans retain failures and intermediate records.

## First implementation batch

Application seconds exclude subprocess/model startup. Successful runtime validation is not independent semantic correctness.

| Row | Seconds | Model requests | Source/workflow assessment |
| --- | ---: | ---: | --- |
| 206 | 52.63 | 5 | Publishes approximately 541 sample-equivalent adults, with qualification. |
| 219 | 156.43 | 9 | Generic insufficiency; exclusive SNS wording remains unresolved. |
| 225 | 155.34 | 8 | Source limitation instead of approximately 738; a correct four-input draft was rejected because its interpretation had 305 characters against a 300-character schema limit. |
| 216 | 140.72 | 9 | Generic insufficiency; limitation cited a sample-table heading rather than the actual 710 row. Numeric rejection was correct. |
| 387 | 26.00 | 3 | Correct Rick Scott text control. |
| 382 | 73.11 | 6 | Correct two-quiz count control. |
| 1079 | 69.36 | 5 | Correct 0.627 arithmetic control. |
| 642 | 60.91 | 5 | Correct numeric-presentation control. |
| 365 | 82.75 | 9 | Technical/unverified final outcome after source-limitation checking. |

The interpretation allowance was raised to 800 characters. The 216 citation loss was fixed through source navigation, not a numeric-validation exemption. Offline replay accepts the saved 225 plan and produces 738; adding the actual 216 value-bearing source makes the existing numeric check pass. These replays are boundary checks, not fresh end-to-end certifications.

## Citation and finalization follow-up

| Row | Seconds | Model requests | Source/workflow assessment |
| --- | ---: | ---: | --- |
| 225 | 134.33 | 9 | Still source limitation: input reviewer imposed a narrower daily category and disputed the internet base. |
| 219 | 194.80 | 10 | Still generic insufficiency; same category ambiguity repeated rather than focused clarification. |
| 216 | 129.16 | 7 | Publishes a source-bound explanation: 18% is known, but a compatible Democratic-only respondent base is not established. No invented 128-person count. |
| 206 | 163.69 | 9 | Regresses to limitation. The second numeric review accepts the approximate operation, but retains `1,503` under invalid canonical notation; execution fails with `QUANTITY_NUMERIC_INPUT_UNRESOLVED`. This is a notation handoff defect, not rejection of approximate arithmetic by that review. |
| 365 | 32.69 | 3 | Correct bounded company mismatch explanation. |
| 382 | 51.39 | 6 | Correct two-quiz control. |
| 1079 | 67.76 | 9 | Correct 0.627 arithmetic control; repeated collection remains an efficiency cost. |

## Notation and clarification recheck

The four target/control rows 206, 225, 219, 216 run sequentially on a new frozen snapshot. Results:

| Row | Seconds | Model requests | Source/workflow assessment |
| --- | ---: | ---: | --- |
| 206 | 109.40 | 5 | Approximately 541 adults published with the sample-equivalent qualification. The collector selected valid notation initially; this run does not exercise a live notation correction. |
| 225 | 159.72 | 8 | Generic insufficiency. A repair finds the frequency pages but fails with `QUANTITY_REQUIRED_CONTEXT_TOO_LARGE`: automatically attached native-page text is incorrectly treated as explicitly required context. A later approximate 738 draft is not a verified bounded-page calculation and is withheld. |
| 219 | 195.35 | 8 | Focused clarification, not an invented exclusive-subgroup count. Finalization supplies it after unsuccessful repair. |
| 216 | 123.93 | 9 | Correct source-bound 18% explanation; Democratic-only sample base is not supplied. |

A separate offline replay feeds the previously failed 206 assessment into the new native review schema: the invalid canonical correction is rejected. Replacing only that metadata with the notation established in the source audit produces 541 and preserves the original display. This replay does not add a fresh source or scope review. The 219 outcome is a focused clarification: whether “only use SNS” means the chart’s “Use SNS” group or SNS-exclusive users. It is semantically appropriate, but it comes from the finalizer after a collector timeout; the new early reviewed-disposition dispatch was not exercised in this live run. Its branch is covered offline. The 216 limitation preserves the 18% finding and avoids the incompatible combined subgroup base.

### Automatic context repair

The 225 follow-up preserves explicitly selected context as required. Automatically attached original-page context is admitted within the existing optional-context budget, with no truncation or limit increase. Excluded automatic text remains in typed application state and its IDs are recorded in `quantity.context.bind`; exclusion is not a source-closure receipt. The selector's explicit authority still cannot be evicted by optional text. A new regression test exercises this exact application-level distinction with unrelated synthetic data.

The context-budget recheck of 225 completes in **169.44 seconds / nine requests**, still generic insufficiency. The size guard no longer fails. Four inputs and the correct approximate expression survive, but the reviewer cannot establish the internet/email-to-internet-user relationship. A matching 59% introduction paragraph already exists as an authorized source unit and is not passed to that review. No numeric check is bypassed.

### Rate-context and page-selection follow-up

The first rate-context attempt runs 225 and 216 sequentially. Row 225 takes **141.52 seconds / seven requests** and publishes a source limitation; its selected page IDs do not cover the requested physical pages, so it fails before extraction and does not exercise the new context handoff. Row 216 takes **162.25 seconds / ten requests**, retaining the correct missing-denominator explanation.

Offline inspection also finds that a global top-three context ranking repeats the downstream frequency chart and a short table cell while missing the rate's explanatory paragraph. The final handoff allocates a candidate to each conditional input, preferring explanatory text with relevant binding terms rather than isolated numeric cells. Candidates are literal, short, visible, authorized, same-source and same-version; their numeric/lexical matches cannot approve a population join. The existing independent checker remains authoritative and the context/request budgets do not increase.

The native page catalog now ranks question-specific lines above repeated report headings and survey footers within its existing six-line/character allowance. Explicit requested pages may resolve to existing same-version catalog authority even when the selector omits the redundant paragraph ID. Hidden, foreign, stale, absent and non-catalog authority remains rejected. This resolves a tool-argument handoff, not an instruction to trust arbitrary page numbers.

An offline replay of the saved 225 draft now selects the source's 59% introduction paragraph and the frequency explanation. The original PDF's physical-page-4 catalog now contains daily/weekly frequency labels instead of only generic prose and headers. These are selection-boundary checks, not fresh answer certification.

A new frozen sequential batch runs only 225 and the incompatible-base control 216 after these changes. Row 225 completes in **195.82 seconds / eight requests** and publishes **approximately 738 sample-equivalent people**, using `1526 × 59 / 100 × (71 + 11) / 100`. The initial population-join objection is preserved; repair opens physical pages 2, 4 and 6 and independently verifies the matching internet-user rate and survey base. No finalizer answer-generation call is needed. The full source category and rounding/weighting limitation are published. Latency remains high; the four-target batch is not evidence of a general tail improvement. The 216 control completes in **173.41 seconds / ten requests** and publishes the known 18% while explaining that the Democratic-only sample count is not supplied. It does not compute 128 from the combined Dem/Lean Dem base. Both rows finish with released, source-bound outcomes; the preserved repair and finalizer overhead remains an efficiency limitation.

| Latest target/control outcome | Model requests | Application seconds | Accepted-total treatment |
| --- | ---: | ---: | --- |
| 206: approximately 541 sample-equivalent adults | 5 | 109.40 | New qualified calculation |
| 225: approximately 738 sample-equivalent people | 8 | 195.82 | New qualified calculation |
| 219: clarify chart SNS group versus SNS-exclusive users | 8 | 195.35 | No numeric-answer promotion |
| 216: 18% known, Democratic-only base not established | 10 | 173.41 | No benchmark-answer promotion |

These latest outcomes come from the scoped follow-up batches above; they are not a single fresh 120-row score. The final source-binding patch is measured on 225/216; 206/219 retain their earlier scoped results.

## Validation and accounting

Current offline validation: 2,525 tests passed, four skipped, five deselected; Ruff and mypy (169 source files) pass. Tests exercise aggregate dispatch, approximate metadata, source limitation release, unchanged numeric checks, actual-value source navigation, source/version/visibility isolation, native notation choices, prevention of valid-value reinterpretation, bounded clarification dispatch including unsupported witnesses, available answers and invalid diagnostics, automatic versus required context budgets, rate-hint rejection isolation, catalog-page authority, and query-specific native catalog labels.

Usage remains available in local ignored results/captures/spans. API pricing is not configured for these runs, so cost is unknown, not zero. Failed and successful attempts remain separate. Final source-grounded qualified estimates for 206 and 225 add two historical accepted outcomes: **103/120 (85.8%)**, comprising 81 supported answers, four qualified calculations, 18 correct refusals and 17 unresolved. Clarification 219 and source limitation 216 are not counted as new accepted answers. This is historical distinct-question coverage, not a fresh 120-row accuracy measurement. The unrelated TechQA semantic-score CSV is outside this work.
