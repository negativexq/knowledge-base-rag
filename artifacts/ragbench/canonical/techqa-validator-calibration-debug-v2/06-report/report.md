# Validator Calibration DEBUG V2

## Scope

V1 was verified as an immutable, closed candidate and was not patched. This
provider-free DEBUG calibration uses 30 newly authored deterministic contract
fixtures; it does not read or tune on corrected HOLDOUT or reuse the V1
independent-validation population.

## Results

| Run | Recall | FP | Unsafe IND | Precision | Forced proxy | Security |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.750 | 4 | 0 | 0.600 | 6 | 0 |
| V1 reproduction | 0.875 | 2 | 3 | 0.778 | 2 | 0 |
| V2 locale guard | 1.000 | 0 | 0 | 1.000 | 0 | 0 |

V2 unsafe-magnitude acceptance cases: `[]`. Protected-contract
regressions: `[]`.

## Decision

{
  "G1_security": true,
  "G2_true_conflict_recall": true,
  "G3_false_positives": true,
  "G4_indeterminate_safety": true,
  "G5_v1_regression_protection": true,
  "G6_forced_abstain": true,
  "G7_unsafe_magnitude_collapse": true
}

Primary DEBUG decision: **VALIDATOR_V2_DEBUG_CANDIDATE_SELECTED**
Secondary effect: **CLEAR_IMPROVEMENT**

The selected V2 path is not production promotion. It requires a separate
independent validation population before any default change. Ambiguity is
handled conservatively as `INDETERMINATE`; no locale guesser or semantic
entailment was added.
