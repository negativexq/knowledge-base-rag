# Production shadow observation plan V1

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_PRODUCTION_SHADOW_OBSERVATION_PLAN_PASSED`

This is a frozen observation design only. It does not enable production shadow,
change defaults, make Architecture V2 authoritative, or authorize canary.

## Frozen controls

- Architecture: `CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1`
- Authority: `baseline`
- Shadow: Architecture V2 only; V3 shadow false by default
- Repository default: `CRITICAL_VALIDATOR_VERSION=baseline`
- Shadow default: `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`
- Sample: at least 1,000 eligible executions **and** 24 hours
- Maximum window: 7 days
- Rollback: `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`, followed by
  normal process restart/redeploy and effective-config verification

## Hard safety policy

Coverage and required telemetry must be 100%. Unresolved unsafe-suspect,
security, privacy, visible mutation, fail-open, and UNKNOWN counts must be zero.
Validator-caused unexplained shadow errors must be zero. Environment failures
are attributed separately; a missed eligible shadow execution pauses the window
and cannot be silently counted as successful coverage.

Architecture V2 p95 must remain below 25 ms and p99 below 50 ms, with no
sustained attributable CPU/memory increase above 10%, event-loop blocking, or
material throughput regression. These are operational gates, not semantic
accuracy requirements.

## Privacy and review

Production OTel and canonical artifacts contain only bounded counters, enums,
durations, booleans, configuration state, and the bounded architecture ID.
Raw production queries, answers, evidence, literals, prompts, IDs, credentials,
cookies, and user/tenant content are forbidden. Disagreements are reviewed via
bounded metadata and safe local reproduction only.

All PS1–PS18 gates must pass before `CANARY_REVIEW_ELIGIBLE=YES`. Canary remains
a separate review and is never enabled automatically.

The machine-readable protocol and its SHA256 sidecar are the authoritative plan
for the future observation task.
