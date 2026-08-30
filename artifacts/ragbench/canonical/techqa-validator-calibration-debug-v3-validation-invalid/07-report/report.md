# Validator Calibration DEBUG V3

V2 was verified as frozen and failed independent validation only on version
specificity (`IV2-TC-10`). V3 adds a claim-specificity guard and uses a fresh
40-case DEBUG population. No HOLDOUT or provider was used.

| Metric | Baseline | V2 reproduction | V3 |
| --- | ---: | ---: | ---: |
| True-conflict recall | 0.750 | 0.917 | 0.917 |
| False positives | 7 | 1 | 1 |
| Version specificity errors | 8 | 6 | 2 |
| Unsafe indeterminate accepts | 0 | 0 | 0 |
| Forced-abstain proxy | 7 | 1 | 1 |
| Security regressions | 0 | 0 | 0 |

## Gates

{
  "G1_security": true,
  "G2_true_conflict_recall": true,
  "G3_false_positives": true,
  "G4_version_specificity": true,
  "G5_exact_version_safety": false,
  "G6_ambiguous_version_safety": true,
  "G7_v2_regression_protection": true,
  "G8_forced_abstain": true
}

Primary DEBUG decision: **NO_VALIDATOR_V3_CANDIDATE_SELECTED**  
Secondary effect: **REGRESSION**

V3 is not production promotion. If selected, it requires a separate
independent validation population. A later correction requires V4 rather than
patching this candidate.
