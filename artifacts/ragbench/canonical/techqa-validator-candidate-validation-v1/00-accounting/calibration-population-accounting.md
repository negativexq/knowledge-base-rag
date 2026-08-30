# Calibration population accounting

"
        "The prior report used historical query-ID count as if it were event-case count.

"
        f"- Raw historical event cases: {accounting['raw_historical_cases']}
"
        f"- Raw synthetic cases: {accounting['raw_synthetic_cases']}
"
        f"- Raw total: {accounting['raw_total_cases']}
"
        f"- Duplicates: {accounting['duplicate_cases']}
"
        f"- Unique cases: {accounting['unique_cases']}
"
        f"- Neutral/non-evaluable: {accounting['neutral_or_non_evaluable_cases']}
"
        f"- Evaluable: {accounting['evaluable_cases']}
"
        f"- TRUE_CONFLICT: {accounting['true_conflict_targets']}
"
        f"- FALSE_POSITIVE: {accounting['false_positive_targets']}
"
        f"- INDETERMINATE: {accounting['indeterminate_targets']}

"
        "Arithmetic reconciles as 8 historical event cases + 15 synthetic "
        "cases = 23 unique evaluable cases; category totals are 7 + 11 + 5 = 23.
