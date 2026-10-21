# Adaptive workflow latency audit

Date: 21 October 2026. Read-only analysis of saved results and OpenTelemetry spans; no new API runs and no runtime edits for this audit.

## Finding

The recurring cost is repeated work across application/model boundaries: selecting evidence again, retranscribing supported objects, rechecking unchanged claims and restarting research after a presentation or coverage handoff fails. One slow planner is significant in 662, but is not the universal bottleneck. Expensive model review and repeated retrieval/reranking both contribute.

The proposed general rule is: **continue from the unresolved obligation while preserving accepted evidence and computations**. A stage should receive the relevant state delta, its exact task and sufficient original evidence. Successful completion should be reusable under the same source version, question constraints and operation. Reuse does not establish completeness or authorize an unsupported answer.

## Sample and method

354 span files were found. 353 have a matching single-row result and usable model spans, covering 120 distinct questions. One unmatched/nonusable pair is excluded. Analyze all attempts for recurrence, the 76 attempts dated 21 October for recent failure modes, and the latest saved attempt per question for deduplicated timing. “Latest” is ordered by trace start time, not file modification time. These are development runs with different implementations and repeated known questions, not a controlled performance benchmark or an accuracy reevaluation.

Model time is the sum of `llm.request` span durations, including failed/timed-out requests. In-run time is `result.seconds`; process startup is excluded. No parent span is added to its children. Retrieval/reranking spans overlap their containing search spans, so those durations must not be added together. Percentages of model time below are not percentages of end-to-end latency. Validation passing is not independent proof of source correctness.

| Sample | Attempts | Distinct questions | Median in-run seconds | Median model calls | Model time / summed in-run time |
| --- | ---: | ---: | ---: | ---: | ---: |
| All usable history | 353 | 120 | 54.40 | 6 | 78.4% |
| 21 October attempts | 76 | 35 | 62.88 | 7 | 76.9% |
| Latest saved attempt per question | 120 | 120 | 48.70 | 6 | 76.8% |

## Where the time goes

Latest saved attempt per question:

| Model role | Calls | Share of model-span time | Median seconds per call |
| --- | ---: | ---: | ---: |
| `quantity_checker` | 94 | 19.9% | 7.79 |
| `quantity_collector` | 93 | 18.3% | 7.68 |
| `scope_validator` | 98 | 16.9% | 6.26 |
| `need_planner` | 120 | 16.7% | 6.03 |
| `quantity_selector` | 104 | 13.0% | 4.81 |
| `answerer` | 95 | 6.7% | 2.94 |
| `reader` | 88 | 5.1% | 2.77 |
| `finalizer` | 22 | 1.4% | 2.82 |
| `source_selector` | 9 | 1.2% | 6.25 |
| `scoped_extraction_checker` | 3 | 0.4% | 6.75 |
| `extractor` | 5 | 0.4% | 3.42 |
| `answer_repair` | 1 | 0.1% | 5.78 |

Quantity checking plus final scope account for 36.8% of model time in the deduplicated sample. Collection accounts for 18.3%, need planning 16.7%, quantity selection 13.0%. Therefore the “extraction is cheap” conclusion applies to the new narrow 662 path; it must not be generalized to existing collectors.

Reranking is material too: 177 rerank spans total 1,096.3 seconds, with a 6.02-second median, versus 0.48 seconds for query embedding. Initial retrieval is included, and tool searches contain their own reranking. This is observed local runtime cost, not evidence that retrieval quality is wrong. Optimize repeat work before changing ranking behavior.

## Repeated patterns

| Latest-attempt group | Attempts | Median in-run seconds |
| --- | ---: | ---: |
| Exactly three model calls | 27 | 23.92 |
| Exactly one quantity collection | 49 | 45.57 |
| Multiple quantity collections | 22 | 79.52 |
| Exactly one scope call | 80 | 41.26 |
| Multiple scope calls | 8 | 62.34 |

These are descriptive associations, not causal savings: multi-page and difficult questions legitimately require more work. A repeated role alone is not a bug.

### 1. Selection churn can count as progress

In the 76 recent attempts there are 82 `tool.search` spans. 56 add no new support IDs; 37 of those still report progress. In ten of those 37, no selected support ID is first seen in the prior `research.context`/`evidence.search.focus` history either. The latter ten occur across rows 207, 222, 365, 367, 508, 520, 1079 and 1084.

Current code in `app/llm/adaptive.py` sets progress when selected IDs differ from the immediately previous selection. A previously seen item can therefore become “progress” when selected again after a different set. That resets the consecutive-no-progress counter. This is a concrete mechanism, not proof every affected search is useless: revisiting evidence can resolve a new relationship or reveal context the model had not received.

In the recent normal-ten row 1079, six searches consume about 41.8 seconds, with five adding no support IDs. Reranking inside each search takes roughly six seconds. The result is published only after the research turn limit and finalization. A correct final answer does not mean the intervening acquisition was efficient.

### 2. Missing boundaries trigger full recollection

In the final 382 control, pages 4 and 6 already provide two supported quiz occurrences. The review objects to missing unit/list boundaries. The next pass inspects pages 4, 5 and 6, retranscribes and checks the count again, then publishes two. This follow-up contains useful new boundary evidence, so deleting it would weaken correctness. The optimization is to acquire/check the missing boundary while retaining the supported occurrences. Two selectors take 21.06 seconds, collectors 41.41 seconds, checks 22.83 seconds. Total runtime is 110.06 seconds versus the earlier five-call control's 68.71 seconds.

### 3. Representation errors reopen solved semantic work

662's verified-windows attempt already had nine figures, complete source coverage and the correct prepared page list. Semantic projection hid the count result; coverage then reported the count/list absent. Repair and subsequent research ended without publication at 148.52 seconds. Showing the actual count answer to semantic coverage recovers publication at 104.89 seconds / six calls. The final application count, source binding and original-image check remain active.

642's numeric-presentation report records the same broader category: a correct source reading is lost in sorting/rounded-display/proof handoff. Typed application output fixes it without rereading the PDF. These are application representation problems, not evidence for stronger answer prompts.

### 4. Broad review can dominate the long tail

The overlarge 831 inventory-followup takes 251.75 seconds, with four scope model calls, timeouts and finalizer attempts. The scope spans alone total about 162 seconds. The later sparse follow-up preserves the original supported answer and appends only identified missing activities: 72.47 seconds / five calls. Both are documented in the [material coverage report](../artifacts/mmlongbench-v2/adaptive-material-coverage-20261021/REPORT.md). Differences are observational, not an isolated causal experiment.

In the final 662 run, planning takes 38.57 seconds and the two reviews take 38.20 seconds. Its two narrow extractions take only 7.81 seconds. Final scope receives 28,564 input tokens while the quantity review receives 13,185. This indicates substantial repeated context, but some original-image review is intentional and must be retained where semantic judgment depends on it.

## Proposed general workflow

Keep typed application state organized around evidence, checked observations, unresolved obligations and prepared results. Existing structures should be extended where possible rather than adding a second parallel state system.

1. **Plan the needed work.** Identify source scope, requested object, constraints and operation. Replan only if new evidence changes that plan or a reviewer identifies a specific gap. Keep decisions compact; explicit reasons are most useful for uncertainty or exclusion.
2. **Acquire and extract the missing part.** Read a missing page, header, boundary or figure. Reuse supported observations from immutable, authorized source versions. Do not ask an extractor to rewrite an entire accepted inventory to add one page.
3. **Review the relevant change.** Check source reading, object membership and coverage at their proper scopes. Retain the independent whole-source closure check for exhaustive questions. A source-local success is not global completeness.
4. **Execute deterministic work in code.** Counts, arithmetic, numeric sorting, deduplication, unit conversion and final formatting use typed approved inputs. Do not open research again merely to express these results.
5. **Finalize independently.** Semantic scope checks whether the actual prepared answer fulfills the question. Reuse existing approvals only for unchanged claims/evidence/constraints. A new claim or changed dependency invalidates the relevant approval. A stopped research loop still publishes a supported prepared result when release checks allow it.

Research progress should distinguish new source evidence, newly exposed evidence, checked facts, resolved obligations and presentation-only changes. Selected-list churn alone should not repeatedly reset progress. Absence of new support IDs must not automatically stop research: a new verified relationship or covered boundary can be real progress. Conversely, acquisition exhaustion is not proof the answer does not exist.

A review objection should identify a specific unsupported claim or unresolved obligation and the evidence needed to resolve it. Review output should remain compact. Avoid regenerating all findings and rationale on every successful check. Deterministic checks should not be delegated back to the model.

## Optimization order

| Priority | Change to measure | Why | Preserve |
| --- | --- | --- | --- |
| 1 | Cumulative progress tracking and reuse of prior search results | Search churn occurs in both answerable and negative questions; each repeated retrieval also pays reranking | Newly exposed evidence and genuinely new semantic work must still count |
| 2 | Missing-boundary/page/relationship completion without full recollection | Repeated collection is widespread; 382 shows an exact trace | Source/version bindings, independent input review and global closure |
| 3 | Dependency-scoped review reuse and compact model payloads | Reviews consume the largest combined model share | Invalidate approvals when claims, scope, operation or evidence change |
| 4 | Direct deterministic publication of prepared results | Avoids representation errors reopening research | Existing release, provenance and numeric checks |
| 5 | Smaller planning contracts and selective effort experiments | Planning is a universal fixed cost and sometimes a long-tail bottleneck | Uncertain-page inspection and semantic judgment |

Do not begin by disabling judges, lowering every effort, truncating source quotations or capping all questions to the same short loop. These would mix efficiency changes with correctness regressions. No new per-question rules are proposed.

## Measurement for the next implementation

Use a frozen sequential regression selection spanning short prose, bounded count, whole-document inventory, numeric presentation, multi-page relationships, material omission and source-audited missing evidence. Include 382/662, 642, 831, 1079, a concise-answer control and negative controls from the existing ledger. Reuse established source answers and acceptance criteria; no new gold-driven runtime rules.

Compare per-question total time, request count, reread occurrences, repeated source/version/page/operation signatures, semantic gaps resolved, rerank calls, input/output tokens and final source correctness. Report cohort median and tail, plus failures, without treating timeout reduction or earlier abstention as success. Timing variation needs repeated frozen measurements before claiming causal savings.

Additional spans should expose first-time source exposure, reused accepted extraction, unchanged review reused, obligation opened/resolved, and prepare-to-release time. Existing IDs/counters are sufficient; do not include raw document text in spans. No API price estimate is possible while model pricing is unconfigured.

## Audited recent attempt manifest

All 76 recent attempts below are included, including intermediate failures. “Published” means validation passed and the result is not an abstention; it is not a fresh correctness label. Paths identify ignored local raw artifacts. Source reports retain interpretation of correctness and failures.

| Row | Seconds | Calls | Terminal observation | Local run directory |
| --- | ---: | ---: | --- | --- |
| 207 | 67.18 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row207` |
| 209 | 127.88 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row209` |
| 222 | 62.38 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row222` |
| 223 | 69.15 | 8 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row223` |
| 365 | 68.79 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row365` |
| 367 | 73.96 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row367` |
| 380 | 50.11 | 6 | Published | `adaptive-source-dispositions-20261021/live-four/row380` |
| 380 | 48.74 | 6 | Published | `adaptive-source-dispositions-20261021/follow-up/live-four/row380` |
| 380 | 52.32 | 6 | Published | `adaptive-source-dispositions-20261021/outcome-handoff/live-four/row380` |
| 380 | 57.19 | 9 | Abstention | `adaptive-source-dispositions-20261021/terminal-finalization/live-two/row380` |
| 380 | 51.86 | 6 | Published | `adaptive-source-dispositions-20261021/answer-local-validation/live-three/row380` |
| 382 | 60.87 | 5 | Published | `adaptive-material-coverage-20261021/row382` |
| 382 | 63.37 | 5 | Published | `adaptive-material-coverage-20261021/inventory-followup/row382` |
| 382 | 68.71 | 5 | Published | `adaptive-inventory-progress-20261021/row382` |
| 382 | 65.42 | 5 | Published | `adaptive-inventory-progress-20261021/planned-windows/row382` |
| 382 | 110.06 | 8 | Published | `adaptive-inventory-progress-20261021/visible-answer/row382` |
| 383 | 28.08 | 3 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row383` |
| 387 | 29.31 | 3 | Published | `adaptive-source-dispositions-20261021/answer-local-validation/live-three/row387` |
| 387 | 29.84 | 3 | Published | `adaptive-material-coverage-20261021/row387` |
| 387 | 35.99 | 3 | Published | `adaptive-material-coverage-20261021/inventory-followup/row387` |
| 387 | 31.40 | 3 | Published | `adaptive-material-coverage-20261021/sparse-followup/row387` |
| 387 | 34.27 | 3 | Published | `adaptive-numeric-presentation-20261021/row387` |
| 507 | 21.23 | 3 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row507` |
| 507 | 23.41 | 5 | Published | `adaptive-checked-visual-scope-20261021/runs/row507` |
| 508 | 49.38 | 4 | Abstention | `adaptive-source-dispositions-20261021/follow-up/live-four/row508` |
| 508 | 126.96 | 9 | Abstention | `adaptive-source-dispositions-20261021/outcome-handoff/live-four/row508` |
| 508 | 46.39 | 6 | Abstention | `adaptive-source-dispositions-20261021/terminal-finalization/live-two/row508` |
| 508 | 51.10 | 7 | Abstention | `adaptive-source-dispositions-20261021/answer-local-validation/live-three/row508` |
| 508 | 46.17 | 6 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row508` |
| 519 | 23.82 | 3 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row519` |
| 519 | 34.06 | 3 | Published | `adaptive-material-coverage-20261021/row519` |
| 519 | 38.51 | 3 | Published | `adaptive-material-coverage-20261021/inventory-followup/row519` |
| 520 | 53.95 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row520` |
| 521 | 71.76 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row521` |
| 634 | 84.02 | 9 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row634` |
| 634 | 71.78 | 9 | Published | `adaptive-visual-conditions-20261021/row634` |
| 634 | 90.12 | 7 | Published | `adaptive-visual-conditions-20261021/fact-handoff/row634` |
| 634 | 64.96 | 7 | Published | `adaptive-numeric-presentation-20261021/row634` |
| 635 | 64.65 | 9 | Failed/other | `adaptive-visual-conditions-20261021/row635` |
| 635 | 51.73 | 9 | Abstention | `adaptive-visual-conditions-20261021/fact-handoff/row635` |
| 637 | 54.17 | 5 | Published | `adaptive-visual-conditions-20261021/row637` |
| 638 | 87.76 | 9 | Abstention | `adaptive-visual-conditions-20261021/row638` |
| 642 | 189.59 | 9 | Abstention | `adaptive-material-coverage-20261021/row642` |
| 642 | 130.17 | 9 | Abstention | `adaptive-numeric-presentation-20261021/row642` |
| 642 | 94.04 | 6 | Published | `adaptive-numeric-presentation-20261021/display-receipt/row642` |
| 659 | 35.27 | 3 | Published | `adaptive-visual-conditions-20261021/row659` |
| 660 | 108.71 | 9 | Abstention | `adaptive-visual-conditions-20261021/row660` |
| 662 | 201.83 | 9 | Abstention | `adaptive-inventory-progress-20261021/row662` |
| 662 | 127.60 | 9 | Abstention | `adaptive-inventory-progress-20261021/planned-windows/row662` |
| 662 | 74.13 | 5 | Abstention | `adaptive-inventory-progress-20261021/narrow-windows/row662` |
| 662 | 148.52 | 9 | Abstention | `adaptive-inventory-progress-20261021/verified-windows/row662` |
| 662 | 104.89 | 6 | Published | `adaptive-inventory-progress-20261021/visible-answer/row662` |
| 727 | 104.61 | 10 | Abstention | `adaptive-source-dispositions-20261021/normal-ten/runs/row727` |
| 727 | 42.16 | 6 | Published | `adaptive-checked-visual-scope-20261021/runs/row727` |
| 728 | 121.62 | 9 | Abstention | `adaptive-source-dispositions-20261021/live-four/row728` |
| 728 | 99.37 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row728` |
| 728 | 66.76 | 9 | Abstention | `adaptive-checked-visual-scope-20261021/runs/row728` |
| 729 | 39.01 | 6 | Published | `adaptive-checked-visual-scope-20261021/runs/row729` |
| 730 | 31.54 | 6 | Abstention | `adaptive-source-dispositions-20261021/live-four/row730` |
| 730 | 65.17 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row730` |
| 830 | 61.91 | 9 | Abstention | `adaptive-source-dispositions-20261021/follow-up/live-four/row830` |
| 830 | 26.96 | 4 | Failed/other | `adaptive-source-dispositions-20261021/outcome-handoff/live-four/row830` |
| 831 | 43.83 | 3 | Published | `adaptive-material-coverage-20261021/row831` |
| 831 | 251.75 | 9 | Abstention | `adaptive-material-coverage-20261021/inventory-followup/row831` |
| 831 | 72.47 | 5 | Published | `adaptive-material-coverage-20261021/sparse-followup/row831` |
| 832 | 21.93 | 3 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row832` |
| 1017 | 95.66 | 9 | Abstention | `adaptive-source-dispositions-20261021/live-four/row1017` |
| 1017 | 119.52 | 10 | Abstention | `adaptive-source-dispositions-20261021/follow-up/live-four/row1017` |
| 1017 | 135.77 | 9 | Abstention | `adaptive-source-dispositions-20261021/outcome-handoff/live-four/row1017` |
| 1024 | 41.16 | 7 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row1024` |
| 1076 | 25.55 | 3 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row1076` |
| 1076 | 26.84 | 3 | Published | `adaptive-numeric-presentation-20261021/display-receipt/row1076` |
| 1079 | 94.47 | 10 | Published | `adaptive-source-dispositions-20261021/normal-ten/runs/row1079` |
| 1079 | 55.43 | 8 | Published | `adaptive-checked-visual-scope-20261021/runs/row1079` |
| 1079 | 47.34 | 6 | Published | `adaptive-numeric-presentation-20261021/row1079` |
| 1084 | 81.97 | 9 | Abstention | `adaptive-source-dispositions-20261021/negative-eleven/runs/row1084` |
