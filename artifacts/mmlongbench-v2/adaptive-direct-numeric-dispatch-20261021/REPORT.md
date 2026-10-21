# Direct dispatch for planned numeric presentation

Date: 21 October 2026. Branch: `fix/cumulative-search-progress`, based on main `5c25898`. This follows the separately measured cumulative search-progress change on the same working branch.

## Final outcome

- **642:** source-correct [64.4, 62.5, 62.2], **five requests / 52.56 seconds**. The preceding frozen batch used six / 80.46. Trace confirms the speculative answer call is skipped.
- **662:** source-correct **9 waveform figures**, distinct physical pages **["11", "12", "13", "16", "18", "20"]**, **six requests / 81.18 seconds**, successful publication and validation. The preceding search-progress batch used six / 73.84; this is a correctness/robustness recovery, not an established latency gain for 662.
- Final local suite: **2,467 passed**, four skipped, five deselected (50.86 seconds). Ruff and mypy pass.
- No distinct questions added: historical coverage remains **101/120 (84.2%)**, 19 unresolved. These development checks do not establish aggregate p90/p95 improvement.

The initial six-question group and every unsuccessful 662 follow-up are retained below. Four distinct unaffected positive/negative controls (387, 1079, 382, 365) retain their expected outcomes in the initial group; the final affected checks are targeted reruns, not a newly frozen full six-question benchmark.

## Problem and change

In the preceding frozen six-question batch, row 642 already had a valid single need specifying numeric sorting, descending order and one decimal place. Nevertheless, the fast-answer model attempted a source answer for 31.12 seconds before deferring to source selection and collection. The complete run took 80.46 seconds / six model requests.

The application now dispatches that existing numeric-presentation contract directly to the existing collection path. Eligibility uses typed plan fields, not question text, dataset names, expected values or a new model classifier: a ready single unresolved lookup/compare/sort need, explicit numeric precision and ascending/descending presentation. Source selection, independent input/coverage checking, application sorting/rounding and final semantic scope remain active. The original source readings are retained before presentation transformations.

Plain lookup, text sorting without explicit numeric precision, composite plans, satisfied needs, unready plans and disabled/unavailable tools retain their existing fast-answer behavior. Image acquisition must be available for an explicitly image-bound need. Direct numeric dispatch excludes that same need from generic visual pre-acquisition, avoiding two acquisition paths for one task. The application also requires room for three collection-stage requests plus final scope when enabled; otherwise it preserves the existing fast path.

If selection is unavailable or collection remains unresolved, the existing research/finalization path continues. No new refusal rule, answer-generation prompt, planner output field, role effort, global budget, embedding setting or reranker setting is introduced. The follow-up inventory checker contract is described below.

## Observability

`research.fast_answer.route` records whether fast answering is enabled, whether its attempt is skipped, the selected need and one of `planned_count`, `planned_numeric_presentation`, `direct_answer_eligible` or `disabled`. It contains no source text.

## Verification and measurement

Offline checks and a frozen sequential measurement are in progress. Six questions are selected before execution: 642, 387, 1079, 382, 365, 662. Compare with the immediately preceding search-progress batch, which retained five source-audited answers and one safe negative. The harness, roles and budgets are unchanged; no paid after-run judge. Raw results and spans remain ignored. No historical question total changes from these reruns.

## Initial routing observation

The first narrow predicate required the planner operation to be exactly `sort`. In this frozen batch, 642's valid plan instead uses `lookup`, while still explicitly specifying descending numeric order and one decimal place. It therefore retains the speculative answer call: the source-correct result passes in 76.68 seconds / six calls, with 20.97 seconds in the answerer. `research.fast_answer.route` correctly records `direct_answer_eligible` rather than a skip. This does not demonstrate the intended optimization.

The two plan labels describe compatible source acquisition for the same typed presentation operation. The follow-up predicate will accept `lookup`, `compare` or `sort` only when the same single numeric-presentation contract is explicit. Scalar lookups with source order remain on the fast path. No prompt or question-specific matching is needed. The initial batch remains frozen until completion; final eligibility changes will be measured separately.


## Initial frozen six-question results

The first narrow routing predicate retains five expected outcomes and fails to publish 662. All six terminal outputs pass runtime validation; this is **not six successful answers**. Source correctness is judged against the existing source-audited outcomes, not validation alone.

| Row | Outcome | Seconds | Model calls |
| --- | --- | ---: | ---: |
| 642 | Correct answer | 76.68 | 6 |
| 387 | Correct answer | 36.01 | 3 |
| 1079 | Correct answer | 42.85 | 6 |
| 382 | Correct answer | 46.80 | 5 |
| 365 | Safe negative | 50.81 | 7 |
| 662 | Incorrect abstention | 112.12 | 9 |

The application/harness hashes remained frozen during this entire group. In 365 the last two searches add no evidence and expose no previously hidden support. The old immediate-selection comparison would classify both as progress; the cumulative rule instead stops acquisition and allows safe negative finalization. Seven calls are observed versus nine in the preceding batch. Future model actions under the old rule are unknown; this is a demonstrated progress-invariant difference, not an isolated two-call causal estimate.

### Inventory regression found in 662

All nine source occurrences are extracted. Every local window and whole-document coverage pass. The reviewer rejects the operation because the planner's free-text counting-unit description includes a page entry per figure, while the application's page projection is a distinct ascending page list. This is a planning-to-review authority error: source-local observations are correct, but an unverified planning narrative is treated as an output requirement. Subsequent generic research exhausts the request reserve and publication fails at 112.12 seconds / nine requests.

The follow-up review receives the original question, original whole-source overview, detail images, source-located occurrences and the explicit application operation, without the planner narrative. The checker still independently decides input accuracy, membership, local/global coverage and operation compatibility with the question. Unsupported operations still prevent aggregation; a regression test exercises that rejection. Planner instructions remain acquisition hypotheses rather than source evidence. Neutral application group labels and an explicit source-occurrence unit replace the planner narrative in generated count proofs, so that narrative cannot become a verified assertion later. The original plan remains in typed state for auditing and acquisition.

The numeric dispatch predicate also accepts `lookup`, `compare` and `sort` when the same explicit numeric ordering/precision contract is present. Scalar lookups with source order remain on their prior fast path. Tests cover all three labels and preserve unavailable-source recovery, composite/text/scalar/disabled-tool paths and request-budget preflight.

## Follow-up

After final local checks, rerun only affected 642 and 662 sequentially, with all application/harness hashes frozen again. Retain the failed initial group above. No broader tail-latency improvement is claimed from these few development runs.

## Final local verification

Before the auxiliary OCR-locator correction, the application passes **2,452 tests**, with four skipped and five deselected (55.85 seconds). Ruff passes; mypy passes for 166 source files. Tests exercise direct numeric dispatch for lookup/compare/sort, application ordering/rounding from unchanged printed operands, unavailable-source research/finalization, scalar/text/composite/satisfied/unready/disabled-tool guards and request preflight. Inventory tests assert that planner output rules do not enter the source review or generated proof, while incomplete coverage and genuine operation mismatch still prevent publication and retain supported observations. Full verification still receives the original overview and detail images.

### Follow-up 642

The final predicate dispatches directly: `research.fast_answer_skipped=true`, reason `planned_numeric_presentation`. The source-correct output remains `["64.4", "62.5", "62.2"]`, with all runtime validation passing and no repair. Calls are exactly need planner, quantity selector, collector, checker and final scope: **five requests / 52.56 seconds**, versus six requests / 80.46 seconds in the preceding search-progress batch (and six / 76.68 in the initial narrow-predicate attempt). One speculative answer call is demonstrably removed. The observed 27.90-second decrease is a single development comparison, not a production tail-latency estimate. Input/output usage is 20,268 / 4,156 tokens; API prices remain unconfigured.

### Follow-up 662: correct inventory, auxiliary locator failure

The follow-up independently approves all nine occurrences, every local window, whole-document coverage and the application operation. The planner-narrative conflict is removed. Final scope also returns supported checks, no omissions and no semantic objections, with original-image requirement witnesses. However, an additional OCR witness for a supported requirement points to E6.S1 line 88 outside that source's line range. The validator rejects this redundant locator even though that same requirement has valid original-image witnesses. Research then reopens and finalization fails under the request reserve: **109.40 seconds / eight calls**, runtime validation fails. This remains a failed live result, not a successful recovery.

The final local correction treats original-image support independently of optional OCR locators. Only a line-resolution failure on an already claim-bound support can be ignored when that same requirement already has valid original-image evidence. Unknown support IDs, image/claim mismatches, unsupported/unknown verdicts and requirements without valid image evidence remain failures. Primary claim witnesses are unchanged and remain strict. No source text is reconstructed, fuzzy matched or invented. The ignored count is exposed as `validator.ignored_optional_text_witnesses`; raw diagnostic capture retains the original references.

Exact local replay of the saved judgment and retained correct candidate passes both requirement validation and primary claim validation with **one ignored optional OCR locator and zero new model calls**. This is an exact witness-validation replay, not a new live end-to-end run or an authorization replay. A final single-row 662 run will check the complete application path separately.

The final application including the source-authority correction passes **2,458 tests**, four skipped and five deselected (48.10 seconds). Ruff and mypy pass. Six additional tests cover independent original-image support, missing/unknown/wrong-claim images, unknown support IDs and an unknown semantic verdict. A failed primary claim witness is still handled by the unchanged strict claim resolver.

### Complete-path check exposes a missing coverage continuation

The next live 662 run safely abstains at 108.67 seconds / nine requests. All nine occurrences are correctly read, every local window is complete and the operation is supported. The independent global reviewer asks for a detail image of excluded page 5: its external-clock-source illustration cannot be confidently classified from the overview alone. This is a legitimate unresolved acquisition request, not grounds to force completeness. It occurs before final scope, so this live run does not exercise the optional-OCR correction. The exact replay above remains the evidence for that correction.

The existing flow loses the actionable page request in free-text issues and falls into generic research. The final continuation adds a typed `missing_detail_pages` field, bounded to three pages. Application code validates the requested physical pages against the same source, excludes already inspected pages, retains the previous review and window records, and dispatches one extra window without another selector or retranscription. One combined follow-up review still independently decides coverage and operation; continued uncertainty remains unresolved. There is at most one such continuation.

The request preflight counts remaining extraction, checking and final scope once, avoiding an unnecessary extra reservation in the old inventory preflight. Global request/token/time limits and the model-call layer's own reserve checks remain unchanged. Insufficient remaining capacity stops before further extraction, preserving typed findings and the pending page request. No absence or completeness is inferred from budget exhaustion.

Tests cover successful closure after an empty extra page, insufficient budget with retained findings, unresolved follow-up with no repeated loop, and an out-of-document page request that never executes. The subsequent single-row check is saved under `coverage-followup/row662`.

### Coverage follow-up works; redundant primary OCR locator still blocks release

The coverage-followup run executes the new mechanism: the first review requests page 5, `inventory.coverage.followup` reuses two checked windows, one new low-effort extraction inspects only page 5, and the next review approves complete coverage and the operation. Nine occurrences remain unchanged. Scope gives supported checks, no omissions/objections and valid semantic requirements; the optional-OCR correction is exercised (`ignored_optional_text_witnesses=1`). Nevertheless the old strict primary resolver rejects one additional OCR range, E6.S1 lines 57–60 where the source has 59 lines. Nine other primary references are valid. The run fails release at **108.90 seconds / eight calls**. This failure is retained.

The final primary-locator correction is narrower than a general citation filter. Only claim indexes produced by `semantic_scope_projection` for an exact, locally reexecuted image-backed application candidate are eligible, with original-image claim bindings present and all semantic requirements passing. The model must still support the whole claim with reason NONE. A malformed additional line range to an already claim-bound source can be dropped only when at least one valid exact source witness remains. Unknown sources, ordinary/model-edited claims, unsupported verdicts, empty source witnesses and all-invalid witness sets still fail. No line is clamped or quote rewritten. Diagnostics expose `validator.ignored_verified_claim_ocr_locators`.

Exact replay of this saved candidate and scope judgment derives eligibility through the same application projection, validates all semantic requirements, and retains the nine valid primary references. Both validators pass with one optional requirement locator and one redundant primary locator ignored, **zero new model calls**. This is a local validation replay, not a new end-to-end result. An original-PDF integration test exercises the complete verification method with a redundant invalid locator, while separate negative tests retain strict rejection.


## Final 662 complete-path result

`verified-authority/row662` publishes **Total: 9; pages ["11", "12", "13", "16", "18", "20"]**, with runtime validation passing, six model calls, one tool, no retries or repairs, 59,639 input / 6,242 output tokens and 81.18 in-run seconds (94.67 process seconds). Application/harness hashes remain unchanged during the run.

| Model stage | Seconds |
| --- | ---: |
| Need planner | 5.37 |
| Whole-source page selection | 16.54 |
| First narrow extraction | 4.19 |
| Second narrow extraction | 5.00 |
| Independent inventory check | 14.61 |
| Final semantic scope | 21.63 |

In this run the first independent source review closes coverage, so no additional page is requested. Scope references are valid, so neither redundant-locator tolerance is needed in this particular final run. The previous coverage-followup run demonstrates the extra-page mechanism live and exercises requirement-image authority; exact saved-judgment replay and offline original-PDF integration tests demonstrate primary-locator recovery. Do not attribute the final live timing to a branch it did not exercise.

The final 642 result is saved under `followup/row642`; the final complete 662 result is under `verified-authority/row662`. Neither is substituted into earlier failed raw results. Only this Markdown report is intended for version control.

## Remaining efficiency work

642 removes a demonstrably redundant call. 662 still spends 14.61 + 21.63 seconds in two independent reviews; page planning takes another 16.54 seconds. A requested extra page can still require a combined review that re-exposes previously checked windows. Dependency-scoped review reuse is the next candidate, preserving whole-document closure and invalidation when source/claim/operation changes. Measure larger frozen cohorts and repeated samples before claiming lower tail latency. API dollar cost is unavailable while model prices are unconfigured.
