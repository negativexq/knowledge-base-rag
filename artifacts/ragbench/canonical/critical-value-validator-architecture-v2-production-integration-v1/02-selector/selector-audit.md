# Selector audit

The server-owned selector is extended to `baseline | v3 | architecture_v2`
through `Settings.critical_validator_version`. Its default remains
`baseline`. Pydantic configuration validation and the runtime adapter both
reject unknown values; there is no silent fallback for an invalid selector.

The selector is not present in `ChatRequest`, headers, cookies, query
parameters, frontend state, or model output. It is passed from server wiring
to the existing validator boundary only.

`CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED` is a separate server-owned
boolean, default `false`. V3 shadow and Architecture V2 shadow are allowed
simultaneously as independent diagnostic paths. If Architecture V2 is already
authoritative, its redundant V2 shadow is skipped.

The checked-in runtime defaults remain `CRITICAL_VALIDATOR_VERSION=baseline`
and `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`.
