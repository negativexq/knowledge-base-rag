# Failure injection

The deterministic test-only shadow exception path was exercised. The baseline
authoritative result survived, the visible result remained unchanged, and the
bounded `shadow_error` path was observed. The deterministic Architecture V2
authoritative exception contract also remained fail-closed with
`CRITICAL_VALIDATOR_INFRASTRUCTURE_FAILURE`.

No user-exposed failure hook was added and no primary browser case used an
injected exception.
