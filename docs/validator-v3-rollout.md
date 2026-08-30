# Validator V3 rollout

`VALIDATOR_CANDIDATE_V3_44dd8bdd2c0b` is integrated behind the server-owned
`CRITICAL_VALIDATOR_VERSION` selector. Its frozen composition is numeric
normalization, version normalization, identifier/negative handling, a locale
ambiguity guard, and a version-specificity guard. Ambiguous locale and version
specificity remain conservative `INDETERMINATE` outcomes; support-ID
authorization remains a separate security boundary.

The selector accepts `baseline` or `v3` and defaults to `baseline`. The
optional `CRITICAL_VALIDATOR_V3_SHADOW_ENABLED` setting defaults to `false`.
When enabled with the baseline selector, V3 evaluates the same claim/support
inputs for bounded diagnostics only; baseline still controls the visible
answer and abstention behavior. Telemetry records version, outcome, bounded
reason/type fields, disagreement class, shadow-error class, forced-abstain
state, and separate baseline/V3 local processing times. A shadow exception is
isolated and cannot fail the baseline answer path. Raw claims, queries, support
text, and tenant-sensitive evidence are not logged.

The V3 independent validation passed, but it retains two known availability
false positives: `12.00 hours` versus `12 hours`, and `100.0%` versus `100%`.
They are not changed by this integration.

Rollback is immediate at the configuration boundary: set
`CRITICAL_VALIDATOR_VERSION=baseline` and restart/redeploy according to normal
configuration procedure. No reindex, migration, data rewrite, model reload, or
artifact regeneration is required. Local shadow safety is verified, but no
authorized live/staging runtime observation was performed; the next step is a
separate telemetry-backed shadow observation. V3 is not active for
user-visible traffic.
