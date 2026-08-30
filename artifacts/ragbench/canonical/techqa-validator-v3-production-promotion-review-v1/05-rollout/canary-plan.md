# Canary plan

Lifecycle:

`FROZEN` → `IMPLEMENTED_DISABLED` → `SHADOW` → `CANARY` → `PROMOTED`

Rollback from any post-shadow state returns to `BASELINE`.

Stage 0 keeps current production behavior unchanged. Stage 1 runs baseline
and V3 side by side where cheaply possible, while only baseline controls the
visible response. Stage 2 uses an internal cohort, environment-level canary,
or server-side allowlist supported by the deployment environment. Stage 3
expands the cohort only after safety and disagreement review. Stage 4 is a
separate promotion decision.

No traffic percentage is prescribed because the repository does not define a
deployment router. Canary activation is blocked until telemetry and the
server-side selector exist.

Hard rollback triggers: any ACL/tenant/support-ID regression, unsafe version
or locale acceptance, sign/identifier violation, validator bypass, or V3
runtime exception increase attributable to the integration.

Soft review triggers: unexpected reject or indeterminate-rate increase,
forced-abstain increase, disagreement spike, or validator latency regression.
Thresholds must be established from a shadow baseline rather than invented
in this review.
