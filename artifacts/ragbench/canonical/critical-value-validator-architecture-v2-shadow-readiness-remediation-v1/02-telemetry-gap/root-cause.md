# Telemetry gap root cause

Before remediation, `_architecture_v2_result()` produced the Architecture ID,
occurrence count, role counts, duration, and forensic ledger. In the baseline
or V3 path, `audit_critical_value()` retained only the shadow outcome,
disagreement, error flag, and forensic payload. `validate_support_unit_answer()`
then aggregated only the generic authoritative fields; the shadow counts were
therefore absent and generic count fields stayed at zero. Finally,
`_record_validator_telemetry()` emitted the shadow outcome/disagreement/error
but had no shadow ID, executed flag, role counters, or shadow duration fields.

The loss was observability-field propagation, not occurrence extraction, role
classification, or V3 comparison semantics. The fix copies bounded fields from
the successful shadow result into the request-local result and aggregate, then
promotes those fields to the request span. For a shadow exception the executed
flag remains false; a successful zero-occurrence execution is true with zero
counters.
