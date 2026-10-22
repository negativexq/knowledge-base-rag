# Four population-composition questions: current runtime recheck

22 October 2026. Following the [original-source audit](../adaptive-composition-audit-20261022/REPORT.md), rows **206, 219, 225, 216** were selected in advance and run once each, sequentially. Application code at `a7e3c13a350c29ea9c433ec16bd4bdcf8f6ee585` was unchanged. Application and trace-harness hashes were frozen before this completed batch, checked before/after every row and again after completion. No prompt, retrieval, embedding, model effort, application budgets or runtime acceptance changes were made.

## Outcome

**All four executions returned generic insufficient evidence.** None of 206/219/225 released a qualified approximate result. Row 216 did not publish the unsupported count 128; this is a safe final behavior compatible with the source limitation, but not a verified runtime population-mismatch receipt or a newly promoted historical refusal.

The source-audited approximate calculations remain 206 ≈541, 219 ≈1,038 under the chart-category interpretation, and 225 ≈738 under the conditional-base estimate. They are not exact observed respondent counts. 216's percentage and the available combined subgroup sample cannot be multiplied as though their populations matched. A four-row gold-number score would obscure these differences. No distinct question, historical success, full-benchmark score or unresolved ledger total changes in this recheck.

| Row | Released result | In-run seconds | Model requests | Observed loss |
| --- | --- | ---: | ---: | --- |
| 206 | Generic insufficient evidence | 162.66 | 9 | Correct 541 estimate computed; final scope rejects government vs top-administration-official wording as entity mismatch |
| 219 | Generic insufficient evidence | 139.82 | 9 | 41% and 27% correctly read; no compatible sample-size composition; percentage/limitation drafts rejected by answer-type guard |
| 225 | Generic insufficient evidence | 120.20 | 9 | How-many request routed as item counting; 59% and 71%/11% never composed into an approximate headcount |
| 216 | Generic insufficient evidence | 131.07 | 9 | 18% read, no compatible Democrats-only denominator established; explanatory draft suppressed by answer-type guard |

Total model requests: **36**. Median in-run time: **135.44 seconds**, summed in-run time **553.75 seconds**. In-run timing includes initial retrieval through terminal output, excluding child setup/shutdown. With only four selected difficult cases, no general tail-latency inference is made. Input tokens: 232,406; output tokens: 29,200. Pricing is unconfigured, so dollar cost is unknown. These totals cover only the completed batch, not the aborted harness attempts below.

## Trace findings

### 206: correct arithmetic withheld by a semantic distinction

The first pass reads 36% but returns a percentage rather than people. Its checker properly identifies the missing sample base and operation. The repair obtains n=1,503, executes `survey_adults * poor_share / 100`, rounds to 541, and explicitly describes an estimate. The final scope model nevertheless returns `ENTITY_MISMATCH`: it distinguishes the question's government/administration ethics from the source's top-administration-official ethics, and rejects the poor-only percentage for the former.

The earlier original-source audit identifies these as the report's intended administration-ethics measure. This execution therefore exposes a likely over-narrow semantic interpretation at final scope, not a missing arithmetic capability. It must be addressed through source context/relationship and output semantics rather than a row-specific equivalence rule or automatic override of all entity objections. The stop is `TOOL_ATTEMPT_LIMIT`, with finalization lacking request reserve. The correct computation survives in typed state but is not released.

### 219: source read without a headcount composition plan

The original-image collection reads offline 41% and SNS users 27% accurately; the checker supports those readings. The operation stays `read`. No multiplication by a verified compatible senior sample base occurs. Subsequent reader/finalizer drafts offer percentages and explain that a count is not supplied; `ANSWER_TYPE_MISMATCH` and `NO_VALID_SUPPORT_BACKED_CLAIMS` reject these drafts because the question expects a count. One intermediate draft also substitutes online/no-SNS 32% for SNS 27%, producing an irrelevant 73%; it is not released.

The final draft correctly notes that the chart does not establish exclusive SNS-only use. Thus the approximate 1,038 response remains conditional on the intended two chart groups, not a license to silently reinterpret the narrower word "only." The workflow needs a transparent interpretation plus compatible-base approximate arithmetic, or a scoped clarification/limitation if that interpretation cannot be established.

### 225: a numerical headcount request is mistaken for an occurrence inventory

The first selection inspects demographic internet/broadband pages 16-17 and returns an empty count group. The second opens frequency page 4 and reads 71% daily plus 11% 3-5 times weekly, but still attempts to enumerate people rather than execute a conditional-percentage estimate. It reports that respondent records/counts are absent. It never composes all-65+ n=1,526, overall online 59%, and conditional frequency 82%.

The finalizer explains 82% but emits `11% + 71%` as the expression. Existing calculation validation flags `CALCULATION_UNPARSEABLE` in addition to the unsupported answer type. This is secondary to the wrong inventory-versus-derived-headcount route, not justification for relaxing expression parsing. No unsafe 82%-of-all-seniors or exact 738 answer is released.

### 216: safe insufficiency, useful limitation text lost

Both collection passes identify the Democrat row and 18% but have no respondent inventory or Democrats-only sample base. The run does not publish a 710 ×18% count. Its finalizer produces a useful explanation: 18% is reported but the relevant Democratic respondent count is unavailable. `ANSWER_TYPE_MISMATCH` prevents that source-limitation draft from being released, leaving generic insufficiency.

The original-source audit independently establishes why combined Dem/Lean Dem n=710 is incompatible with the Democrats-only percentage. This run's bounded search is not itself proof of document-wide absence or an independently checked subgroup-mismatch closure. Keep safe non-invention and explanatory publication as separate acceptance questions.

## General next correction

The missing capability is **population-aware approximate composition and answer-kind handling**, not more blanket refusal rules or a larger global budget:

1. Distinguish reported counts, counts of source occurrences, and headcounts derived from percentages before choosing the tool contract. "How many people" alone does not imply a list of individual people exists to count.
2. Carry each percentage's base population, conditional relationship, survey period and source locations. Sum only disjoint categories sharing a base; chain subgroup percentages only when the source establishes the join. Execute validated arithmetic in the application.
3. Preserve the output's reported/approximate/assumed status. Compatible rounded, weighted percentages can support an explicitly qualified sample-equivalent estimate, not an exact raw respondent count. "Approximately" does not repair 216's incompatible populations.
4. Allow a separately grounded source limitation or clarification to answer a numerical request without forcing it into a numeric answer contract. A failed calculation alone must not authorize absence, and a limitation must not silently borrow the wrong denominator.
5. Calibrate semantic scope using source relationships and actual question intent, with both over-rejection (206) and incompatible-population acceptance (216) controls. Do not introduce a question-specific government/official alias or force a reference answer.

These are findings and proposed work only; no runtime fix is included in this four-row measurement.

## Harness compatibility interruption

The initial batch stopped before terminal result export because new `research_progress` stage events use `stage`, while the trace script indexed the legacy `operation` key. Initial 206/219/225 logs are retained at this report's root; they are not question failures or successful measurements. The old batch was stopped and no overlapping question processes were left running.

The logging-only correction in `scripts/experiments/run_adaptive_trace.py` prints `operation`, falling back to `stage` (and a status default). It does not change generation or validation. The entire four-row batch was then restarted under `completed/` with a new freeze. All four terminal results and spans were exported successfully. Partial aborted-attempt usage was not exported and must not be treated as zero cost or folded into completed-batch totals.

Ruff for the trace script, `git diff --check`, and the ten existing research-stage/chat-stage tests pass. The full application suite was not rerun because no application source changed. Raw JSON, spans, captures and logs stay local and ignored; this English report is the tracked measurement summary.
