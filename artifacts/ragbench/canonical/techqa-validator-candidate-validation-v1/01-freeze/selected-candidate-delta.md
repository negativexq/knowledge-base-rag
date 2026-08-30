# Selected candidate delta

"
        "Selected path: `IDENTIFIER_NEGATIVE`, evaluated cumulatively as "
        "`NUMERIC + VERSION + IDENTIFIER_NEGATIVE`.

"
        "Baseline is `app.evaluation.critical_values.claim_local_critical_value_audit`. "
        "The candidate is an offline experimental path in "
        "`scripts/run_techqa_validator_calibration_debug_v1.py`; no application "
        "default is changed.

"
        "Included behavior:

"
        "- Numeric: grouped-integer equivalence for unambiguous `1,000`/`1000`-style "
        "forms, including technical dotted grouping when the context is not "
        "version-like; ordinary decimals remain distinct.
"
        "- Version: optional formatting normalization and explicitly marked "
        "`family`/`or later` compatibility; exact claims remain exact.
"
        "- Identifier/negative: compact CVE/SQLCODE formatting comparison plus "
        "explicit negative-claim handling; no global evidence search or semantic "
        "entailment.
"
        "- Support segmentation candidate is not included.

"
        "This is the exact current experimental code path, frozen by source hashes "
        "before independent validation. Any future correction requires a new "
        "candidate version.
