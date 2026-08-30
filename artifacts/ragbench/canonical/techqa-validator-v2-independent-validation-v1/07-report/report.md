# Validator V2 Independent Validation V1

## Scope

DEBUG calibration and independent validation are separate phases. This run
uses a new 48-case contract population, frozen before execution, and does not
reuse corrected HOLDOUT, V1 validation cases, or V2 DEBUG fixtures verbatim.
No production default or BGE decision changed.

## Results

| Metric | Baseline | Frozen V2 |
| --- | ---: | ---: |
| True-conflict recall | 9/12 | 11/12 |
| False positives | 9 | 0 |
| Determinate precision | 0.500 | 1.000 |
| Unsafe indeterminate accepts | 0 | 0 |
| Forced-abstain proxy | 9 | 0 |
| Security regressions | 0 | 0 |

## Frozen gates

{
  "G1_security": true,
  "G2_true_conflict_recall": true,
  "G3_false_positives": true,
  "G4_determinate_precision": true,
  "G5_indeterminate_safety": true,
  "G6_unsafe_magnitude_collapse": true,
  "G7_sign_identifier_safety": true,
  "G8_version_specificity": false,
  "G9_forced_abstain_proxy": true
}

Primary decision: **VALIDATOR_V2_INDEPENDENT_VALIDATION_FAILED**  
Secondary effect: **REGRESSION**  
Promotion eligible: **NO**

The candidate is eligible for a separate promotion review only. It is not
production promotion. Any failure in a later review requires a new candidate
version rather than patching this freeze.
