# Validator V3 independent validation

DEBUG CALIBRATION != INDEPENDENT VALIDATION.

The frozen candidate `VALIDATOR_CANDIDATE_V3_44dd8bdd2c0b` was evaluated once against a fresh
60-case population. Corrected HOLDOUT was not used, no provider was called,
and production behavior was not changed.

## Results

| Metric | Baseline | V3 |
| --- | ---: | ---: |
| True-conflict recall | 17/18 | 18/18 |
| False positives | 11 | 2 |
| Determinate precision | 60.71% | 90.00% |
| Unsafe indeterminate accepts | 0 | 0 |
| Forced-abstain proxy | 11 | 2 |
| Version specificity errors | 8 | 0 |
| Security regressions | 0 | 0 |

## Decision

Primary decision: **VALIDATOR_V3_INDEPENDENT_VALIDATION_PASSED**

Secondary effect: **CLEAR_IMPROVEMENT**

Passing validation authorizes a separate promotion review only; it does not
deploy the candidate.
