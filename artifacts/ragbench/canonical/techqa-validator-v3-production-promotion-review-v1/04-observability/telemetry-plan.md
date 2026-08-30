# Production telemetry prerequisite

Existing tracing uses OpenTelemetry spans and bounded metadata, but it does
not currently provide a validator-specific counter set sufficient for a
baseline comparison. Therefore `CANARY_READY = NO` until the following is
implemented and observed in shadow mode.

Required counters/attributes:

- `validator.invocations`
- `validator.pass`
- `validator.reject`
- `validator.indeterminate`
- `validator.reason_class`
- `validator.critical_value_type`
- `validator.locale_ambiguity`
- `validator.version_ambiguity`
- `validator.version_specificity_reject`
- `validator.identifier_reject`
- `validator.forced_abstain`
- `validator.processing_ms`
- `validator.version` (`baseline` or `v3`)

Shadow comparison should record only bounded outcomes such as `SAME`,
`BASELINE_REJECT_V3_PASS`, `BASELINE_PASS_V3_REJECT`,
`BASELINE_IND_V3_PASS`, or `BASELINE_PASS_V3_IND`. It must not record raw
queries, document contents, support text, secrets, or tenant-sensitive
evidence. Configuration fingerprints should expose the selected validator
version without exposing user data.

The production integration task should instrument the existing validator
span/report path rather than introduce a parallel tracing framework.
