# Adapter contract

`app.evaluation.critical_validator_runtime.audit_critical_value` is the
small production adapter. It retains the existing result dictionary consumed
by support-ID validation and adds bounded Architecture V2 metadata.

When `architecture_v2` is authoritative, the adapter invokes the exact frozen
Architecture V2 entry point. Its dataflow is one canonical extraction,
immutable occurrence ledger, occurrence-local role classification, structured
VALIDATE filtering, and delegation to the frozen V3 comparison adapter. No
raw-text masking, normalized-value role mask, role-layer rediscovery, or
post-role re-extraction is used.

`baseline` and `v3` retain their existing authoritative behavior. An optional
Architecture V2 shadow receives the same claim/support inputs, but its result
is diagnostic only. The adapter never mutates the answer, support IDs,
evidence, citations, or forced-abstain state.

An authoritative validator exception is converted by the support-unit
validation boundary into `CRITICAL_VALIDATOR_INFRASTRUCTURE_FAILURE` and a
fail-closed application abstention. It is not silently changed to another
validator.
