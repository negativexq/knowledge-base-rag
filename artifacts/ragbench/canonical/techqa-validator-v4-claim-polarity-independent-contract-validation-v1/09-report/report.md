# VALIDATOR V4 CLAIM POLARITY INDEPENDENT CONTRACT VALIDATION V1

Decision: **VALIDATOR_V4_CLAIM_POLARITY_INDEPENDENT_CONTRACT_VALIDATION_FAILED**

This is an independently-authored occurrence-level validator contract validation, not a new TechQA HOLDOUT. The corrected HOLDOUT remains consumed and was not used.

## Accounting
- 50 cases
- 100 critical-value occurrences
- Primary unit: CRITICAL_VALUE_OCCURRENCE
- Case-level and occurrence-level denominators are documented separately.

## Results
- V3: {'occurrences': 100, 'validate_total': 66, 'validate_kept': 66, 'real_assertion_incorrectly_skipped': 0, 'ambiguous_total': 8, 'ambiguous_conservatively_validated': 8, 'ambiguous_incorrectly_skipped': 0, 'rejected_premise_total': 26, 'correct_rejected_premise_skips': 0, 'rejected_premise_not_skipped': 26, 'corrective_recovery_rate': 0.0, 'unsafe_skip_rate': 0.0, 'correct_total': 74, 'outcome_behavior_distribution': {'VALIDATE': 100}}
- V4: {'occurrences': 100, 'validate_total': 66, 'validate_kept': 66, 'real_assertion_incorrectly_skipped': 0, 'ambiguous_total': 8, 'ambiguous_conservatively_validated': 8, 'ambiguous_incorrectly_skipped': 0, 'rejected_premise_total': 26, 'correct_rejected_premise_skips': 14, 'rejected_premise_not_skipped': 12, 'corrective_recovery_rate': 0.5385, 'unsafe_skip_rate': 0.0, 'correct_total': 88, 'outcome_behavior_distribution': {'VALIDATE': 86, 'SKIP': 14}}

## Gates
- G1_REAL_ASSERTION_SAFETY: PASS
- G2_AMBIGUOUS_SAFETY: PASS
- G3_UNSUPPORTED_POSITIVE_CLAIM_SAFETY: PASS
- G4_CORRECTIVE_IMPROVEMENT: PASS
- G5_CORRECTIVE_RECOVERY: PASS
- G6_V3_REGRESSION_PROTECTION: PASS
- G7_QUERY_ECHO_SAFETY: PASS
- G8_NEGATION_SAFETY: PASS
- G9_MULTI_OCCURRENCE_SAFETY: FAIL
- G10_SECURITY: PASS

## Blocking finding
G9 failed on C50: V4 did not distinguish the two same-text `30` occurrences because their token kinds were NUMBER and DURATION. This is a contract coverage failure, not an unsafe skip.

No V4 patch, relabeling, provider call, HOLDOUT use, or production change occurred. V4 remains immutable and closed.
