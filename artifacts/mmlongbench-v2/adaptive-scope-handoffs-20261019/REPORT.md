# Grounded scope handoffs and explicit arithmetic interpretations

## Outcome

**Five frozen rechecks: two source-correct published answers, one justified refusal, and two unanswered cases (3/5 successful task outcomes).** Row 221 is newly solved. Row 1020 now includes its percent unit and interpretation. Row 372 remains unresolved; row 385 encountered an operational model-call timeout. Neither unanswered case counts as a success.

| Row | Published output | Seconds | Main model calls | Tool attempts | App retries |
| --- | --- | ---: | ---: | ---: | ---: |
| 372 | I could not obtain enough evidence to answer this question. | 85.25 | 6 | 1 | 1 |
| 221 | 12.000 percentage points (Subtract the broadband-at-home percentage from the internet-use percentage for the specified male age group.) (calculation: 65 - 53 = 12.000) [E3.S1] [E1.S47] [E1.S75] [E1.S70] [E1.S98] | 44.07 | 6 | 1 | 0 |
| 1020 | 25.04 % (Long-term debt, including the specified long-term lease liabilities, as a percentage of total liabilities for FY2021.) (calculation: (6692 + 2642 + 980) / 41190 * 100 = 25.04) [E3.S1] [E1.S16] [E1.S47] | 48.70 | 6 | 1 | 0 |
| 385 | I could not obtain enough evidence to answer this question. | 101.66 | 6 | 2 | 0 |
| 220 | I could not obtain enough evidence to answer this question. | 72.04 | 5 | 1 | 1 |

## Source and trace findings

- **221 — solved:** Original physical pages 16 and 17 bind male age 65+ internet use to 65% and home broadband to 53%. Collection retained those exact populations and image handles, independent review passed, and application subtraction produced 12.000. The renderer published **12 percentage points**, with the absolute-difference interpretation and calculation. Six calls, one tool attempt, no retry. The reference images on benchmark pages 7–8 omit the male rows; source verification therefore relies on the actual demographic tables and saved original-image bindings, not the coincidentally equal all-senior gap.
- **1020 — source-correct and clearer:** Checked values 6692, 2642, 980, and 41190 yielded **25.04%**, now displayed with its unit and FY2021 definition. The model did not write the calculation result; the application did. Percentage and rounded ratio 0.25 are equivalent presentations at their respective precision. Exact string agreement is not the criterion.
- **220 — correct refusal:** The requested 2022 headcount remains unsupported by the older report's 2013 survey. The actual explicit period requirement was retained; relaxing invented requirements did not authorize a 2022 answer.
- **372 — review-repair bookkeeping still blocks research:** The collector again selected the three-member Audit Committee subset. The first checker returned an operand-target issue for a list and an internally contradictory assessment. One bounded diagnostic correction fixed the receipt and identified unknown company binding plus incomplete company-wide coverage, but consumed the sole repair slot. No source-repair attempt ran. This does not exercise the new final-scope handoff: failure occurs earlier, in input review. A review contract limited to actual operation slots, an independent source-repair slot within the existing hard ceiling, and whole-inventory replacement for unresolved binding plus missing coverage are the next bounded fixes. Verified-item union remains appropriate only when the existing input bindings are supported.
- **385 — operational timeout:** The quantity-selector call returned no model output before its **60-second** deadline. `tool.collect` started at 12:16:22.811 UTC and timed out at 12:17:22.836 UTC. Original-image extraction, the new per-image collection contract, and arithmetic were not reached in that collection attempt. Later extraction did not recover the layout answer. This trace cannot distinguish provider queueing, slow inference, or connection delay. It does not prove a schema rejection. The previous run's unavailable-source route was a separate observed failure, preserved in its own report. This previously solved control still needs a successful current recheck.

## Implementation in this revision

A valid grounded final-scope objection can start one bounded source-repair attempt. The parent receipt and objection stay in typed state, the operation is fixed, and replacement inputs plus final scope must pass again. A known scope-rejected whole-answer receipt is not repeatedly retried during finalization. Unsupported diagnostic references never grant source access or auto-approval.

Arithmetic extraction carries an explicit interpretation and result unit through review, application calculation, proof admission and rendering. Review evaluates the proposed, clearly labeled interpretation rather than requiring that no other interpretation be conceivable. Scope validation continues to enforce actual entity, population, period and unit requirements. Source availability now means a plausible authorized region can be inspected, not that parser text already exposes a visual answer.

The input checker reserves a final scope call: application-owned prepared results need no additional answer-writing call. Shared limits remain ten requests, 120,000 tokens, 240 seconds and six tool attempts, with the same research time reserve. No SDK retry, embedding, index, ingestion, retrieval or reranking change was made. Each row ran once, sequentially, with gpt-6-luna and unchanged role effort settings. Main runs saw no benchmark gold answer or reference pages. Runtime source hashes were frozen before calls and were unchanged during this batch; follow-up work used a separate worktree.

## Validation and usage

Offline validation before this batch: **2,135 backend tests passed**, four optional skips, five deselected; **205 adaptive tests passed**; Ruff and mypy were clean. The follow-up review-target and source-repair changes are not represented by the results above and require their own frozen recheck.

Main usage: **29 calls**, **351.72 seconds**, **100,831 input tokens**, **17,678 output tokens**, **6 tool attempts**, **2 application retries**. Separate review calls are excluded. Provider billing for a timed-out call may not be fully represented by received usage; model prices are unset, so a dollar total is unavailable.

There are still **30 distinct questions tried**; repeats add no distinct questions. Historical published source-correct answers increase to **27**, with one correct refusal and two never-successfully-answered rows, 372 and 661. Row 385 has a historical success and a current regression/operational failure. The older successes are not a claim of current-version stability. Raw JSON, captures, state, spans and reviews remain local and ignored; only this English summary is intended for Git.
