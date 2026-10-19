# Five mixed questions: unchanged agentic workflow

## Result

**3/5 questions received a correct, source-supported published answer. Two abstained despite answerable source evidence.** No runtime code, prompts, retrieval settings, embeddings, or model budgets were changed during this measurement. No failed question was substituted or rerun.

The five previously untried rows were frozen before execution: narrative accounting policy (1077), table filtering (370), cross-page comparison (524), color-coded diagram interpretation (634), and a financial ratio across pages (1024). All ran sequentially with `gpt-6-luna`, fast path and evidence needs enabled, on main revision `37988df87062822aa4f92c9d1ab4499ad22f3b4f`. The existing diagnostic harness scoped retrieval to each question's source document. Main generation received neither benchmark answers nor reference pages; separate review followed each completed run.

| Row | Outcome | Published response | Seconds | Model calls | Tool attempts | Retries |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1077 | Correct answer | Best Buy records merchandise inventories at the lower of cost or net realizable value. It determines cost using the weighted-average method, including inbound freight to distribution centers and certain vendor allowances. Storage and transportation costs to retail stores are expensed as incurred; markdowns and physical inventory losses are also reflected in inventory valuation. (E2.S1) [E2.S1] | 25.71 | 3 | 0 | 0 |
| 370 | Correct answer | Mr. S.V. Shanbhag was the only executive director who attended more than six Board Meetings, attending 7. The other listed executive directors attended 6 or fewer. [E2.S1] | 21.93 | 3 | 0 | 0 |
| 524 | Abstained; failed to answer | I could not obtain enough evidence to answer this question. | 39.89 | 5 | 1 | 0 |
| 634 | Abstained; failed to answer | I could not obtain enough evidence to answer this question. | 50.44 | 9 | 3 | 1 |
| 1024 | Correct answer | 0.304 (calculation: 8958 / 29441 = 0.304) [E3.S1] [E1.S75] [E1.S41] | 34.74 | 6 | 1 | 0 |

## Source verification and evidence handoffs

- **1077:** Original Best Buy PDF page 45 states lower of cost or net realizable value, weighted-average costing, inbound freight and vendor allowances, and the expense/markdown/loss qualifications. The published response matches. Need planning, direct answering, and scope validation took three model calls and no tools.
- **370:** Original Godfrey Phillips PDF physical page 9 lists executive directors K.K. Modi (6 meetings), S.V. Shanbhag (7), Lalit Kumar Modi (3), and Samir Kumar Modi (5). Only Shanbhag satisfies more than six. The answer preserved both executive status and the strict threshold, with three model calls and no tools.
- **524:** Original slide 19 binds the named measurement tools to Twitter; slide 15 shows rural percentages 11 in 2013 and 17 in 2014. The answer should be **2013**. The source-quality gate correctly detected zero native text characters and forced image extraction. The collector preserved both values, context IDs, and the expression `rural_2013 < rural_2014`; the quantity checker accepted the inputs and operation. Application execution then raised `ValueError`: the arithmetic evaluator does not support comparison expressions. Offline replay of the saved typed draft reproduced `Only numeric arithmetic is allowed` without another API call. `tool.collect` failed; the accepted receipt retained the draft but no executable result. The published response abstained. This is an operation-contract mismatch after successful extraction, not missing source evidence.
- **634:** Original paper physical page 2, Figure 1, has two blue Functions-column boxes labeled **Fact Checker**. The source answer is `["Fact Checker"]` as a unique-name list. The first text-only answer proposed all program instructions and did not establish the color constraint. The quantity selector then requested original page images; the visual collector correctly read the two blue Fact Checker boxes, but put an unsupported `page` field on the group. Offline schema validation reproduced `groups.0.page: extra_forbidden`; item-level `page` fields are supported, group-level ones are not. The failed extraction produced no admitted quantity receipt. Subsequent inspection calls did not recover the visual finding; finalization abstained after no progress. Routing a visual name-selection/sort task through a count-only extraction contract is also a design limitation. This evidence does not establish that merely discarding the extra field would solve the complete task.
- **1024:** Original Costco PDF page 40 reports FY2021 net cash provided by operating activities of 8,958 million; page 38 reports current liabilities of 29,441 million. Application arithmetic gives 0.304269556..., or **0.304** to three decimals. The published response matches and includes the calculation and source IDs. Six model calls, one collection tool attempt, no retry.

The relevant eight original PDF pages were rendered and visually inspected in addition to the separate Luna reviews. All five diagnostic reviewers returned `answer_supported=true`, including the two abstentions. Those booleans are not used as the success metric: 524 and 634 failed to publish the source answer and remain failures. This run reinforces the need to distinguish answerability, correctness of a released claim, and successful task completion.

## General improvements suggested by these failures

1. Represent compare/select-min/select-max as typed operations with source-bound values and label mappings; validate operation compatibility before execution. Keep arithmetic evaluation restricted rather than allowing arbitrary model expressions.
2. Support visual categorical facts and lists separately from counts. Preserve validated extraction findings independently of downstream calculation and formatting outcomes.
3. Check extraction contracts at the handoff and expose actionable schema diagnostics. If recovery is added, bound it, log it, and verify semantic scope; do not silently relax arbitrary extra-field rejection.
4. Score a non-abstaining source-supported answer separately from safety validation and reviewer support flags. Neither can turn an unanswered question into a success.

## Usage, limits, and records

Main runs totaled **172.71 seconds**, **26 model calls**, **84,501 input tokens**, and **8,293 output tokens**. These times exclude model/dependency loading and separate reviews. Each run kept the same 10-request, 120,000-token, 240-second outer budget and bounded research policy as the prior diagnostics.

Separate reviews used 5 requests, 46,017 input tokens, and 6,180 output tokens. API dollar cost is unavailable because model prices were not configured; null cost is not zero cost.

Together with the preceding 7/7 selection on unchanged workflow code/settings, this makes **10/12 source-supported published answers on the current workflow**. Across historical development runs, **20 distinct questions have been tried and 18 have a source-supported published answer**; the other eight historical successes have not been rerun on this version. This is selected, source-scoped diagnostic coverage, not a full benchmark or an open-corpus retrieval score.

Raw profiles, results, model outputs, typed state, spans, reference-page renders, review packets, and reviews remain local under `row1077/`, `row370/`, `row524/`, `row634/`, `row1024/`, and `source-check/`. They are ignored by Git; only this compact English report is intended for the repository.
