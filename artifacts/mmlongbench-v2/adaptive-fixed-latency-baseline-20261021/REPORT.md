# Frozen mixed-question latency and correctness baseline

21 October 2026. Twenty existing, previously source-audited questions were selected before execution and run once each, sequentially. Application and trace-harness SHA-256 hashes were checked before and after every question and again after the batch. No application changes or paid after-run judge were used during this measurement.

## Outcome

**15/20 expected source outcomes (75%): 13 correct answers and two correct safe refusals. Five answerable questions abstained.** Answerable-question success is 13/18 (72.2%); audited-negative success is 2/2. No wrong substantive final answer was observed in this sample. Runtime validation passing is not counted as answer correctness: it also passes on the five unwanted abstentions.

This is a fixed current-code baseline, not a randomized old/new comparison, and not a new score for all 120 questions. Each question was run once; the tail estimates are exploratory. Existing historical README coverage remains unchanged. All cases were already in the ledger, so distinct-question coverage does not increase.

Selection: five prose/lookups (387, 519, 507, 1076, 478); five numerical tasks (1079, 380, 1024, 642, 223); five counts or multi-source tasks (382, 477, 729, 831, 1017); three visual tasks (634, 727, 662); two audited negatives (365, 728). Categories describe the selected tasks, not a forced runtime route.

## Measurement contract

Existing source-document-scoped `run_adaptive_trace.py --fast-path --evidence-needs`, gpt-6-luna, unchanged role efforts, 10 main requests, 120,000 tokens, 240 application seconds, 60-second model/tool timeout and 60-second finalization reserve. The child-process ceiling is 360 seconds. Existing Qwen embedding and BGE reranking were retained. Reference answers were used only for this post-run review, never supplied to generation.

Correctness was compared with the previously audited source results in [the question ledger](../../../docs/adaptive-solved-questions.md), including activity coverage for 831. No fresh independent source-image judge was run. Row 642 is checked against its original-source audit (64.4, 62.5, 62.2), not the known incorrect benchmark label.

In-run time starts before initial retrieval and ends at terminal output. Child-process time additionally includes setup and shutdown; it is not the response time of a persistent service. Percentiles use nearest rank, `ceil(p*n)` in ascending order; median is the average of the middle pair. Every result, including failures and negatives, is retained. Model-span time is summed only over `llm.request`; overlapping parent/search/rerank spans are not added.

| Metric | Observed |
| --- | ---: |
| In-run median | 47.55 s |
| In-run p90 | 79.63 s |
| In-run p95 | 92.06 s |
| In-run maximum | 115.14 s |
| Process median | 60.93 s |
| Process p90 | 93.21 s |
| Process p95 | 105.78 s |
| Total main model requests | 128 |
| Median requests | 6.0 |
| Input tokens | 720773 |
| Output tokens | 70645 |
| Cached input tokens (subset of input) | 115946 |
| Model span time / summed in-run time | 79.6% |

Pricing is unconfigured (`cost_usd=null`); dollar API cost is unknown, not zero. All 20 child processes exited successfully; application-level failures remain failures. No timed-out child processes were dropped.

## Per-question outcomes

| Row | Source outcome | In-run s | Requests | Observation |
| --- | --- | ---: | ---: | --- |
| 387 | Correct answer | 28.06 | 3 | Rick Scott |
| 519 | Correct answer | 28.27 | 3 | eMarketer |
| 507 | Failed: answerable abstention | 38.95 | 9 | Little Rock candidate blocked by named-entity lexical gate |
| 1076 | Correct answer | 22.37 | 3 | USD 1,874 million |
| 478 | Correct answer | 19.14 | 3 | 88: boiler over-temperature; 188: heater error |
| 1079 | Correct answer | 48.46 | 7 | 0.627 |
| 380 | Failed: answerable abstention | 60.17 | 9 | Wrong subtotal caught; source-correction/finalization did not recover |
| 1024 | Correct answer | 44.56 | 6 | 0.304 |
| 642 | Correct answer | 47.26 | 5 | 64.4, 62.5, 62.2; source-correct, benchmark label differs |
| 223 | Failed: answerable abstention | 78.37 | 10 | Correct 90%, 42%, 39% draft blocked by lexical gate |
| 382 | Correct answer | 47.83 | 5 | 2 quizzes |
| 477 | Correct answer | 44.98 | 5 | 7 levels |
| 729 | Failed: answerable abstention | 71.23 | 9 | Accepted 41-tweet calculation lost at final scope |
| 831 | Correct answer | 41.50 | 5 | Interview/team plus supplier, local-business/supply-chain and product tasks |
| 1017 | Failed: answerable abstention | 115.14 | 10 | Accepted 11,407 million calculation lost at final scope |
| 634 | Correct answer | 56.27 | 7 | Fact Checker |
| 727 | Correct answer | 42.54 | 6 | 12 Tweets |
| 662 | Correct answer | 79.63 | 6 | 9 figures; pages 11, 12, 13, 16, 18, 20 |
| 365 | Correct safe refusal | 57.72 | 8 | Safe insufficiency; requested company differs from document |
| 728 | Correct safe refusal | 92.06 | 9 | Safe insufficiency; Boeing operand missing |

## Model time by role

| Role | Calls | Total s | Share of model time | Median s/call |
| --- | ---: | ---: | ---: | ---: |
| `scope_validator` | 26 | 280.07 | 33.0% | 9.63 |
| `quantity_checker` | 13 | 124.54 | 14.7% | 7.40 |
| `need_planner` | 20 | 102.85 | 12.1% | 5.12 |
| `quantity_selector` | 13 | 91.58 | 10.8% | 6.20 |
| `quantity_collector` | 11 | 91.02 | 10.7% | 8.29 |
| `answerer` | 15 | 56.83 | 6.7% | 2.89 |
| `reader` | 17 | 56.33 | 6.6% | 2.83 |
| `finalizer` | 5 | 13.79 | 1.6% | 2.21 |
| `extractor` | 3 | 11.89 | 1.4% | 3.94 |
| `source_selector` | 2 | 7.47 | 0.9% | 3.74 |
| `answer_repair` | 2 | 6.02 | 0.7% | 3.01 |
| `scoped_extraction_checker` | 1 | 5.21 | 0.6% | 5.21 |

Final scope is the largest model-time component (33.0%). Quantity checking adds 14.7%; together they account for 47.7% of model time. This does not mean all checks can be removed. Row 380's checker prevents publication of a genuinely wrong subtotal; 1017 initially needs additional lease disclosure.

Four of five answerable failures have multiple scope calls: 507 (4), 223 (3), 729 (3), 1017 (2). The other repeated-scope question, 831 (2), succeeds after adding genuinely missing activities. Repeated roles therefore require inspection of their actual obligations. Likewise, 662's two extractor calls process different page windows and are useful, not duplicate work.

## Loss audit

1. **Deterministic lexical requirement rejection: 507 and 223.** The source contains `Little Rock | AR01`, and the candidate and semantic scope judgments support Little Rock. All four checks nevertheless fail `SCOPE_NAMED_ENTITY_RELATION_UNGROUNDED`. The guard in `scope_requirements.py` treats capitalized words from the question quote as names and demands each in the selected witness text. For `EPS Code AR01` it includes `EPS` and `Code`; 223 also includes ordinary `Among` and `Higher`, plus survey-name/date words spread across different source lines. In 223 the final candidate already contains 90%, 42%, 39%, but three checks hit this guard. These are evidence-binding/lexical-gate failures, not evidence that the model lacks the correct values. Repeating the same semantic judgment cannot by itself fix an application-side gate.
2. **Computed answer hidden at the scope boundary: 729 and 1017.** The calculation records contain the correct accepted results, 41 Tweets and USD 11,407 million. Scope subsequently reports a missing numeric total, describing the answer as only referring to a computed result. The saved typed answer parts already contain those numbers. 729 even appends “The total is 41 Tweets,” then receives the same omission. This demonstrates a representation/handoff problem to investigate in semantic projection; it does not justify disabling material-omission checks. In 1017 the first missing-lease-disclosure objection is valid, and the second acquisition legitimately adds six supported operands; the final two omission checks are where publication is lost.
3. **Wrong input caught but repair not completed: 380.** Collection binds shareholders' funds to 29,274.75 (the overall balance-sheet total) rather than the 25,966.14 subtotal. Both checker calls correctly identify the mistake and preserve the valid income operand. Source correction fails at `quantity.repair.inputs`; a later selector emits a document-count plan for an arithmetic task. Reader/finalizer drafts recover the correct arithmetic, but no authorized final answer is released before the request reserve. This is a typed repair-contract/finalization gap, not a reason to accept the wrong input or increase global budgets.

The five failures published safe insufficiency rather than fabricated values, but they remain correctness losses. The same terminal text is acceptable only for the two separately source-audited negatives.

## Fast-path checks and next optimization

- Four successful short lookups (387, 519, 1076, 478) use need planner → answerer → scope, three calls each. Fast path skips research, not planning. The fifth short lookup exposes the lexical gate above.
- 642 dispatches directly from the typed numeric-presentation need to selector → collector → checker → scope: five calls including planning, 47.26 seconds. No speculative answerer call occurs. This verifies dispatch in this execution, not a universal speedup.
- 382 and 477 each finish in five calls. 662 returns all nine figures and the unique page list in six calls, 79.63 seconds. Its first coverage review closes successfully; this run does not exercise the missing-page continuation branch.
- 831 retains the supported interview/team content and adds the three missing activity groups in five calls. Its extra scope check has a real purpose and must be preserved.

Prioritize the **finalization contract and requirement authority**, then reuse of checks. Show a verified application's exact result, unit and requested presentation to coverage checking while preserving original-source input authority. Replace raw capitalized-word matching with validated entity/relationship obligations, without weakening real company/year/population mismatch rejection. Keep accepted operands during typed source correction, and make repair schemas match arithmetic tasks. After these correctness gaps are fixed, reuse unchanged judgments only under matching question constraints, source version, operation and claim; verify only new obligations/deltas. Blanket memoization of failed checks would reproduce the current failures faster.

Retest the five failures plus representative currently passing text, arithmetic, visual and negative controls under the same freeze. A paired fixed-cohort before/after is needed before claiming reduced calls or p90/p95. The broader baseline shows that isolated 642/662 successes do not establish that the full architecture is already stable.

## Artifacts and repository impact

`selection.json`, `source-freeze.json`, `progress.json`, `analysis.json`, per-row `result.jsonl`, `spans.json`, captures and logs remain local and ignored. This English report is the shareable artifact. No application source, prompt, model effort, retrieval setting or test was changed for this measurement. No tests were rerun for this read-only batch. No new distinct benchmark questions or historical README successes were added.
