# Complete company director inventory: successful bounded recheck

## Outcome

**Row 372 answered correctly:**

> Mr. R.A. Shah; Mr. Lalit Bhasin; Mr. Anup N. Kothari; Mr. C.M. Maniar; Mr. O.P. Vaish.

The five names and their Non-Executive & Independent category are supported by the original table on physical page 9. The runtime published the complete list after input review and final scope validation. A separate after-run original-source review agreed. The benchmark gold answer and reference pages were unavailable to main generation.

## Observed execution

1. Initial collection again selected the three-person Audit Committee subset on page 11. The input checker accepted it, showing that the first reviewer can still make a coverage mistake.
2. Final scope review correctly rejected the subset as insufficient for the company-wide roster and emitted a grounded missing-evidence objection. The original checked transcription and objection remained in typed state.
3. The application sent that objection back to source selection, preserving list mode. The native page catalog made physical page 9 individually discoverable inside an admitted 8–16 source range.
4. The repair selected original physical pages **9 and 10**. Application image handles bound all five returned names to physical page **9**.
5. Independent input/coverage/operation review and final scope passed. The application published the five-item list, citing the checked proof and its original source. The parent three-item receipt remains in state; it was not released as the whole answer.

The run took **58.28 seconds**, **10 model calls**, **2 tool attempts**, and **0 application diagnostic retries**. It used 36,945 input tokens and 3,173 output tokens, including 4,084 cached input tokens. A second source inspection is counted as a tool attempt, rather than hidden as a retry. Separate diagnostic review is excluded from main usage. Model prices are unset; dollar cost is unavailable.

## Last implementation change and causal limit

The preceding pair found page 9 but attempted to combine the old page 11 with newly requested pages 8–10, exceeding the three-page inspection window. The application can now keep old evidence in its parent receipt while requesting a complete replacement inventory within a fresh three-page window. The checker must establish coverage of the original question and prior supported items against the new evidence, allowing source-supported name variants. Prior items are not copied into a fresh source window as if re-observed there. This branch has an end-to-end offline PDF test; the source-window ceiling remains three.

**This live success used the existing final-scope `source_research` path with pages 9–10; `inventory_replacement` was false.** It therefore demonstrates the combined catalog, goal-preserving scope handoff and independent fresh-source checking, but does not establish that the last window-branch change alone caused the success. The bounded replacement branch is verified offline, not directly exercised by this paid run. One successful recheck is not a stability estimate.

## Validation and coverage

Before the paid recheck: **2,141 backend tests passed**, four optional skips and five deselected; **211 adaptive tests passed**; Ruff and mypy were clean. Runtime hashes were frozen and unchanged throughout the single request. The same gpt-6-luna effort settings, ten-request/120,000-token/240-second diagnostic ceilings, index, embedding, ingestion and initial retrieval/reranker settings were retained. No SDK retry or question-specific entity/value/page rule was added.

The [visual-heading question](../adaptive-page-catalog-20261019/REPORT.md) passed in the preceding frozen revision. These two successful case outcomes span two revisions; they are not a same-version 2/2 benchmark batch. The earlier [scope/interpretation recheck](../adaptive-scope-handoffs-20261019/REPORT.md) answered the male percentage gap and finance ratio and retained the correct explicit-period refusal. Those controls have not all been rerun after the final window change.

Historical distinct-question coverage is now **30 tried: 28 source-correct published answers, one correct refusal, one never-successfully-answered reference question**. Row 661 remains unresolved: the 0 V reference requires an inference that the waveform does not explicitly annotate. These historical counts span development revisions and do not mean all 30 have passed on the latest code. Raw JSON, state, catalogs, model captures, review packets and spans remain local and ignored; only this English summary and ledger updates are intended for Git.
