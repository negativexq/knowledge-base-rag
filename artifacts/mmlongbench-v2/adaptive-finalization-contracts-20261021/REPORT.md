# Finalization contracts: preserving grounded answers and typed repair

21 October 2026. Follow-up to the [frozen 20-question baseline](../adaptive-fixed-latency-baseline-20261021/REPORT.md). Five answerable failures and six controls were selected before running and measured once each, sequentially, under frozen application/trace-harness hashes. All hashes still match after completion.

## Result

**11/11 expected source outcomes: nine correct answers and two correct safe refusals.** All five baseline failures now publish the source-correct answer. Four answerable controls remain correct; two source-audited negatives remain safely unanswered. Runtime validation is not the correctness criterion. Results were compared with the previously source-audited [question ledger](../../../docs/adaptive-solved-questions.md), including the complete activity groups in 831 and the corrected source values for 642. No new paid after-run judge was used.

These are reruns of existing questions. Historical coverage remains **101/120 (84.2%)**, including qualified calculations; no distinct question or historical success was added. This does not establish 11-question results for the other nine baseline rows or prove full-suite benchmark stability.

## Corrections

### Ground source restrictions without a capitalization heuristic

`scope_requirements.py` no longer infers entity identities from every capitalized question word and demands those exact tokens in the selected witness lines. That made `EPS Code AR01` require the literal words `EPS` and `Code` alongside an already established `Little Rock | AR01` relationship; an income-population question also treated `Among` and `Higher` as required names.

The existing independent scope call still must return a supported binding for every question-grounded restriction, using valid claim-bound original-source line or image witnesses. Unknown/mismatch/unestablished verdicts, missing or foreign witnesses, wrong image bindings and incomplete requirement coverage remain blocking. Generated calculation/transcription proof alone cannot establish entity/population identity, including when a proposed binding is labeled linguistic equivalence. Meaning and relationships are checked semantically against original evidence; capitalization is not an identity test. There is no alias dictionary, benchmark answer injection, new judge or collection-specific exception.

This deliberately removes an unreliable deterministic token test; it does not make semantic judgments infallible. Genuine company/year/population mismatch still depends on a grounded negative semantic finding, not mere token absence. The negative controls below test two such source limitations, not every possible mismatch.

### Keep an executed answer visible to final coverage

`quantity_scope.py` retains the exact application's answer text for arithmetic, as already done for count results. Before this correction, an exact accepted result such as 41 Tweets or 11,407 million was replaced by a generic computed-result sentence. Material coverage then reasonably reported the numeric total as absent, and repeated checks/answer append could not fix the hidden projection.

Calculation proof fields remain separate from source evidence. Only an exact application candidate whose values, expression, units/conversion and completion state are rechecked locally receives the verified-operation view. Model-edited claims, changed formulas/units, stale/pending results and ordinary prose retain normal validation. The original unmodified answer payload remains the release fingerprint. Source entity, period, inputs and formula relevance still need positive independent checking. No final coverage check is bypassed.

### Repair a localized image operand using its existing source

`quantities.py` reuses the parent's authorized source selection for a source-correction repair only when the parent is image-based, has known pages, and every grounded objection targets an operand on those same pages. This avoids a speculative selector after the checker has already located the wrong cell. The existing bounded repair contract owns the formula, operand names, output convention and unaffected inputs; the collector corrects source readings and the complete merged result is reviewed again. Other repair types and unknown/outside-page locations retain source selection.

The `quantity.repair.route` span now records `quantity.reuses_source_selection`. Existing parent/child records, target indexes, contracts and reviews retain where the failed and corrected values came from. No global budget or allowed tool scope was increased.

## Paired results

The comparison below uses only the same eleven rows from the prior frozen baseline. The broader 20-row baseline's timing distribution is not compared to this smaller group. One attempt per row per implementation; provider variation and source-route variation remain. Observed changes are not a universal or isolated causal speedup estimate.

| Row | Baseline result | Baseline s / calls | Follow-up result | Follow-up s / calls |
| --- | --- | ---: | --- | ---: |
| 507 | Answerable abstention | 38.95 / 9 | Little Rock | 22.64 / 3 |
| 223 | Answerable abstention | 78.37 / 10 | 90%, 42%, 39% | 48.47 / 5 |
| 729 | Answerable abstention | 71.23 / 9 | 41 Tweets | 39.27 / 6 |
| 1017 | Answerable abstention | 115.14 / 10 | 11,407 million | 114.99 / 9 |
| 380 | Answerable abstention | 60.17 / 9 | 8,367,277,000 rupees | 46.40 / 6 |
| 387 | Correct answer | 28.06 / 3 | Rick Scott | 24.53 / 3 |
| 642 | Correct answer | 47.26 / 5 | 64.4, 62.5, 62.2 | 57.84 / 5 |
| 662 | Correct answer | 79.63 / 6 | 9 figures; pages 11, 12, 13, 16, 18, 20 | 80.07 / 6 |
| 831 | Correct answer | 41.50 / 5 | Interview/team, supplier comparison, local-business resources/supply chain, product selection | 76.04 / 6 |
| 365 | Correct safe refusal | 57.72 / 8 | Correct safe refusal | 54.10 / 7 |
| 728 | Correct safe refusal | 92.06 / 9 | Correct safe refusal | 87.73 / 9 |

| Paired 11-row metric | Baseline | Follow-up |
| --- | ---: | ---: |
| Expected source outcomes | 6/11 | 11/11 |
| Total model requests | 83 | 65 |
| Median in-run seconds | 60.17 | 54.10 |
| p90 in-run seconds | 92.06 | 87.73 |
| p95 in-run seconds | 115.14 | 114.99 |
| Summed in-run seconds | 710.09 | 652.08 |
| Scope calls | 17 | 10 |

Nearest-rank p90/p95 use `ceil(p*n)`; median averages the middle pair when needed. All failures and negative outcomes are retained. In-run time includes initial retrieval through terminal output, excluding child setup/shutdown. At n=11, p95 is the maximum. **The tail is essentially unchanged**, dominated by 1017's multi-source acquisition. Model requests fall by 18 (21.7%), while summed in-run time falls by 8.2%; neither is a guarantee for other workloads.

## What the traces establish

- **507 and 223:** each now has one scope call instead of four/three. The saved earlier positive judgments were also replayed offline through current line and requirement validation, requiring zero new model calls. This isolates removal of the lexical rejection at that saved boundary; live end-to-end runs supply separate current results.
- **729:** correct 41-Tweet execution reaches one final scope call; there is no answer-repair call. Previous outcome had three scope calls and one repair. The source acquisition path varies between runs, so the full timing difference cannot be assigned solely to projection.
- **1017:** still needs two selector/collector/checker passes. The final accepted calculation uses 799 + 6692 + 3916 and is published with one scope call. Acquisition remains expensive; the finalization failure is recovered without claiming a large speedup.
- **380:** current live run reads the correct subtotal immediately and publishes six-call arithmetic. It does **not** exercise localized repair. That new branch is verified by an offline original-PDF integration test with a deliberately wrong operand: one source selection, two collection/check passes, unchanged valid input retained, corrected total executed. The prior failed value remains in the parent record.
- **387/642/662:** prose stays at three calls; numeric presentation stays at five with no speculative answerer; nine-figure inventory stays at six with different extractor windows retained.
- **831:** genuine missing activity groups are appended and checked, retaining the supported interview/team content. It takes six calls this time rather than five; material-omission checking remains active.
- **365/728:** missing/wrong-entity source data does not become an invented positive value. Both return safe insufficiency. Rich source explanations and efficient closure remain separate open capabilities.

## Verification and limits

**2,471 tests passed**, four skipped, five deselected. Ruff (`app tests scripts`), mypy (166 app files) and `git diff --check` pass. Regression coverage includes exact result visibility with immutable original payload, changed-result/formula/unit rejection, positive semantic requirements with nonliteral wording, unresolved/mismatch rejection, generated-only identity rejection, image/source binding failures, and localized operand repair with preserved valid input and application-owned operation.

All paid runs use the unchanged gpt-6-luna fast-path/evidence-needs profile, role efforts, ten main requests, 120,000 tokens, 240 application seconds and 60-second model/tool timeouts. Child ceiling is 360 seconds. Embedding, reranking, retrieval and model choice are unchanged. Dollar API cost is unknown because pricing is unconfigured; token/call usage is recorded locally. No application/harness changes occurred during the eleven-question batch.

Remaining priorities: incremental acquisition/review for multi-page numerical tasks such as 1017; reuse of unchanged successful judgments under exact dependencies; safe, efficient negative closure; repeated measurements of tail latency. These results close the targeted execution failures, not every historical unresolved question or every semantic-model failure.

Raw results, spans, forensic captures, selection, source hashes and process logs remain local and ignored. Only this English report and documentation are intended as tracked measurement artifacts.
