# Missing-input, conditional-lookup and empty-inventory recheck

Rows 212, 635 and 1023 were rerun sequentially after general extraction-contract
changes. Runtime hashes were frozen before row 212 and unchanged across all three
requests. The [initial five](../adaptive-unseen-five-20261019/REPORT.md) remain recorded.

| Row | Published result | Source-reviewed outcome | Main time / calls / tools |
| --- | --- | --- | --- |
| 212 | Abstained | Unresolved; newly located comparison evidence was not consumed. | 147.22 s / 8 / 3 |
| 635 | `["Fact Checker"]` | Incorrect visual condition; the original box is blue, not grey. | 70.51 s / 6 / 1 |
| 1023 | 19.246 percent | Correct; `(799 + 6692 + 3916) / 59268 * 100`. | 57.96 s / 6 / 1 |

**One correct published answer out of three.** Total main time was 275.69 seconds;
batch wall time including startup and separate reviews was 382.36 seconds. Pricing
is unset, so API dollar cost remains unavailable. Same model, effort profile,
ten-request/120,000-token/240-second ceilings, index and retrieval settings as before.

## What the runs establish

The application now accepts grounded missing-operand coverage objections and can
search the same authorized immutable document. Conditional lookup has a typed
comparison-to-output join, executed by application arithmetic rather than selecting
the largest output value. List contracts can represent a source-inspected absence,
and rejected items can be removed without changing unaffected items. Empty results
remain usable by independent finalization after research closes.

Row 1023 selected the balance sheet and the lease note, including the 3,916 million
total lease-liability figure. The final answer passed input and scope checks and the
independent original-page review. Its success does **not** demonstrate the new gap
search: it used one collection tool and did not require that repair branch.

Row 212 correctly selected conditional-lookup mode and transcribed congressional
support as 92% and 90%, but initially bound ethics to partisans' ratings of their own
party (66%/64%) instead of public ratings (41%/42%). Missing policy inputs triggered
document search, which admitted `E3.S1` containing the actual 50%/50% comparison and
41%/42% ethics values. Repair nevertheless selected the same physical pages 12 and
14. Moving an existing input source into the context role bypassed the old reuse
guard. The missing fields remained unresolved; no calculation was executed.

Row 635's collector called the Fact Checker background "pale gray-blue"; the input
checker accepted it. Direct post-run inspection of original Figure 1 on physical
page 2 shows blue Fact Checker boxes, pink QA Model and green Logical Reasoner.
The released name therefore fails the question's grey condition. The separate
reviewer received **no image**, because this question has an empty reference-page
list; its output explicitly declined independent visual verification. Empty-list
support was not exercised by this run and cannot be credited with a live success.

## Validation and remaining work

Before the batch, 2,148 backend tests passed, four optional tests skipped and five
were deselected; Ruff and mypy were clean. Seven new offline tests cover conditional
lookup, source-gap routing/search, empty-list evidence and finalization. Those tests
establish mechanical behavior, not reliable live semantic color/population judgments.

The follow-up implementation links a typed gap-search receipt to actual candidate
inspection, checks source content/pages rather than role IDs for progress, and keeps
lookup populations/series/periods explicit. That follow-up has separate tests and a
separate run directory. Neither the source-handoff defect nor the visual-condition
failure is hidden by this report. No runtime question IDs, answers, party names or
physical-page constants were introduced. Raw outputs remain local and ignored.
