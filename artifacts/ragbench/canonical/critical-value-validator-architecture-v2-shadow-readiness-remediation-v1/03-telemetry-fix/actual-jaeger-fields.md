# Actual aggregate span fields

The final local smoke trace `eda99f300e83b054fb01eb032a1bb466` contained the
following bounded Architecture V2 shadow fields:

```text
validator.shadow.architecture_v2.architecture = CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1
validator.shadow.architecture_v2.executed = true
validator.shadow.architecture_v2.occurrence_count = 1
validator.shadow.architecture_v2.validate_count = 1
validator.shadow.architecture_v2.skip_rejected_premise_count = 0
validator.shadow.architecture_v2.ambiguous_count = 0
validator.shadow.architecture_v2.outcome = PASS
validator.shadow.architecture_v2.disagreement = SAME
validator.shadow.architecture_v2.duration_ms = 5.253
validator.shadow.architecture_v2_error = false
```

The values were read from the actual Jaeger API response. No raw request or
response content was retained.
