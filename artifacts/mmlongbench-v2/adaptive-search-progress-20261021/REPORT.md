# Cumulative search progress

Date: 21 October 2026. Branch: `fix/cumulative-search-progress`, based on main `5c25898`.

## Change

Search previously counted a change from the immediately previous selection as progress, even when the same evidence had already been shown earlier. Alternating known selections could reset the existing consecutive-no-progress limit and incur more reader/retrieval/reranking work.

The application now records fingerprints of the complete authorized evidence projections in typed `ResearchState.evidence_exposures`. Catalog previews do not count. Search still counts newly admitted source evidence and first exposure of existing, previously hidden evidence as progress. Returning to an unchanged, already exposed selection does not count. Source metadata, version and content are part of the fingerprint; no model-authored summary or semantic similarity heuristic is involved.

This change only measures search acquisition. Existing extraction and calculation progress remains separate. It does not certify absence, invalidate supported findings, change source scope or lower answer-release checks. After the existing no-progress limit, finalization still has its reserved budget and access to retained evidence, computations and prepared results.

No prompt, role effort, retrieval/reranker setting, global budget or completeness criterion changes. This is the first measured optimization from the [latency audit](../../../docs/adaptive-latency-audit.md), not implementation of all recommendations.

## Observability

`evidence.search.focus` adds `evidence.newly_exposed_support_ids`, `research.progressed` and `research.progress_policy=cumulative_evidence_exposure_v1`. Successful `SearchEvidence` receipts retain the newly exposed IDs. Fingerprint state survives JSON roundtrip. Spans contain IDs and counters, not source text.

## Verification

Full suite: **2,438 passed, four skipped, five deselected** (47.90 seconds). Ruff and mypy pass. Added offline tests cover A/B/A search churn across checkpoint restore, first exposure of hidden admitted evidence, and independent finalization after acquisition stops, both for a supported answer with scope validation and an abstention. Existing identical-chunk reuse, authorization and search-evidence retention tests pass.

## Sequential live measurement

Six existing questions are selected before execution: 1079 (search-heavy numeric answer), 365 (source-audited negative), 387 (short prose), 382 (bounded count), 642 (numeric presentation), 662 (whole-document visual count). They run sequentially with `--fast-path --evidence-needs`, unchanged role efforts and ten-request / 120,000-token / 240-second limits. No paid after-run judge. All application and harness hashes are frozen during the batch. Raw results, source hashes, spans and captures remain local/ignored.

The comparison uses each question's latest saved attempt before this change, rather than selecting its slowest historical run. Those attempts are historical observations, not simultaneous paired baselines. A six-question development check can detect regressions and repeated-work changes; it cannot establish production p90/p95 improvement. Validation passing alone is not independent source correctness.

The frozen batch is complete. All six expected outcomes are retained: five answers agree with their previously source-audited results, and the source-audited negative safely abstains. Runtime validation passes for all six. There is no new independent paid judge and no additional source-answer discovery. Historical coverage remains **101/120 (84.2%)**, with 19 unresolved questions; these are reruns, not new questions.

| Row | Expected outcome retained | Previous seconds / calls | New seconds / calls |
| --- | --- | --- | --- |

| 1079 | 0.627 = 9912 / 15803 | 47.34 / 6 | 44.64 / 6 |
| 365 | Safe insufficient-evidence outcome; no invented value | 68.79 / 9 | 65.64 / 9 |
| 387 | Rick Scott | 34.27 / 3 | 25.46 / 3 |
| 382 | 2 quizzes | 110.06 / 8 | 45.82 / 6 |
| 642 | [64.4, 62.5, 62.2] | 94.04 / 6 | 80.46 / 6 |
| 662 | 9 figures; pages ["11", "12", "13", "16", "18", "20"] | 104.89 / 6 | 73.84 / 6 |

## What this measurement does and does not show

The six runs use 36 model requests versus 38 in the saved baselines. Observed median latency is 55.73 versus 81.42 seconds; the slowest observed run is 80.46 versus 110.06 seconds. These are descriptive observations, **not measured causal savings from this patch** and not a p90/p95 estimate. The largest path reduction is in 382, which selected all required pages immediately this time and avoided a second collection cycle. That route does not use the modified generic search-progress logic. 662 also keeps the same six-call route; its lower time mainly reflects different model-call durations.

In 365, six searches still consume nine total model requests. First exposures of existing evidence continue to count as real acquisition progress. The final two searches introduce no new exposure and correctly stop research at `NO_RESEARCH_PROGRESS`, with finalization returning the safe negative. The saved baseline also uses nine calls. The patch fixes the progress invariant, but **this live sample does not establish a reduction in calls attributable to it**. Offline tests directly demonstrate that repeated A/B/A exposure no longer resets progress and that both positive finalization and abstention remain available.

1079 publishes the existing checked arithmetic after a repeated-operation stop. The finalizer reuses the prepared result; acquisition stopping is not interpreted as source absence. Its six-call count is unchanged.

No runtime edits or harness changes occurred during the batch. API dollar cost remains unavailable because model prices are unconfigured.

## Fast-path audit from the same six runs

With `evidence_needs_enabled`, `NeedWorkflow.prepare()` runs before `research.fast_answer`. An existing ready need plan can be reused, but a fresh request normally pays one need-planner call. The current fast path skips the open research/extraction loop when a direct source-supported answer succeeds; it does not skip question planning or final scope validation.

- **387:** planner 4.60 seconds, direct answer 2.01 seconds, scope 6.23 seconds; 25.46 seconds total including retrieval/application work. Three requests, zero tools.
- **642:** planner 8.10 seconds, unsuccessful direct-answer attempt **31.12 seconds**, then selector/collector/checker/scope. Six requests, 80.46 seconds total. This is an expensive speculative fast attempt before the needed tool path.
- **662:** planned count dispatch skips direct-answer speculation and goes straight to inventory collection; six calls retain the correct result.
- **382:** this time the planner/fast-answer handoff leads to one complete count collection. The previous count run used a different plan and needed another collection cycle. Do not attribute this variation to search-progress tracking.

The next optimization to investigate is **whether a prepared evidence need can dispatch a necessary tool directly without a failed answer attempt**. A numeric or visual question alone must not force heavy collection when existing text already suffices. Keep final semantic scope and independent input/coverage checks. A planner-free short-answer route is a separate experiment; removing the planner globally would change constraint binding and visual/count dispatch and is outside this patch.

## Remaining work

- Measure cumulative-progress behavior on repeated frozen search-heavy cases before claiming latency savings.
- Make missing-boundary/page completion reuse accepted observations rather than retranscribing them.
- Avoid duplicate semantic work under unchanged evidence/claim/operation dependencies.
- Evaluate speculative answer dispatch and planner overhead on a mixed regression set.
- Establish tail latency on a larger frozen sample with repeated runs; do not optimize by earlier unsupported refusal.

## Saved baseline directories

- 1079: `artifacts/mmlongbench-v2/adaptive-numeric-presentation-20261021/row1079`
- 365: `artifacts/mmlongbench-v2/adaptive-source-dispositions-20261021/negative-eleven/runs/row365`
- 387: `artifacts/mmlongbench-v2/adaptive-numeric-presentation-20261021/row387`
- 382: `artifacts/mmlongbench-v2/adaptive-inventory-progress-20261021/visible-answer/row382`
- 642: `artifacts/mmlongbench-v2/adaptive-numeric-presentation-20261021/display-receipt/row642`
- 662: `artifacts/mmlongbench-v2/adaptive-inventory-progress-20261021/visible-answer/row662`
