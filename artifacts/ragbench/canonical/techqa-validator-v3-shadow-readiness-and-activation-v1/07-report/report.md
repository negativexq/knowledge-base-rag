# Validator V3 shadow readiness and activation V1

## Decision

`VALIDATOR_V3_SHADOW_READINESS_PASSED`

The integrated V3 path is operationally ready for a separately authorized
shadow deployment. Local deterministic verification proved that baseline
remains authoritative with shadow enabled and that a shadow exception is
isolated from answer delivery.

`SHADOW_ACTIVATION_ELIGIBLE = YES`

No staging or production application runtime was available in this
environment. Qdrant and Jaeger containers were running, but the backend was
not running and no authorized traffic source was changed. Therefore:

`SHADOW_ACTIVATED = NO`

`activation_state = LOCAL_SHADOW_VERIFIED`

This is not production shadow evidence. `SHADOW_OBSERVATION_PENDING` remains
the canary status.

## Safety boundary

With `CRITICAL_VALIDATOR_VERSION=baseline` and shadow enabled, the baseline
result determines visible validation, forced abstention, citations, evidence
selection, support IDs, and authorization. V3 only produces bounded
comparison telemetry. If V3 raises, the baseline result is returned and the
bounded diagnostic class is `SHADOW_EVALUATION_FAILURE`.

The seven directional disagreement values are supported, and `SHADOW_ERROR`
is an additional bounded diagnostic value. Disagreement is behavioral
telemetry, not semantic correctness.

## Configuration and rollback

Committed defaults remain `baseline` and shadow `false`. Runtime activation,
when authorized later, is server-controlled only:

```text
CRITICAL_VALIDATOR_VERSION=baseline
CRITICAL_VALIDATOR_V3_SHADOW_ENABLED=true
```

`CRITICAL_VALIDATOR_VERSION=v3` is not authorized by this task. Disabling
shadow or restoring baseline requires no migration, reindex, data rewrite, or
model reload.

If `CRITICAL_VALIDATOR_VERSION=v3` is ever selected, the current deterministic
behavior is V3 primary with no second V3 shadow invocation; that combination is
not part of this rollout and is not authorized here.

## Telemetry and observation

Telemetry is bounded and excludes raw query, claim, support, document,
prompt, secret, and tenant-sensitive content. It includes outcome/reason
enums, value-type enums, counts, booleans, disagreement direction, shadow
error class, and baseline/V3 local durations.

The observation protocol is frozen before any real observation. Its completion
criterion is `OBSERVATION_WINDOW_REQUIRES_RUNTIME_BASELINE`: establish sample
and duration thresholds from the authorized runtime's baseline distribution.
No runtime comparisons were collected here, so no production counts or
latencies are claimed.

## Canary entry

Canary entry is not currently eligible. A separate observation review must
review each disagreement direction, shadow errors, latency, privacy, and
rollback readiness. A lower reject rate alone is not a canary gate.

Known residual limitations remain unchanged: `IV3-EQ-16` (12.00 hours vs 12
hours) and `IV3-EQ-17` (100.0% vs 100%) are known availability-only false
positives and were not fixed.

The final BGE verdict remains `BGE_REMOVAL_NOT_SUPPORTED`. Corrected HOLDOUT
remains consumed and was not reused. No provider call, deployment, traffic
change, or primary V3 activation occurred.
