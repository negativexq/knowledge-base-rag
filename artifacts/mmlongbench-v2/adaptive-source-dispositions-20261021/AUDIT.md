# Source-disposition lifecycle audit

Subsequent design decision: preserve normal correct-answer behavior and avoid an
additional terminal judge loop. The [current follow-up](answer-local-validation/REPORT.md)
records the narrower implementation and controls. The assessment-stage proposal
below is the original audit recommendation, not the current implementation plan.

Audited 21 October 2026 on `audit/thirteen-source-dispositions`, based on merged
main `45402ee`. This audit reads existing code, captures, spans and source reviews.
It adds documentation only: no runtime changes and no new paid model calls.

## Conclusion

The main gap is the lifecycle connecting evidence to a terminal outcome. Typed
source dispositions exist, but their production remains optional. Across all
**12 completed runs, covering six distinct questions, zero source-disposition
receipts were created**. This is not twelve failed answers: the arithmetic control
380 succeeds three times, and the latest 830 correctly requests clarification.

The evidence does not establish an embedding-model defect. It establishes missing
outcome routing, incomplete acquisition/reuse, and an evaluation export defect.
Stricter answer prompts would not repair those application contracts.

## Evidence and limits

The [implementation report](REPORT.md) records three sequential four-row batches:
initial `728,730,380,1017`, followed by two batches of `508,830,1017,380`.
Each batch froze application Python and the trace harness before measurement;
every subprocess exited zero and retained its batch's source hashes. Exit zero
does not certify an answer. Raw captures, spans and source manifests remain local
and ignored. Original-PDF findings come from the prior
[thirteen-question source audit](../adaptive-negative-thirteen-audit-20261020/REPORT.md).

| Latest row | Observed terminal result | Run seconds | SDK requests | Audit finding |
| --- | --- | --- | --- | --- |
| 508 | Generic insufficient evidence | 126.96 | 9 | Research turn limit; no typed finding despite recognition of the neighboring reported entries. |
| 830 | Clarification | 26.96 | 4 | Correct question survives normalization; token-only export records an empty answer. |
| 1017 | Finalization failure | 135.77 | 8 | Three checked inputs survive; repair collector times out; full lease note is absent from final visible evidence. |
| 380 | Correct 8,367,277,000 rupees | 52.32 | 6 | Source operands, scale and application arithmetic remain effective. |

## 1. P0 — source-finding production is optional

`QuantityAssessment.source_disposition`, reader stop proposals and scope judgments
can supply findings, but none is a required lifecycle transition.
[`AdaptiveSession.current_disposition`](../../../app/llm/adaptive.py#L428)
retrieves an existing eligible receipt.
[`_finalize`](../../../app/llm/adaptive.py#L2022) reuses successful calculations or
an existing disposition, then asks for a plain `AdaptiveAnswer`. That final schema
cannot create the missing independently reviewed source finding.

**Recommended correction, not implemented by this audit:** after research stops,
the application should dispatch a terminal semantic assessment when there is no
releasable result or reusable reviewed outcome. Use reserved finalization budget;
classify source conflict, closed-object absence, clarification or incomplete
evidence. Require independent semantic review and version-bound witnesses for
strong claims. Reuse an existing checked outcome without another call. A budget
stop must remain incomplete evidence when the required scope was not inspected.

## 2. P0 — positive binding rejects an absence explanation

In the middle 508 run, the answerer explains that the geographic list reports
AR01 and AR02, while the requested AR03 is not provided. The checker marks the
claim supported, cites source lines and raises no factual objection. However,
the positive target requirement remains unknown/unestablished, causing
`SCOPE_REQUIREMENT_UNRESOLVED`. The subsequent abstaining draft includes answer
parts, which normalization safely removes. No independently reviewed negative
receipt survives to explain the result.

[`validate_requirements`](../../../app/llm/scope_requirements.py#L72) correctly
requires positive target binding for a positive answer. Its contract cannot also
represent proof that a target is missing from a complete relevant object.

**Correction:** route independently checked source findings as a distinct outcome.
Do not globally weaken target binding, publish unchecked abstention prose, or add
row/entity-specific exceptions. Closure of the relevant object remains necessary.

## 3. P0 — missing-input acquisition and reuse remain incomplete

1017 has separate failures across the three attempts:

- Initially, switching the old page window from text to images counts as fresh
  evidence before other located pages are opened. The new candidate-page priority
  and bounded replacement logic have offline coverage; subsequent live attempts
  do not establish a causal recovery through that branch.
- In the middle attempt, general research finds Note 6 and the correct six-input
  formula, `799+6692+222+72+2642+980 = 11407` million. Reader drafts mix an answer
  and a prepared calculation. Finalizers rewrite canonical arithmetic with display
  commas; broad source locators also trigger bounded-page inspection. The correct
  total is not published. Mixed-plan normalization and canonical proof reuse have
  since been implemented and checked offline.
- In the latest attempt, only `799`, `6692` and `2642` are independently retained.
  The repair collector times out after **60.01 seconds**, about 44% of the run.
  The final visible evidence does not contain the complete Note 6 lease inputs.
  Finalizers offer the explicitly qualified subtotal `10133`; this is not the
  complete requested total and fails the numeric source inspection contract.

The latest failure is therefore not evidence that the complete correct total was
found and then rejected. That occurred along a different path in the middle run.
The timeout is inside an awaited model call; traces do not establish whether the
provider, network or another external condition caused its latency.

**Correction:** retain checked operands and collect only missing inputs, then let
the application join and calculate. Independently review the resulting semantic
composition. Do not repeatedly collect all old pages or treat a partial sum as the
requested total. If completion fails, preserve known values in a scoped
insufficiency outcome rather than asserting document-wide absence.

## 4. P1 — benchmark export loses clarification

The latest 830 draft contains a valid typed clarification, alongside answer text.
Normalization prioritizes clarification and removes the draft. The production
stream emits a `clarification` event and returns. The
[trace harness](../../../scripts/experiments/run_adaptive_trace.py#L239) only joins
`token` events into `answer`; it does not persist clarification or terminal kind.
Thus an empty exported answer is not proof of runtime silence.

An **offline replay of the exact captured draft**, using the real normalization
and stream path, emits: “Which market are you asking about?”, with U.S. stock
market / another market options. No model call was made. The original harness
does not persist the full event stream, so this is replay evidence, not an
original recorded clarification event.

**Correction:** export terminal kind and clarification explicitly. Evaluate it as
clarification; do not invent an answer string or automatically count it as failure.

## 5. P1 — whole-document absence is intentionally unsupported

[`admit_disposition`](../../../app/llm/research_dispositions.py#L160) requires
question/object binding, closure, excluded alternatives and no pending candidates.
It always downgrades document-wide claims with
`DISPOSITION_DOCUMENT_CLOSURE_UNESTABLISHED`. This is a necessary safety boundary,
not a completed whole-PDF absence mechanism.

**Correction:** add an application-owned multi-window coverage manifest before
certifying document-wide absence. Until then, retain bounded findings or incomplete
evidence. Removing this guard would create premature refusals.

## 6. P2 — request attempts and usage accounting differ

Latest 1017 has eight SDK-accounted requests but nine `llm.request` attempt spans;
the middle attempt has nine versus ten. Timeout attempts must be reported
separately from completed requests and requests with known usage. These counts
alone do not prove a quota overrun or dollar cost. Pricing is not configured, so
API dollar cost remains unknown.

## Fix order and acceptance

1. Connect terminal source assessment and distinct source-finding outcomes to
   finalization. Exercise bounded absence, source mismatch, clarification and a
   delayed positive match; incomplete coverage must never become a strong negative.
2. Complete incremental missing-input acquisition and checked-operand composition.
   Recheck 1017 and retain the correct 380 arithmetic control.
3. Export terminal kind/clarification and separate timeout attempts from known
   usage. Recheck the captured 830 event without a paid call first.
4. Implement document-wide closure only with an explicit coverage manifest.

The implementation preceding this audit passes **2,368 tests**, with four skipped
and five deselected; Ruff passes and mypy passes 162 files. Those checks establish
local contracts, not end-to-end recovery of the thirteen source-negative cases.
This documentation-only audit makes no new ledger promotions: **120 distinct
questions; 79 supported, two qualified, four verified refusals, 35 unresolved**.
