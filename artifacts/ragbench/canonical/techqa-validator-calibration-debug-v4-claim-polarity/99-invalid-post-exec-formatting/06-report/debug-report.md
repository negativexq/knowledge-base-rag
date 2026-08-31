# V4 DEBUG observed comparison

Decision: **VALIDATOR_V4_CLAIM_POLARITY_DEBUG_CANDIDATE_SELECTED**
Frozen DEV population: 70 cases.
The preliminary arm was invalidated after source mutation and preserved under `99-invalid-pre-freeze-run/`; it is excluded from this decision.

## V3
{
  "cases": 70,
  "true_conflict_detected": 25,
  "true_conflict_total": 27,
  "true_conflict_recall": 0.9259,
  "corrective_answer_allowed": 2,
  "corrective_total": 13,
  "corrective_false_conflict_count": 11,
  "unsupported_positive_claim_allowed_count": 0,
  "ambiguous_polarity_preserved": 2,
  "ambiguous_polarity_total": 2,
  "false_positive_count": 16,
  "false_reject_count": 2,
  "forced_abstain_proxy": 11,
  "security_regressions": 0,
  "forced_abstain_count": 45,
  "type_metrics": {
    "DATE": {
      "correct": 1,
      "total": 1,
      "rate": 1.0
    },
    "DURATION": {
      "correct": 12,
      "total": 18,
      "rate": 0.6667
    },
    "IDENTIFIER": {
      "correct": 8,
      "total": 9,
      "rate": 0.8889
    },
    "NUMBER": {
      "correct": 16,
      "total": 24,
      "rate": 0.6667
    },
    "PERCENTAGE": {
      "correct": 3,
      "total": 4,
      "rate": 0.75
    },
    "VERSION": {
      "correct": 12,
      "total": 14,
      "rate": 0.8571
    }
  },
  "polarity_metrics": {
    "COMPARISON_VALUE": {
      "correct": 5,
      "total": 5,
      "rate": 1.0
    },
    "CORRECTIVE_REFERENCE": {
      "correct": 0,
      "total": 7,
      "rate": 0.0
    },
    "NEGATED_ASSERTION": {
      "correct": 7,
      "total": 9,
      "rate": 0.7778
    },
    "POSITIVE_ASSERTION": {
      "correct": 26,
      "total": 26,
      "rate": 1.0
    },
    "QUOTED_VALUE": {
      "correct": 4,
      "total": 4,
      "rate": 1.0
    },
    "REJECTED_PREMISE": {
      "correct": 2,
      "total": 11,
      "rate": 0.1818
    },
    "UNKNOWN": {
      "correct": 8,
      "total": 8,
      "rate": 1.0
    }
  },
  "outcome_distribution": {
    "PASS": 25,
    "REJECT": 40,
    "INDETERMINATE": 5
  }
}

## V4
{
  "cases": 70,
  "true_conflict_detected": 25,
  "true_conflict_total": 27,
  "true_conflict_recall": 0.9259,
  "corrective_answer_allowed": 12,
  "corrective_total": 13,
  "corrective_false_conflict_count": 1,
  "unsupported_positive_claim_allowed_count": 0,
  "ambiguous_polarity_preserved": 2,
  "ambiguous_polarity_total": 2,
  "false_positive_count": 2,
  "false_reject_count": 2,
  "forced_abstain_proxy": 1,
  "security_regressions": 0,
  "forced_abstain_count": 31,
  "type_metrics": {
    "DATE": {
      "correct": 1,
      "total": 1,
      "rate": 1.0
    },
    "DURATION": {
      "correct": 17,
      "total": 18,
      "rate": 0.9444
    },
    "IDENTIFIER": {
      "correct": 8,
      "total": 9,
      "rate": 0.8889
    },
    "NUMBER": {
      "correct": 23,
      "total": 24,
      "rate": 0.9583
    },
    "PERCENTAGE": {
      "correct": 4,
      "total": 4,
      "rate": 1.0
    },
    "VERSION": {
      "correct": 13,
      "total": 14,
      "rate": 0.9286
    }
  },
  "polarity_metrics": {
    "COMPARISON_VALUE": {
      "correct": 5,
      "total": 5,
      "rate": 1.0
    },
    "CORRECTIVE_REFERENCE": {
      "correct": 6,
      "total": 7,
      "rate": 0.8571
    },
    "NEGATED_ASSERTION": {
      "correct": 7,
      "total": 9,
      "rate": 0.7778
    },
    "POSITIVE_ASSERTION": {
      "correct": 26,
      "total": 26,
      "rate": 1.0
    },
    "QUOTED_VALUE": {
      "correct": 4,
      "total": 4,
      "rate": 1.0
    },
    "REJECTED_PREMISE": {
      "correct": 10,
      "total": 11,
      "rate": 0.9091
    },
    "UNKNOWN": {
      "correct": 8,
      "total": 8,
      "rate": 1.0
    }
  },
  "outcome_distribution": {
    "PASS": 39,
    "REJECT": 26,
    "INDETERMINATE": 5
  }
}

## Gates
- G1_SECURITY: PASS
- G2_TRUE_CONFLICT_SAFETY: PASS
- G3_UNSUPPORTED_POSITIVE_CLAIM_SAFETY: PASS
- G4_CORRECTIVE_AVAILABILITY: PASS
- G5_POLARITY_SAFETY: PASS
- G6_AMBIGUOUS_POLARITY: PASS
- G7_V3_REGRESSION_PROTECTION: PASS
- G8_FORCED_ABSTAIN: PASS
- G9_T3_T5_REGRESSION_ANCHORS: PASS

## Changed cases
- C01: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C03: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C05: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C06: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C07: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C08: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C09: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C11: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C12: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- C13: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- M05: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- M07: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- M08: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)
- Q04: REJECT -> PASS (FIXED_CORRECTIVE_FALSE_CONFLICT; POLARITY_GUARD_EXPECTED)

V3 remains frozen. V4 is DEBUG-only. No independent validation was run. T4 BOOLEAN, T6 unit equivalence, and T10 version semantics were not changed.
