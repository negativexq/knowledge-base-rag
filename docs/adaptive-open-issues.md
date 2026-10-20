# Open adaptive workflow issues

Updated 20 October 2026. This register separates confirmed code defects, semantic
acceptance failures, partial fixes and source/metric adjudication. The detailed
[code-and-trace audit](adaptive-issue-audit.md) contains source anchors and offline
replays. Prior run reports retain unsuccessful attempts.

There are **46 unresolved question/workflow outcomes** in the
[120-row ledger](adaptive-solved-questions.md). That is not 46 independently proven
code bugs. One row can exercise multiple families; counts below are not additive.
The shared matcher scores and strict source/workflow audit remain separate.

## Current priorities

| Issue | Priority / status | Confirmed evidence and boundary | Next correction |
| --- | --- | --- | --- |
| REPAIR-001: exact text equality in input repair | P0; live + offline confirmed | 366, 1016 and 1070 raise `REPAIR_CHANGED_UNTARGETED_STRUCTURE`. Equivalent interpretation text triggers rejection; 1070 expressions have identical ASTs. | Application-owned operation fields and operand-only patch contract. Preserve protections against genuinely changed operations. |
| REPAIR-002: text locators inside image repair | P0; live + offline confirmed | 1072 fresh pages [40,39,39] become [40,null,null] when untargeted old text operands are restored; then `QUANTITY_ITEM_PAGE_INVALID`. | Preserve per-operand provenance independently from current observation modality; do not invalidate prior evidence with a record-wide image requirement. |
| PAGE-001: required visual page dropped as context | P0; live + offline confirmed | 641 requests pages 7/8 but comparison source is a context-role unit; input-page filtering sends only page 8 to the collector. | Validate visual evidence roles; retain/promote required authorized pages or return a typed mismatch, within existing budgets. |
| FLOW-001 / ROUTE-001: universal quantity fallback | P0; code confirmed; semantic failures observed | Failed fast text answers also enter numeric collection; 508/511/517/520 show incompatible result types. A created unsuccessful quantity draft terminates the general research path. | Dispatch by required evidence/result type and return typed compatibility/missing-evidence outcomes to the bounded application policy. |
| INV-001: page or subset mistaken for whole inventory | P0; source-confirmed wrong release | 476 publishes 5 instead of 9 USB functions; 381 publishes 6 instead of 7 course quizzes. A footer/current page is not inventory closure. | Separate item observations from source-grounded inventory closure; accumulate coverage across bounded windows. |
| MEMBER-001 / SCOPE-001: group membership and target constraints | P0; source-confirmed wrong/incomplete release | 399 counts neighboring-category names; 660 ignores port range; 638 counts top figure for bottom request; 510 lacks Oxford binding; 831 omits available tasks. | Validate sibling-heading membership, requested object/location/conditions and answer completeness separately from transcription. |
| REPAIR-003: wrong freshness requirement | P1; exact guard confirmed | 214/380/637 raise `REPAIR_REUSED_INSUFFICIENT_SOURCE`; all scope diagnostics become fresh-source research even for a unit transform or page relationship. | Classify missing source, interpretation, provenance, presentation and actual mismatch before choosing repair. Retain freshness for real missing-source searches. |
| PROV-001: header/entity/period/page binding | P1; observed + code boundary confirmed | 1070 issuer context; 366 period context; 637 physical/printed page; 1014/1086 recover missing unit context. Immutable document identity alone is not semantic issuer proof. | Carry verified title/table/period/unit/location links as typed evidence available to each independent check. |
| NUM-001: numeric displays and absence | Partially fixed; remaining sensitivity | Original crash/checkpoint cases 471/1026/1025/388 recovered. Grouped display with incompatible notation still fails in 1016/1021/1074. | Retain display/canonical separation and checkpoint-before-execution; preflight notation compatibility without guessing locale or treating absence as zero. |
| UNITS-001: arithmetic output transformation | P1; observed + code boundary confirmed | 380 subtracts lac-denominated inputs but labels result rupees; arithmetic normalization does not apply scalar-read output transforms. | Typed input/output units and explicit application-checked transforms; do not silently change formulas or signs. |
| CALC-001: named function becomes missing operand | P1; offline confirmed latent failure | 366 would hit `QUANTITY_UNKNOWN_OPERAND` on `abs` after merge recovery. Generic abs/min/max/mean reproduce it in quantity execution. | Declare operator capabilities; use bounded supported deterministic operators and report unsupported function distinctly. No arbitrary Python execution. |
| COVER-001: incomplete source-object coverage | P1; observed, not all cases arithmetic bugs | 730/728 lack Boeing object closure; 662/663 lack guide-wide inventory; 1017 misses a lease note; 641 also has PAGE-001. | Accumulated coverage and typed missing roles. Search exhaustion is not source absence; do not raise page limits before correcting handoff. |
| COMPOSE-001: denominator/population/plan composition | P1; observed; some reference assumptions disputed | 206/225/219 require approximate survey headcounts; 216 cannot borrow Dem/Lean Dem base for Democrats; 1015 needs a stated EBITDA definition. | Keep population, denominator, period, metric definition and approximation status with observations. |
| STOP-001: mismatch, absence and no progress conflated | P1; observed | 207/222/365/367/830/1084 repeat searches or stop without verified terminal receipts; 384 ends in ModelRetry. | Grounded source-scoped mismatch/absence receipts, distinct from partial search and execution error; terminate deterministically when justified. |
| OBS-001: safe domain errors missing from spans | P1; confirmed | Spans retain exception class only, but local `ResearchState.needs` retains exact guard codes; previous audits overlooked this. | Allowlisted domain codes in spans/typed failures; preserve the privacy boundary against arbitrary messages/content. |
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
