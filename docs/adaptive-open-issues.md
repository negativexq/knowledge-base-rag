# Open adaptive workflow issues

Updated 20 October 2026. This register separates confirmed code defects, semantic
acceptance failures, partial fixes and source/metric adjudication. The detailed
[code-and-trace audit](adaptive-issue-audit.md) contains source anchors and offline
replays. Prior run reports retain unsuccessful attempts.

There are **35 unresolved question/workflow outcomes** in the
[120-row ledger](adaptive-solved-questions.md). Two additional questions have qualified interpreted calculations. These are not independently proven
code bugs. One row can exercise multiple families; counts below are not additive.
The shared matcher scores and strict source/workflow audit remain separate.

## Current priorities

| Issue | Priority / status | Confirmed evidence and boundary | Next correction |
| --- | --- | --- | --- |
| REPAIR-001: exact text equality in input repair | P0; implemented; targeted checks pass; end-to-end blockers remain | 366, 1016 and 1070 raise `REPAIR_CHANGED_UNTARGETED_STRUCTURE`. Equivalent interpretation text triggers rejection; 1070 expressions have identical ASTs. | Application-owned operation fields and operand-only patch contract. Preserve protections against genuinely changed operations. |
| REPAIR-002: text locators inside image repair | P0; implemented; targeted checks pass; end-to-end blockers remain | 1072 fresh pages [40,39,39] become [40,null,null] when untargeted old text operands are restored; then `QUANTITY_ITEM_PAGE_INVALID`. | Preserve per-operand provenance independently from current observation modality; do not invalidate prior evidence with a record-wide image requirement. |
| PAGE-001: required visual page dropped as context | Handoff fixed; row 641 relationship review remains open | Earlier 641 lost the comparison page through role filtering. The follow-up retains both required pages and delivers definition evidence E1.S60; independent review still rejects the evaluation-population join. | Preserve required-page authority and context budget. Investigate the remaining semantic relationship under COMPOSE-001 rather than repeating the page-filter fix. |
| FLOW-001 / ROUTE-001: universal quantity fallback | Implemented; prose dispatch verified live; remaining source gaps | Prior 508/511/517/520 entered incompatible numeric collection. Dispatch now uses typed count/calculation needs or a compatible fast-answer capability hint. Failed collection returns an application-owned receipt and resumes bounded research. | All four target prose cases avoid numeric collection; 511 and 517 are recovered. Source-scoped absence in 508/520 remains unresolved. Failed drafts remain checkpointed. |
| ACQUIRE-001: located source not opened in the required representation | Implemented; targeted acquisition verified live | 517 now inspects the map and releases the correct qualitative answer. Page opening delivers both correct operands in 380; scale conversion remains under UNITS-001. Controls 511/382/477 retain correct answers. | Broaden acquisition coverage without forcing all PDFs through vision or treating partial reads as complete. See [report](../artifacts/mmlongbench-v2/adaptive-source-acquisition-20261020/REPORT.md). |
| INV-001: page or subset mistaken for whole inventory | P0; targeted counts recovered; broader accumulation open | Prior 476/381 releases were 5/6 instead of 9/7. The follow-up now publishes 9/7 from the original source. Optional parser metadata is not a release gate. | Keep independent coverage review and source-scoped document-window dispatch. Accumulate independently checked partial inventories when no three-page window suffices. |
| MEMBER-001 / SCOPE-001: group membership and target constraints | P0; targeted group count recovered; semantic cases remain | 399 now releases 4+3=7 from the correct groups. Prior 660/638/510 unsafe answers are withheld; their final dispositions remain unresolved. 831 completeness still needs a targeted check. | Retain quoted question restrictions, independently checked inventories and original native source witnesses. Validate remaining location/relationship/list cases without treating missing parser text as a factual contradiction. |
| REPAIR-003: wrong freshness requirement | Implemented; local reuse verified offline; live scope gaps remain | Prior 214/380/637 reached `REPAIR_REUSED_INSUFFICIENT_SOURCE`. Grounded scope diagnostics now distinguish existing-source binding, interpretation, unit transformation and presentation from missing source or contradiction. | 637 now releases 1 without repair. 214 has an unestablished premise and 380 lacks income; neither exercises local reuse live. Same-source repairs still require independent review. UNITS-001 remains separate. |
| PROV-001: header/entity/period/page binding | Partially implemented; 1086 context verified live | Version-bound original-page context now reaches first text collection/review; 1086 retains 13,929 million with six requests. Issuer/relationship cases such as 1070 remain. | Broaden binding coverage without inferring units or treating a file identity as semantic issuer proof. [Report](../artifacts/mmlongbench-v2/adaptive-context-coverage-20261020/REPORT.md). |
| NUM-001: numeric displays and absence | Partially fixed; remaining sensitivity | Original crash/checkpoint cases 471/1026/1025/388 recovered. The numeric-authority follow-up recovers 1016/1021; 1074 remains unresolved and has not been remeasured after that fix. | Retain display/canonical separation and checkpoint-before-execution; preflight notation compatibility without guessing locale or treating absence as zero. |
| UNITS-001: arithmetic output transformation | Implemented; 380 recovered live | Typed source/base/output receipts produce **8,367,277,000 rupees** from source amounts in lacs. Ratios and percentages remain correct in controls. | Keep source-scale and metric review; no exchange-rate inference or silent formula rewriting. [Report](../artifacts/mmlongbench-v2/adaptive-unit-arithmetic-20261020/REPORT.md). |
| CALC-001: named function becomes missing operand | Implemented; abs verified live, min/max/mean offline | Bounded allowlisted functions now execute as operators, with every argument source-checked. Row 366 releases 35.821% under an explicit relative-shortfall convention. | Metric adjudication remains INTERPRET-001; support for an operator does not establish the intended formula. |
| FINAL-001: completed calculation cannot publish proof | Implemented; targeted publication recovered | A protected allocation inside the existing evidence total preserves checked proofs; page reads no longer pay for fragments plus a duplicate view. 1086 now publishes 13,929 million; 380 publishes 8,367,277,000 rupees in the preceding frozen pair. | Broaden coverage for oversized/multiple results; initial unit-context repair can still cost another image pass. Source/scope review remains mandatory. [Report](../artifacts/mmlongbench-v2/adaptive-result-reservation-20261020/REPORT.md). |
| COVER-001: incomplete source-object coverage | Partially implemented; 1017 recovered, visual closure remains open | Page/search cursors and authorized source buffers survive checkpoints. 1017 now releases 11,407 million from the balance sheet and lease note. 730/728 lack document-wide absence closure; 662/663 lack guide-wide visual inventory; 641 population join remains unresolved. | Multi-window inventory accumulation/closure and source-scoped negative receipts; acquisition exhaustion alone is not semantic completeness. |
| COMPOSE-001: denominator/population/plan composition | P1; observed; some reference assumptions disputed | 206/225/219 require approximate survey headcounts; 216 cannot borrow Dem/Lean Dem base for Democrats; 1015 needs a stated EBITDA definition. | Keep population, denominator, period, metric definition and approximation status with observations. |
| CALL-001: mixed answer/calculate decisions and repeated finalization | Observed; open efficiency defect | 1017 has the correct six-input formula by request 5, but two reader outputs mix answer and calculation actions. Search repeats; a broad source locator also causes a finalizer retry. Final answer is correct at ten requests. | Operation-specific decision contracts and prepared-calculation handoff; preserve source/unit/scope validation rather than accepting malformed mixed actions. |
| STOP-001: mismatch, absence and no progress conflated | P1; observed | 207/222/365/367/830/1084 repeat searches or stop without verified terminal receipts; 384 ends in ModelRetry. | Grounded source-scoped mismatch/absence receipts, distinct from partial search and execution error; terminate deterministically when justified. |
| OBS-001: safe domain errors missing from spans | P1; confirmed | Spans retain exception class only, but local `ResearchState.needs` retains exact guard codes; previous audits overlooked this. | Allowlisted domain codes in spans/typed failures; preserve the privacy boundary against arbitrary messages/content. |
| JUDGE-001: false arithmetic veto over checked calculation | P0; runtime correction implemented; live answer restored | Prior 1021 computes 29441/41190 = 0.714760… → 0.715 correctly, but scope validator twice insists on 0.716; after-run reviewer repeats the error. | Exact application candidates are locally reexecuted and receive semantic-only scope projection; source/formula/scope challenges remain. After-run reviewer arithmetic remains an EVAL-001 concern. |
| SCHEMA-001: numeric readability mixed with binding ambiguity | P1; schema correction implemented; relationship review remains required | Prior 641 reads 56.82 but sets ambiguous status because dataset identity is uncertain; native NumericReading rejects a non-null value with that status. | Ambiguous numeric displays survive checkpoints without executing; lookup binding status is separate. Same-snapshot definition context is supplied for independent join review. |
| EVAL-001: judge/image coverage and missed constraints | P1; confirmed audit weakness | Reference-page-only review omits images for many negative rows and relevant pages for 1086/834. Reviewers approve wrong grouping/range/location in 399/660/638. | Audit actual observed pages and independent required source scope; calibrate both false acceptance and false refusal. |
| VIS-001: visual-condition acceptance | P1; semantic defect open | 635 accepts blue Fact Checker as grey; 475 correctly rejects a non-red bar but does not close the color defect. | Original-source visual condition and object binding; no color-specific document rule. |
| COUNT-001 / INTERPRET-001 | Adjudication + observed workflow failures | 658 merged N-prefix memberships; 663 connection-graph unit; 366 relative shortfall vs percentage points; 732 panels vs numeric figure; 1075 current-debt inclusion. | Establish task/counting unit/metric definition before certifying or forcing a reference answer. |
| SRC-001 | Source limitation open | 661 waveform low voltage is not explicitly annotated; 0 V interpretation is not independently established. | Source adjudication, not a prompt rule requiring the gold number. |

## What changed in this audit

The previous register recorded many symptoms but did not identify the exact
repair guards. The audit checks `ResearchState.needs`, raw model outputs, typed
receipts and source code together. Corrections to prior diagnoses:

- **1070, 366, 1016:** exact failure is `REPAIR_CHANGED_UNTARGETED_STRUCTURE`, not an
  unspecified ValueError or proven source-ID admission failure.
- **1072:** exact failure is `QUANTITY_ITEM_PAGE_INVALID`; saved fresh image handles
  bind correctly before merge restores untargeted text locators.
- **636:** exact failure is `QUANTITY_REFERENCE_TOO_LARGE`, the bounded witness
  resolver, not proof that the model cannot read the figure.
- **641:** the selector does request both pages. The application role/page filter
  removes one, so this cannot be assigned only to model source selection.
- **NUM-001:** original Decimal-exception containment and review checkpoint fixes
  remain implemented. New notation, unit and dispatch failures do not mean the
  original fix was absent.
- **CALC-001:** offline execution after a controlled merge recovery exposes a
  second failure in 366. This was not its initial live stop.

Three live merge failures were replayed offline. In 1016, retaining the original
operation text is sufficient for the existing extracted values to execute to
10314 without a new model call. That is not a published live success or a code fix.
The original failed run and score remain unchanged.

## Acceptance and implementation policy

First fix the reproduced repair/locator/page handoff failures, then typed dispatch
and final-scope repair selection. In parallel preserve tests against false closure,
wrong category membership and missed target conditions. A release policy must not
trade fewer abstentions for more unsupported answers.

Keep all changes general: no expected counts, gold values, row IDs, color names,
company prefixes or document-specific pages in runtime. Model effort, embedding,
reranking and global prompt tightening are not first-line responses to these
confirmed code failures. Existing ACL, document-version checks and budgets remain
required. No runtime edits or paid calls were made for this audit.

The [audit](adaptive-issue-audit.md) specifies code locations, proof strength,
acceptance boundaries and remaining uncertainty. Detailed run evidence remains in
the linked ledger and reports. Raw captures, JSON, spans and renders remain local
and ignored.

## Repair implementation follow-up

REPAIR-001, REPAIR-002 and PAGE-001 now have application changes and regression
coverage. See the [implementation and remeasurement report](../artifacts/mmlongbench-v2/adaptive-repair-handoff-20261020/REPORT.md).
Offline replay passes the previously failing handoff checks, while separate issues
in 366 and 1070 remain. The sequential live regression completed: one published answer (1086), four
abstentions. The prior operation/locator exceptions did not recur, but separate
notation, metric-definition, identity/schema and false-judge blockers remain.
Historical benchmark counts have not been recomputed with this development batch.

## Numeric authority follow-up

The [numeric authority report](../artifacts/mmlongbench-v2/adaptive-quantity-authority-20261020/REPORT.md)
records live recovery for 1016, 1072 and 1021 and retention of 1086. Row 1072 is an
explicitly interpreted calculation, not a source-reported ROCE definition. Native
source checking can correct invalid notation metadata without changing values or
reinterpreting valid numbers. Exact application arithmetic candidates receive
semantic-only scope validation, with full original-answer release fingerprints.

Row 641 exposed two additional handoff gaps: optional context evicting required
page authority, then definition passages losing to result sections. Required seeds
now reserve context budget first; bounded same-snapshot relationship definitions
are surfaced as candidates without certifying aliases. Targeted results and all
unsuccessful attempts are retained in the report.

Latest row-641 result: the typed relationship path sends E1.S60 to independent
review without depending on `evidence_kind`, another selector call or a document
search. It still abstains because the reviewer does not accept the evaluation-
population join. This remains open; definition/subset evidence is not automatically
an alias. The four other target questions publish answers, with 1072 tracked as a
qualified calculation rather than a uniquely source-defined metric.


The [inventory/scope follow-up](../artifacts/mmlongbench-v2/adaptive-inventory-scope-20261020/REPORT.md)
records the initial over-rejection, intermediate failures and successful recoveries.
The historical ledger is now 74 source-supported answers, one qualified calculation,
four verified refusals and 41 unresolved outcomes across the same 120 questions.
The frozen full-set matcher scores above are not recomputed from these targeted reruns.


## Typed dispatch and repair classification follow-up

The [routing and repair report](../artifacts/mmlongbench-v2/adaptive-routing-scope-20261020/REPORT.md)
tracks the FLOW-001/ROUTE-001 and REPAIR-003 implementation and the completed nine-row
sequential regression. Application-owned collection receipts preserve failed and successful
work separately; a failed numeric draft no longer automatically terminates research.
Existing-source scope repairs avoid a redundant selector and freshness veto while
retaining independent review. Unknown, missing-source, contradictory or invalid
diagnostics do not disable freshness. No ledger question is promoted by offline tests.

The live batch recovers 511 and 637 and retains both 382/477 controls. All four prose
targets avoid numeric collection. Rows 508/517/520 remain evidence-acquisition or absence
outcomes; 214 has a premise defect and 380 still lacks income plus a scale conversion.
The local-reuse scope branch is covered offline but not exercised by these live targets.
The current historical ledger is **76 supported / 1 qualified / 4 verified refusals /
39 unresolved**, with 120 unique questions.


## Source acquisition audit

The [read-only source handoff audit](adaptive-source-handoff-audit.md) confirms that
380's income amount already exists in the index and is returned by the existing
authorized page reader. It also confirms that 517 never inspects its available map.
ACQUIRE-001 records the missing locate-to-open-to-extract handoff; no runtime fix or
additional paid run has been made for this audit.


## Source acquisition implementation follow-up

The [implementation and live report](../artifacts/mmlongbench-v2/adaptive-source-acquisition-20261020/REPORT.md)
recovers 517, retains 511/382/477, and verifies that 380 now receives both operands.
The initial 517 attempt lost a correct qualitative extraction at a generic text-value
capacity limit; its correction preserves full relationships while retaining numeric
execution bounds. At that measurement UNITS-001 remained open for 380. Its historical totals were
**77 supported / 1 qualified / 4 verified refusals / 38 unresolved** across 120 questions.

## Unit arithmetic and named-function follow-up

The [new measurement](../artifacts/mmlongbench-v2/adaptive-unit-arithmetic-20261020/REPORT.md) recovers 380 and moves 366 to qualified interpretation. Historical totals are now **78 supported / 2 qualified / 4 verified refusals / 36 unresolved**, across the same 120 questions.

- **1021:** correct 0.715 is released via the sourced text calculator. Its initial collector still fails when a reviewer proposes incompatible canonical notation for an already-valid comma-grouped display (`NUMERIC_NOTATION_ALREADY_VALID` in offline replay). Do not describe that collector path as recovered.
- **1086:** 13,929 million is independently checked and executed, but proof admission fails at the evidence budget and finalization fails. Compact JSON serialization preserves all fields and witnesses; a separate follow-up run also abstains (71.00 s / nine requests). This is a result-publication boundary, not incorrect subtraction.


## Protected proof and page-view follow-up

The [sequential measurements](../artifacts/mmlongbench-v2/adaptive-result-reservation-20261020/REPORT.md)
recover publication for 1086 (13,929 million, nine requests) and retain a source-correct
380 answer in the preceding pair (8,367,277,000 rupees, six requests). A full-source
reservation stays inside the existing hard total; it does not bypass release checks.
The page-view handoff's 21-paragraph/three-ID regression was reproduced, tested and
corrected, with its failed paid run preserved. 382 retains two quizzes in both control
batches. Invalid notation suggestions preserve a valid original display without approving
unknown source bindings; numerically different interpretations remain rejected.

The result-publication defect is recovered for these targeted cases. Initial text
selection can still omit unit context, causing another selected image pass; this is
remaining acquisition efficiency work, not permission to infer units or skip review.
Historical distinct-question totals remain unchanged.


## Context and acquisition coverage follow-up

The [new report](../artifacts/mmlongbench-v2/adaptive-context-coverage-20261020/REPORT.md)
records original-page context, resumable authorized page reads and scoped search cursors.
1086 retains its correct amount in six requests; 1017 recovers 11,407 million in ten.
The successful 1017 follow-up uses the general reader/search/finalizer path, so it does
not certify the newly implemented narrow gap-query route. Its extra decision/repair
calls remain CALL-001. 730 and 662 remain open; neither is upgraded because a reviewer
approves cautious abstention. Current totals: **79 supported / 2 qualified / 4 verified
refusals / 35 unresolved**, across 120 distinct questions.


## Primary-blocker distribution of the 35 unresolved questions

This is a mutually exclusive grouping by each row's latest recorded principal blocker,
not a count of implementation bugs or a new current-code measurement. Several rows have
secondary issues. Known unsupported premises and disputed references still need source
adjudication; they are not automatically verified refusals.

| Primary blocker | Questions | Rows |
| --- | --- | --- |
| Source mismatch, missing-data or underspecified-request disposition | 13 | 207, 209, 222, 365, 367, 384, 508, 520, 521, 728, 730, 830, 1084 |
| Incomplete inventory or source-object coverage | 4 | 636, 662, 663, 831 |
| Visual condition or target-location acquisition | 4 | 393, 635, 638, 660 |
| Entity/period/unit binding and cross-source relationships | 5 | 510, 641, 1015, 1070, 1074 |
| Population, denominator and approximate headcount composition | 4 | 206, 216, 219, 225 |
| Question, counting-unit or formula adjudication | 4 | 214, 658, 732, 1075 |
| Unestablished source reading | 1 | 661 |
| **Total** | **35** | Each unresolved ledger row appears once. |
