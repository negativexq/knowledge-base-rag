# Open adaptive workflow issues

Updated 20 October 2026. This register separates confirmed code defects, semantic
acceptance failures, partial fixes and source/metric adjudication. The detailed
[code-and-trace audit](adaptive-issue-audit.md) contains source anchors and offline
replays. Prior run reports retain unsuccessful attempts.

There are **41 unresolved question/workflow outcomes** in the
[120-row ledger](adaptive-solved-questions.md). One additional question has a qualified interpreted calculation. That is not 41 independently proven
code bugs. One row can exercise multiple families; counts below are not additive.
The shared matcher scores and strict source/workflow audit remain separate.

## Current priorities

| Issue | Priority / status | Confirmed evidence and boundary | Next correction |
| --- | --- | --- | --- |
| REPAIR-001: exact text equality in input repair | P0; implemented; targeted checks pass; end-to-end blockers remain | 366, 1016 and 1070 raise `REPAIR_CHANGED_UNTARGETED_STRUCTURE`. Equivalent interpretation text triggers rejection; 1070 expressions have identical ASTs. | Application-owned operation fields and operand-only patch contract. Preserve protections against genuinely changed operations. |
| REPAIR-002: text locators inside image repair | P0; implemented; targeted checks pass; end-to-end blockers remain | 1072 fresh pages [40,39,39] become [40,null,null] when untargeted old text operands are restored; then `QUANTITY_ITEM_PAGE_INVALID`. | Preserve per-operand provenance independently from current observation modality; do not invalidate prior evidence with a record-wide image requirement. |
| PAGE-001: required visual page dropped as context | Handoff fixed; row 641 relationship review remains open | Earlier 641 lost the comparison page through role filtering. The follow-up retains both required pages and delivers definition evidence E1.S60; independent review still rejects the evaluation-population join. | Preserve required-page authority and context budget. Investigate the remaining semantic relationship under COMPOSE-001 rather than repeating the page-filter fix. |
| FLOW-001 / ROUTE-001: universal quantity fallback | P0; code confirmed; semantic failures observed | Failed fast text answers also enter numeric collection; 508/511/517/520 show incompatible result types. A created unsuccessful quantity draft terminates the general research path. | Dispatch by required evidence/result type and return typed compatibility/missing-evidence outcomes to the bounded application policy. |
| INV-001: page or subset mistaken for whole inventory | P0; targeted counts recovered; broader accumulation open | Prior 476/381 releases were 5/6 instead of 9/7. The follow-up now publishes 9/7 from the original source. Optional parser metadata is not a release gate. | Keep independent coverage review and source-scoped document-window dispatch. Accumulate independently checked partial inventories when no three-page window suffices. |
| MEMBER-001 / SCOPE-001: group membership and target constraints | P0; targeted group count recovered; semantic cases remain | 399 now releases 4+3=7 from the correct groups. Prior 660/638/510 unsafe answers are withheld; their final dispositions remain unresolved. 831 completeness still needs a targeted check. | Retain quoted question restrictions, independently checked inventories and original native source witnesses. Validate remaining location/relationship/list cases without treating missing parser text as a factual contradiction. |
| REPAIR-003: wrong freshness requirement | P1; exact guard confirmed | 214/380/637 raise `REPAIR_REUSED_INSUFFICIENT_SOURCE`; all scope diagnostics become fresh-source research even for a unit transform or page relationship. | Classify missing source, interpretation, provenance, presentation and actual mismatch before choosing repair. Retain freshness for real missing-source searches. |
| PROV-001: header/entity/period/page binding | P1; observed + code boundary confirmed | 1070 issuer context; 366 period context; 637 physical/printed page; 1014/1086 recover missing unit context. Immutable document identity alone is not semantic issuer proof. | Carry verified title/table/period/unit/location links as typed evidence available to each independent check. |
| NUM-001: numeric displays and absence | Partially fixed; remaining sensitivity | Original crash/checkpoint cases 471/1026/1025/388 recovered. The numeric-authority follow-up recovers 1016/1021; 1074 remains unresolved and has not been remeasured after that fix. | Retain display/canonical separation and checkpoint-before-execution; preflight notation compatibility without guessing locale or treating absence as zero. |
| UNITS-001: arithmetic output transformation | P1; observed + code boundary confirmed | 380 subtracts lac-denominated inputs but labels result rupees; arithmetic normalization does not apply scalar-read output transforms. | Typed input/output units and explicit application-checked transforms; do not silently change formulas or signs. |
| CALC-001: named function becomes missing operand | P1; offline confirmed latent failure | 366 would hit `QUANTITY_UNKNOWN_OPERAND` on `abs` after merge recovery. Generic abs/min/max/mean reproduce it in quantity execution. | Declare operator capabilities; use bounded supported deterministic operators and report unsupported function distinctly. No arbitrary Python execution. |
| COVER-001: incomplete source-object coverage | P1; observed, not all cases arithmetic bugs | 730/728 lack Boeing object closure; 662/663 lack guide-wide inventory; 1017 misses a lease note. Row 641 now retains both pages but its evaluation-population join remains unresolved. | Accumulated coverage and typed missing roles. Search exhaustion is not source absence; do not raise page limits before correcting handoff. |
| COMPOSE-001: denominator/population/plan composition | P1; observed; some reference assumptions disputed | 206/225/219 require approximate survey headcounts; 216 cannot borrow Dem/Lean Dem base for Democrats; 1015 needs a stated EBITDA definition. | Keep population, denominator, period, metric definition and approximation status with observations. |
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
