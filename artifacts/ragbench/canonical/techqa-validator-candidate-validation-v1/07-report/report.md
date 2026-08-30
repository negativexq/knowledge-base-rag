# Validator Candidate Independent Validation V1

## Scope

This is an offline independent validation of the frozen cumulative
`NUMERIC_PLUS_VERSION_PLUS_IDENTIFIER_NEGATIVE` candidate. The corrected
HOLDOUT was not used for tuning or validation. No production code default was
changed and no provider call was made.

## Population accounting

The prior calibration has **8 historical event cases**, **15 synthetic
cases**, **23 total unique evaluable cases**, and category totals of **7 true
conflict / 11 equivalent-risk / 5 indeterminate**. The earlier `10 historical
query IDs` was a query-ID count, not an event-case count.

Independent validation population: **28 cases** — {'TRUE_CONFLICT': 8, 'FALSE_POSITIVE_RISK_EQUIVALENT': 10, 'INDETERMINATE': 5, 'SECURITY_REJECT': 5}.

## Results

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| True-conflict recall | 0.750 | 0.875 |
| False positives | 1 | 0 |
| Determinate precision | 0.857 | 1.000 |
| Forced-abstain proxy | 4 | 0 |
| Indeterminate unsafe acceptances | 1 | 3 |
| Security regressions | 0 | 0 |

## Gates

{
  "G1_security_regressions_zero": true,
  "G2_true_conflict_recall_candidate_gte_baseline": true,
  "G3_false_positive_candidate_lte_baseline": true,
  "G4_determinate_precision_candidate_gte_baseline": true,
  "G5_forced_abstain_proxy_candidate_lte_baseline": true,
  "G6_no_new_unsafe_equivalence_acceptance": false,
  "G7_no_unsafe_indeterminate_acceptance": false
}

Primary decision: **VALIDATOR_CANDIDATE_VALIDATION_FAILED**  
Secondary effect: **REGRESSION**  
Promotion eligible: **NO**

This result is eligibility only. It is not production promotion. Any future
promotion requires a separate review and must not reuse the consumed HOLDOUT
as confirmation.
