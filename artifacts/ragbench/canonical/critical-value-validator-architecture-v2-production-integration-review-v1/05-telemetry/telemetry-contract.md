# Telemetry contract

Current OTel instrumentation already emits bounded validator version,
outcome, reason class, counts, durations, forced-abstain, and V3 shadow
metadata (`app/llm/structured_output.py:870-936`). The local forensic capture
is separate (`app/evaluation/forensic_capture.py:107-155`) and is explicitly
opt-in.

## Future bounded fields

- `critical_validator.architecture`
- `critical_validator.outcome`
- `critical_validator.reason_class`
- `critical_validator.duration_ms`
- `critical_validator.occurrence_count`
- `critical_validator.validate_count`
- `critical_validator.skip_rejected_premise_count`
- `critical_validator.ambiguous_count`
- `critical_validator.forced_abstain`
- `critical_validator.shadow_enabled`
- `critical_validator.shadow_outcome`
- `critical_validator.shadow_disagreement`
- `critical_validator.shadow_error`

All values must be enums, booleans, bounded counts, or durations. Request-
specific occurrence IDs remain local forensic data only.

OTel must never receive raw query, answer, claim, evidence, critical literal,
support text, prompt, or model output. Existing forensic raw text remains
disabled by default and must not be copied into OTel.
