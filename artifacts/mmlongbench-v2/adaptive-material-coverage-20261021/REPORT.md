# Material answer coverage without penalizing concise answers

21 October 2026. Target 831; see the
[source audit](../adaptive-answer-coverage-audit-20261021/REPORT.md).

## Final implementation

The existing line-based adaptive scope call can return source-located material
omissions separately from support checks on emitted claims. It must identify the
missing source content, the original source binding to the question's scope, and
the question segment requiring it. Invalid, uncited or generated-only locations
cannot trigger completion. There is no length, wording or gold-answer gate.
Single values, concise paraphrases and merged summaries remain acceptable;
unrelated neighboring content and optional details are not required.

When all emitted claims pass their existing checks but a material omission remains,
the application checkpoints the supported parts and uses the existing answer-repair
role to append missing content from the same cited evidence. Original parts stay
unchanged. The shared repair budget limits completion; recursive completion is
disabled. New content still passes normal source, quantity and scope validation.

The follow-up scope call receives the previously located missing items and added
claim indexes. Its coverage task is to verify those gaps were filled, without
reopening an exhaustive inventory or requiring finer subsidiary instructions.
Normal factual/source checking remains active. The combined draft is checkpointed
before this call. If it times out, finalization retries that prepared draft's check
instead of regenerating a full answer. A repeated timeout or rejected completion
can end in safe insufficiency; it cannot certify the pending additions.

The final design has one sparse omission channel. The attempted full per-item
coverage inventory and planner scope classification were removed. No additional
judge role, retrieval pass, OCR, embedding change or global budget increase is
introduced. An adequate ordinary answer uses the same call count. A genuine
omission can cost one append call and the existing scope recheck.

Spans expose omission count, completion, pending-draft resumption and failure codes.
Typed checkpoints distinguish supported original content, proposed candidate parts
and pending/verified/rejected completion status. The model does not write the
application state or promote proposed parts to verified facts.

## Measurements, including failed attempts

All rows used the existing gpt-6-luna fast-path/evidence-needs profile: ten main
requests, 120,000 tokens and 240 application seconds, with a 360-second process
ceiling including setup. No paid after-run reviewer. Runs were sequential; each
batch froze all app Python plus the harness and verified them unchanged throughout.

The first five-row batch showed the sparse contract alone was not enough in that
attempt: 831 still omitted the three tasks and scope returned no omissions. Short
controls 387/519 and count control 382 passed without completion. Numeric-list
control 642 abstained on a separate ordering/precision handoff, not a coverage
objection.

| Row | Initial result | In-run seconds | Requests |
| --- | --- | --- | --- |
| 831 | Published supported but incomplete interview/team answer; not accepted | 43.83 | 3 |
| 387 | Rick Scott | 29.84 | 3 |
| 519 | eMarketer | 34.06 | 3 |
| 642 | Abstained; order/rounding correction did not publish | 189.59 | 9 |
| 382 | Two quizzes | 60.87 | 5 |

An intermediate full-inventory attempt identified the missing 831 activities but
failed operationally. It reported the same three gaps in two channels, producing
six entries. The patch added missing activities, but scope revalidation timed out
at 60 seconds. Finalization regenerated answers, and another scope review demanded
finer small-business substeps. The request reached its 240-second application
limit: **251.75 in-run / 267.32 process seconds**, seven completed requests plus
two timed-out calls. SDK usage does not include those timed-out calls as completed
requests. This is a failed outcome, not a recovered answer.

The intermediate controls still passed: 387 = Rick Scott (35.99 s / 3 requests),
519 = eMarketer (38.51 s / 3), 382 = two quizzes (63.37 s / 5). No completion call
was triggered on those adequate answers.

After removing full-inventory output, keeping a single omission list, bounding
follow-up coverage to the original gaps and preserving the patched draft, the
affected pair was measured again:

| Row | Final result | In-run seconds | Process seconds | Requests |
| --- | --- | --- | --- | --- |
| 831 | Interview/team content retained; supplier research, local-business resources/supply-chain investigation and frequently used product selection added | 72.47 | 87.76 | 5 |
| 387 | `Rick Scott.`; no completion | 31.40 | 46.79 | 3 |

831 directly exercises completion: need planner, answerer, scope validator,
answer repair, scope validator. The first check locates the three missing activity
groups in a single omission entry; the application preserves the original part
and appends one sourced part. Both pass the final check. No retry, timeout, tool
call or finalizer regeneration occurs. The checkpoint ends verified.

Its model time is planner 10.74 s, answerer 3.37 s, first scope 21.09 s, append
5.78 s and final scope 21.00 s. Scope remains the largest component; reduced
latency in this pair is not a universal performance guarantee. The three task
groups match the independently reviewed Quarter 3 source, not only the reference
label. The answer appropriately retains additional supported interview context.

The final pair uses eight requests and 103.87 summed in-run seconds. Pricing is
unconfigured, so dollar cost is unknown. Raw JSON, spans, captures, hashes and logs
remain local and ignored. Failed artifacts are retained separately.

## Verification and remaining boundaries

**2,408 tests passed**, four skipped and five deselected. Ruff and mypy pass.
Regression cases cover adequate short/specific/paraphrased answers, append-only
completion, malformed/generated source locations, failed additions, bounded
repair, checkpoint preservation and timeout resumption without regeneration.

The live final pair does not exercise timeout resumption; that path is verified
offline. Coverage is semantic model judgment, not a deterministic guarantee that
every omission will be detected. The change addresses missing content already
present in the cited source, not multi-window document inventory closure. The
noncompact plain-scope path retains its prior behavior.

642 remains a presentation handoff issue: scope objects to unsorted two-decimal
scores, although the question asks descending order and one decimal. It reports
the wrong PERIOD_MISMATCH category while describing a presentation repair, then
the workflow reruns collection/checking and exhausts budget. No additional source
evidence was requested by that objection. This correction does not claim to fix it.

831 moves to supported answers. Historical totals become **80 supported / two
qualified / 18 correct refusals / 20 unresolved**, across the same 120 questions:
**100/120 (83.3%) accepted outcomes**, including qualified calculations. This is
the historical ledger, not a full latest-code 120-question score.
