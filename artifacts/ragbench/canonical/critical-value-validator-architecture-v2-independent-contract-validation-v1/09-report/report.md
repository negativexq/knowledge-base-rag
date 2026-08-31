# CRITICAL VALUE VALIDATOR ARCHITECTURE V2 — INDEPENDENT CONTRACT VALIDATION V1

This is an independently authored occurrence-level validator contract
validation. It is not a new TechQA HOLDOUT and does not reopen the consumed
BGE HOLDOUT verdict.

## Frozen execution

- 98 cases and 187 critical-value occurrences.
- 131 `VALIDATE`, 50 `SKIP_REJECTED_PREMISE`, and 6
  `AMBIGUOUS_KEEP_VALIDATING` labels.
- One canonical Architecture V2 execution; no provider, retrieval, BGE, or
  HOLDOUT calls.
- Extraction/identity: 187 expected and observed, with zero missing,
  spurious, nested, boundary, sign, version, duration, identifier, or ID
  collision errors.
- V3 outcome equivalence: zero mismatches.

## Role result

Architecture V2 correctly skipped 43 of 50 rejected-premise occurrences and
missed 7. It incorrectly skipped one occurrence labelled `VALIDATE`:
`CORR13.O2`, in the frozen case `The signed result is -312 rather than -311.`
The observed roles were `-312=VALIDATE` and `-311=SKIP`; the frozen expected
labels were the reverse. This is a hard real-assertion safety failure under the
frozen adjudication and cannot be relabelled after execution. The evidence
supports classifying the blocker as `TEST_ANNOTATION_DEFECT`, pending a new
population review; the canonical result nevertheless remains FAIL.

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_INDEPENDENT_CONTRACT_VALIDATION_FAILED`

The safety gate is not waived by the 86.0% corrective recovery rate. No
Architecture V2 source, V3 semantics, production selector, provider, or
historical artifact was changed. Future work must first author and freeze a
corrected independent population under a new validation run; this candidate is
not promoted.

## Gate disposition

- Architecture gates A1-A10: PASS.
- Safety gates S1, S3-S8: PASS.
- S2 real-assertion safety: FAIL under the frozen adjudication because
  `CORR13.O2` is labelled `VALIDATE` but the observed occurrence-local role is
  the rejected premise `-311`.
- Identity gates: extraction and global identity checks are zero-error; the
  single observed sibling mismatch is the same frozen `CORR13` label defect,
  not a span collision or value-level collapse.
- Corrective recovery: 43/50 = 86.0%, meeting the preregistered Q1 threshold
  of 80%.

## Full deterministic suite

The architecture-specific deterministic suite passed. The full current run
completed with `1230 passed, 1 skipped, 6 deselected, 5 warnings`; there were
no current Qdrant errors. The three Qdrant fixture errors from the prior full
run remain recorded in `08-fixture-triage/qdrant-fixture-triage.md` as
environment-dependent fixture failures, with zero task-caused regressions.

## Scope and provenance

The primary unit is a `CRITICAL_VALUE_OCCURRENCE`; case counts are secondary.
The population and adjudications were frozen before execution, and the
canonical execution count is one. T4 boolean normalization, T6 unit
equivalence, T10 version semantics, INDETERMINATE policy, BGE verdict, and the
consumed corrected HOLDOUT were not changed or reopened.
