# Ten previously untried questions: unchanged strict-output workflow

## Outcome

**7/10 successful task outcomes: six source-supported answers, one justified abstention, and three unanswered answerable/reference-answer questions.** No incorrect substantive answer was published in this batch. An abstention on an answerable question is not a success; reviewer booleans and safety-validation passes are not substitutes for task completion.

The selection was frozen before execution, excluding the 20 distinct rows already tried in adaptive runs. All ten were run once, sequentially, on main revision `9fd8ead`, across nine PDFs. Runtime code, prompts, model, embedding, index, retrieval/reranking settings, reasoning roles and budgets remained unchanged. There were no outcome-based substitutions or main-run retries in a new directory. Bounded application-level repair attempts inside a run remain reflected in usage.

| Row | Task | Outcome | Published response | Seconds | Model calls | Tool attempts | App retries |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 478 | Error descriptions for codes 88 and 188 | Correct source answer | Error 88: Boiler: over-temperature. Error 188: Heater error. [E2.S1] | 24.77 | 3 | 0 | 0 |
| 372 | All non-executive and independent company directors | Unanswered | I could not obtain enough evidence to answer this question. | 63.84 | 7 | 2 | 0 |
| 382 | Combined quizzes in Units 4, 5 and 6 | Correct source answer | 2 (calculation: 1 + 1 = 2) (count: 1 listed items) (count: 1 listed items) [E3.S1] [E1.S50] | 40.84 | 5 | 1 | 0 |
| 385 | Three top-row rectangle headings on printed page 2 | Correct source answer | ["STRATEGIC PRIORITY AREAS", "STRATEGIES", "OBJECTIVES"] [E3.S1] [E1.S21] [E1.S12] [E1.S11] [E1.S13] | 59.86 | 6 | 1 | 0 |
| 639 | Lowest total semantic-error percentage category in HOVER | Correct source answer | Subtask errors have the lowest total percentage across the HOVER hop groups: 2% (2-hop), 5% (3-hop), and 2% (4-hop). [E2.S1] | 54.32 | 8 | 1 | 0 |
| 661 | Minimum voltage of the bottom-left waveform symbol | Unanswered | I could not produce a verified answer from the documents. Please try rephrasing the question. | 85.91 | 10 | 3 | 1 |
| 1020 | FY2021 long-term debt / total liabilities including long-term leases | Correct source answer | COSTCO’s FY2021 Long-term Debt to Total Liabilities was **25.04%**. Using the specified definition, the numerator is $6,692 million in long-term debt (excluding current portion) + $2,642 million in long-term operating lease liabilities + $980 million in long-term finance lease liabilities, divided by total liabilities of $41,190 million. [E2.S1] [E3.S1] | 50.67 | 8 | 2 | 0 |
| 519 | Audience data source for the platform identified by its metrics | Correct source answer | The audience data source is eMarketer. The listed metrics identify the platform as Facebook, and the audience chart is labeled “Source: eMarketer.” [E2.S1] | 22.60 | 3 | 0 | 0 |
| 221 | Male 65+ internet versus home broadband percentage gap | Unanswered | I could not produce a verified answer from the documents. Please try rephrasing the question. | 58.50 | 8 | 1 | 2 |
| 220 | Headcount for a claimed July–September 2022 survey in the older-adult report | Correct abstention | I could not obtain enough evidence to answer this question. | 85.71 | 9 | 5 | 0 |

## Source checks and successful paths

- **478:** Original manual pages 88–89 bind code 88 to Boiler: over-temperature and code 188 to Heater error. The answer preserved both label relationships with three model calls and no tools.
- **382:** Original curriculum pages 4–6 list Quiz #2 under Unit 4 and Quiz #3 under Unit 6; Unit 5 has no separate quiz. The combined count is two. Application counting produced `1 + 1 = 2` after collection. The repetitive count annotations in the published response are a presentation issue, not a wrong answer.
- **385:** The strategy-map page is physical page 5, printed page 2. Its top row reads STRATEGIC PRIORITY AREAS, STRATEGIES, OBJECTIVES, left to right. Original-image collection recovered these headings after the initial context was insufficient; the published order is correct.
- **639:** Original paper page 8, Table 2, gives Token 8/20/18, Structure 19/13/57, and Subtask 2/5/2 across the three hop groups. Their totals are 46, 89, and 9. Subtask is the correct minimum category. The structured collector supplied already-computed totals as operands and `count_mode=total` with select mode; its cross-field contract failed before a quantity record was created. Later finalization released the correct category with the three printed Subtask percentages, without an unsupported numeric total. This is a correct source answer, but it does not demonstrate successful application-owned sum-then-minimum execution.
- **1020:** Original Costco pages 38 and 53 support `(6692 + 2642 + 980) / 41190 = 0.250400582...`, rendered as 25.04%. The definition excludes the current portion of debt and includes long-term operating and finance leases. The exact source ratio is equivalent to the published percentage; the stored label 0.25 is the ratio rounded to two decimal places. Percentage versus ratio presentation is reported separately from source correctness. The first quantity draft had correct inputs and formula but irrelevant `count_mode=total`, which the arithmetic coherence validator rejected. A later application text-calculation path recovered the result.
- **519:** Original slides 10 and 13 identify Facebook through the metrics and show Source: eMarketer on its audience chart. The answer correctly binds the platform and source with three calls and no tools.

## Three unanswered questions

### 372: incomplete source object and repair goal drift

The company-wide board table on original physical page 9 identifies five directors: R.A. Shah, Lalit Bhasin, Anup N. Kothari, C.M. Maniar, and O.P. Vaish. The run instead collected the three-person Audit Committee subset on page 11. The checker correctly accepted those transcriptions while rejecting complete-company coverage.

The repair did **not** supply a larger complete list. It returned the same three names, now as a count group instead of a categorical list. `REPAIR_CHANGED_UNTARGETED_STRUCTURE` rejected the mode/structure change. Relaxing list length alone would not fix the observed run: repair needs a missing-coverage search with the original list goal preserved and a different, company-wide source object. The current generic merge guard also rejects changed item cardinality, so future coverage-completion work needs a separate bounded append/replace contract rather than weakening all repair validation.

### 661: scalar visual reading routed as minimum selection

The collector proposed P2.7 (ENABLE), 0 V, in a select draft with one operand and `count_mode=total`. The draft violates select-mode coherence: selection expects at least two comparable inputs and does not use counting fields. No checked quantity record survived this contract rejection. Subsequent inspection/extraction did not establish the source need; a final 0.0 V candidate was rejected by scope validation, and the run exhausted its request reserve.

The benchmark label is 0.0. Original page 16 shows the bottom-left P2.7 ENABLE trace at its low/baseline level; page 15 states VSS = 0 V. The source reviewer considered 0.0 V a plausible inference but noted that the waveform does not explicitly label that trace minimum as 0 V. This is an unanswered reference-answer question with a source-inference ambiguity, not proof that accepting the rejected candidate without stronger binding is safe. A direct visual-value reading contract and grounded inference handling are needed; simply relaxing the final scope check would conceal the uncertainty.

### 221: correct male values lost at contract/provenance handoffs

The original demographic appendix on physical pages 16–17 gives male 65+ internet use 65% and home broadband 53%, so the gap is 12 percentage points. The collector found both correct values and the subtraction, but supplied `count_mode=total` in arithmetic mode. The cross-field validator rejected the draft before creating a checked quantity record.

There is also a latent page-identity defect: the selector requested physical pages 16/17/18, while the collector assigned printed page numbers 15/16 to the values. The first page number would be outside the selected image set if validation reached the page check. This is observable in the saved output, but it is not the first exception that caused this run to fail. Later finalizers proposed the correct 12.0 with a broad merged support ID; the original-page authority guard rejected the unbounded source window. Two finalizer attempts did not recover a narrow checked proof, and no answer was released.

The benchmark reference images for this row point to physical pages 7–8, which have no male rows. The all-senior values 59 and 47 happen to have the same gap of 12, so exact label agreement would not prove correct population binding. Manual original-PDF inspection used the actual male tables on pages 16–17. These benchmark reference pages are used only after generation; they did not cause the runtime failure.

## Correct abstention and unnecessary research

**220:** The question requests a 2022 survey headcount. The supplied report was published April 3, 2014 and describes the 2013 survey; a whole-document native-text search found no 2022 occurrence. The model identified the period mismatch and the difference between percentages and a requested headcount, and did not invent a 2022 number. Its final abstention passed security validation and was not an application-forced generation failure. That counts as a correct refusal within this source-document scope, not as a published numeric answer.

It nevertheless used nine model calls and five tool attempts, including four further searches for essentially the same unresolved year/headcount need. The quantity collector also failed output coherence. This is an efficiency/termination problem: newly returned source IDs do not necessarily mean the requested evidence need has progressed. A bounded search result is not global proof of absence, so a new stop policy must retain that distinction.

The standard after-run reviewer had no benchmark reference images for the unanswerable row. The manual date/full-document audit supplies the additional original-source check; no claim is made that the reviewer inspected every PDF page visually.

## Prioritized changes suggested by the evidence

1. **Use operation-specific output contracts.** Direct value reading, arithmetic, count, minimum/maximum selection, and categorical list operations should not require irrelevant fields from each other. Native strict JSON shape is useful, but cannot correct a cross-mode contract that rejects valid inputs. Keep unknown-field and source-value checks strong within each actual operation.
2. **Separate input correction from missing-coverage completion.** Preserve the original question goal and output type. Keep valid existing facts while locating the missing company-wide inventory; allow only source-grounded additions/deletions instead of reinterpreting a list as a count or blindly relaxing structural guards.
3. **Make page/evidence identity application-owned.** Return fixed image/source handles with explicit physical-page mapping, distinguish printed page labels, and keep narrow source IDs attached through extraction, calculation and finalization. A correct number does not justify bypassing missing proof or page-authority checks.
4. **Represent composed operations as bounded prepared steps.** For totals followed by a minimum, extract source-printed cells, calculate category totals in code, then select among the resulting typed values. Avoid asking a single selector to invent computed operands.
5. **Stop on evidence-need progress, not just new chunk IDs.** Retain unresolved bindings and similar failed attempts; terminate repeated searches without treating one bounded search as a corpus-wide absence proof.
6. **Validate against original source relationships.** Audit reference-page errors, source role, population and units independently of gold-string match and reviewer booleans.

The first implementation pass should address operation contracts, goal-preserving repair and provenance, then recheck the three unanswered rows plus previously successful controls. Composed-operation and no-progress optimization can follow without increasing model-call budgets or adding a mandatory answer-writing call.

## Usage, controls and record policy

Main runs: **547.02 seconds**, **67 model calls**, **265,214 input tokens**, **26,607 output tokens**, **16 tool attempts**, and **3 bounded application retry attempts**. Timing excludes dependency/model loading and separate review. SDK retry settings remained zero.

Separate diagnostic reviews: 10 calls, 107,636 input tokens and 16,271 output tokens. Model prices were not configured; dollar cost is unavailable, not zero.

All runs retained the existing per-question 10-request, 120,000-token, 240-second diagnostic budget, six research/tool attempts and finalization reserve. Runtime code hashes and profile settings are checked for consistency. Main generation never received gold answers or benchmark reference pages. Runs were scoped to each source document; this is not an open-corpus retrieval score or the full 120-question benchmark.

There are now **30 distinct adaptive questions tried**: **26 historical source-supported published answers**, **one correct refusal**, and **three unresolved rows**. These counts span development revisions. On the unchanged current workflow, the prior two targeted successes plus this batch give eight published answers, one justified refusal and three unanswered cases across 12 distinct questions; the older 18 successes have not been rerun on this workflow.

Raw selection/profile JSON, result JSONL, full typed state, model captures, spans, review packets and source-page renders remain local and ignored. Only this English Markdown summary and ledger updates are intended for Git. Runtime code was not changed during this measurement.
