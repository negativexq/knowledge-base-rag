# Complete 120-row adaptive audit

Updated 20 October 2026. Every row in the pre-existing 120-row / 13-PDF manifest
has an adaptive result. There were no additional questions or paid reruns in this
completion step. All runs use the question's source-document scope, not open-corpus
document discovery. The [question ledger](../../../docs/adaptive-solved-questions.md)
keeps one entry per manifest row and preserves links to failed attempts.

## Shared automatic comparison

The same current repository `answer_matches` and `response_kind` functions were
applied offline to the earlier `luna-full-v3/results.jsonl` archive and the latest
saved adaptive result for each manifest row. V2 corrected questions/labels and
answer formats were used for both. No new model calls were needed. Answerable
rows require a released matching answer; unanswerable rows require abstention.
This deterministic matcher is lenient and is not the official benchmark judge.

| Measure | Earlier pipeline | Adaptive latest saved answers |
| --- | ---: | ---: |
| Overall shared match | 79/120 (65.8%) | 84/120 (70.0%) |
| Answerable match | 60/99 | 67/99 |
| Unanswerable label-compatible refusal | 19/21 | 17/21 |
| Published answers | 72 | 81 |

Paired score changes: 16 gains, 11 losses, 93 unchanged. Gains are rows 210, 212,
371, 385, 386, 388, 396, 513, 515, 516, 519, 524, 639, 642, 727 and 729. Losses
are 206, 216, 366, 510, 511, 635, 638, 658, 663, 1016 and 1070. These are matcher
outcomes, not independent proof of every reference label or source interpretation.

Selection is the result file with the latest filesystem modification timestamp
per row, across local `adaptive-*` run directories. All selected paths and scores
are retained in the ignored thirty-row `comparison.json`. This gives a complete
archive comparison; it is not a new single-pass execution of all 120 questions.

## Frozen current-runtime cohort: 55 new rows

The [ten](../adaptive-unseen-ten-next-20261019/REPORT.md),
[fifteen](../adaptive-unseen-fifteen-20261019/REPORT.md) and
[remaining thirty](../adaptive-remaining-thirty-20261020/REPORT.md) use identical
application and harness hashes, settings and budgets. There were no code changes
between these batches. Compare the earlier archive on these exact same rows:

| Measure on the same 55 questions | Earlier pipeline | Current adaptive runtime |
| --- | ---: | ---: |
| Shared matcher | 34/55 (61.8%) | 25/55 (45.5%) |
| Answerable match | 20/40 | 13/40 |
| Unanswerable label-compatible refusal | 14/15 | 12/15 |
| Published answers on answerable rows | 24/40 | 19/40 |
| Main-pipeline elapsed time, sum | 759.00 s | 3,239.80 s |

There are zero matcher gains and nine losses in this cohort: 206, 216, 366, 510,
511, 638, 663, 1016 and 1070. This is a real observed weakness on these questions,
not something to dismiss by pointing at the aggregate 70%. The current path is
also about 4.27 times slower by summed main-pipeline time on this cohort. Different
pipeline settings, context sizes and tool/model roles prevent attributing this
entire difference to a single component. In particular, the earlier report used
candidate/top context sizes 40/14 while the adaptive trace uses 15/5, followed by
bounded tool research. This is a whole-pipeline comparison, not an isolated
retrieval or judge ablation. Timing is observational, not repeated controlled
latency measurement.

## Source and workflow audit

The historical ledger contains **70 source-supported published answers, four
verified correct refusals and 46 unresolved questions/workflows**, totaling 120.
Unresolved does not mean 46 wrong numeric answers: it includes incomplete
inspection, expected abstentions without verified terminal receipts, answerable
misses, ambiguous source/metric definitions and incorrectly accepted answers.
These categories are separate from automatic label matching and must not be
combined into one accuracy claim.

The 55-row cohort has 14 source-supported published answers, 41 open outcomes and
no newly certified clean refusals under this audit policy. The automatic matcher
also counts 12 label-compatible refusals as successful, explaining part of the
metric difference. Some source-supported answers differ from labels, while some
label-compatible outcomes still have workflow defects. Automatic review booleans
were overridden where original-page inspection exposed missed heading membership,
port range, bottom/top location or unsupported geographic inference.

## Engineering priorities

1. Preserve verified provenance, table headings, period columns and printed-page
   mappings with operands so independent review does not repeatedly discard them.
2. Make repair admissibility explicit before dispatch and retain precise guard
   errors. Correct extraction must survive unsuccessful repair and finalization.
3. Separate textual extraction, visual/spatial comparison, numeric read, inventory
   closure and arithmetic. Keep operators narrow while fixing dispatch coverage.
4. Accumulate inventory coverage across bounded windows, with explicit sibling
   heading membership and actual closure. Do not increase page budgets to hide
   incomplete evidence handling.
5. Distinguish mismatch/absence, partial inspection, unsupported result and error;
   terminate grounded source mismatches efficiently. Preserve assumptions and
   approximation for ambiguous metrics and survey headcounts.
6. Recheck a frozen control set after each architectural correction. Retain the
   earlier pipeline as a comparison; no claim is made that the current path has
   already replaced it successfully for every task.

No runtime fixes were applied during this audit. No extra paid benchmark rows or
reviewer retries were run. Raw results and spans remain local and ignored.

## Issue audit addendum

Issue audit addendum: the [code-and-trace audit](../../../docs/adaptive-issue-audit.md) now identifies concrete repair, mixed-locator, page-role and dispatch defects behind several observed losses. It also corrects prior unspecified error diagnoses using `ResearchState.needs`. No new paid run or scoring change is included.
