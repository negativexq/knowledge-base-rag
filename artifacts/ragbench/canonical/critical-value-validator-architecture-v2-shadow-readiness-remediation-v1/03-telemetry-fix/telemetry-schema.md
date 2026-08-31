# Bounded telemetry contract

The aggregate request span now emits these Architecture V2 shadow attributes:

- `validator.shadow.architecture_v2.architecture`
- `validator.shadow.architecture_v2.executed`
- `validator.shadow.architecture_v2.occurrence_count`
- `validator.shadow.architecture_v2.validate_count`
- `validator.shadow.architecture_v2.skip_rejected_premise_count`
- `validator.shadow.architecture_v2.ambiguous_count`
- `validator.shadow.architecture_v2.outcome`
- `validator.shadow.architecture_v2.disagreement`
- `validator.shadow.architecture_v2.duration_ms`
- `validator.shadow.architecture_v2_error`

All values are bounded strings, booleans, integers, or floats. No occurrence
IDs, spans, literals, answer text, query text, evidence, prompts, or exception
strings are promoted. The detailed ledger remains local forensic data only.
