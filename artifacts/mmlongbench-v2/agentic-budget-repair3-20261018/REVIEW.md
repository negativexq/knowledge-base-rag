# Final policy: targeted three-question smoke

Revision `a4eb6df`, `gpt-6-luna`, same corrected labels, existing corpus and hard
shared budgets. Rows 381, 507 and 1016 were selected before this output to exercise
quiz-count verification, single-document routing and calculation/verification
recovery. This is a **targeted development test**, not a random sample or a new
mini10. Do not compare its aggregate accuracy with a ten-question run.

| Row | Result | Audit |
| --- | --- | --- |
| 381 | Withheld | Scope rejected; token preflight prevented a further correction. |
| 507 | Withheld | Literal search returned zero blocks; token preflight prevented the next turn. Earlier correct Little Rock behavior was not stable. |
| 1016 | 10314 | Correct grounded sum 6692 + 2642 + 980, citing FY2021 tables E1.S55/E1.S134 and report date E1.S3. One invalid scope judgment was repaired. |

The dedicated **post-research** repair slot was not used by any question. Costco's
correction fit inside the normal three research requests; the token reserve and
remaining-history estimates prevented another call on the other two questions.
Deterministic agent-loop tests verify the separate tools-closed repair slot and
its mandatory final scope receipt; this live smoke does not prove that it will
fit a large real-document context.

This run gives **1/3 grounded correct** and two budget blocks, with 11 real model
requests, 121133 input tokens and 923 output tokens. No quality, cost or latency
improvement is established. It confirms that simply adding numeric limits is not
a solution for weak routing, repeated large contexts or unreliable scope judgments.
No further threshold/prompt changes were made from these outputs. The final
implementation remains an experimental branch with the existing opt-in agentic
rollout, no push, no deployment and no `.env` edits.

The next controlled evaluation should start from the original 4/8-grounded
reference and change one component at a time. Neither this smoke nor the earlier
combined experiments constitute an isolated causal analysis or a held-out benchmark.

The unmodified automatic reports, fixed selection/settings/corpus and separate
manual review are retained here. Raw `results.jsonl` stays local and git-ignored.
The harness uses tenant/question-document scope but does not exercise HTTP auth
or application user/group grant administration. Cross-tenant probes found no leak;
separate offline tests cover grants, revocation and final release.
