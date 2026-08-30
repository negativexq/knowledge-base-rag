# Validator V3 production integration V1

## Decision

`VALIDATOR_V3_PRODUCTION_INTEGRATION_PASSED`

The frozen candidate `VALIDATOR_CANDIDATE_V3_44dd8bdd2c0b` was ported into
production-compatible application code without importing experiment scripts.
The port matches all 50 frozen non-security V3 contract fixture decisions and
reason classes checked offline; support-ID authorization remains a separate
security layer.

## Runtime controls

`CRITICAL_VALIDATOR_VERSION` accepts only `baseline` and `v3`, fails closed on
invalid configuration, and defaults to `baseline`. The optional
`CRITICAL_VALIDATOR_V3_SHADOW_ENABLED` setting defaults to false. With baseline
active and shadow enabled, V3 is evaluated only for diagnostics and baseline
continues to determine the visible answer and abstention behavior.

The selector is serving configuration, not an embedding/index schema field.
It is visible in request/report metadata and bounded OpenTelemetry attributes.
Telemetry records enums, counts, booleans, disagreement class, and duration;
raw queries, claims, support text, and tenant-sensitive evidence are not
recorded. Telemetry failures cannot break answer delivery.

## Safety and rollback

No ACL, tenant-isolation, support-ID, prompt-injection, citation, public
response, or SSE contract changed. V3 adds no provider, network, model, I/O,
database, migration, or reindex dependency. Rollback is the server-side
selector change from `v3` to `baseline`; it needs no data or index migration.

The two known availability-only V3 residual false positives (`12.00 hours`
versus `12 hours`, and `100.0%` versus `100%`) were not changed.

## Activation boundary

`SHADOW_ACTIVATION_ELIGIBLE = YES`, but shadow remains disabled and no traffic
was changed. A separate readiness task must verify telemetry in the deployed
path, define an observation window, and activate shadow only while keeping
baseline user-visible. V3 is not the production default.

Final BGE verdict remains `BGE_REMOVAL_NOT_SUPPORTED`. The corrected HOLDOUT
was not reused and remains consumed.
