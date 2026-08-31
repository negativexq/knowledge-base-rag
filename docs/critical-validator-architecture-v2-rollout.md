# Critical-value validator Architecture V2 rollout

Architecture V2 is integrated behind the server-owned
`CRITICAL_VALIDATOR_VERSION` selector. Allowed values are `baseline`, `v3`,
and `architecture_v2`; the default remains `baseline`. Invalid values fail
closed during settings validation.

The optional `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED` flag defaults to
`false`. Shadow execution is diagnostic-only: it cannot change the
authoritative result, forced abstention, support IDs, citations, SSE, or HTTP
response. OTel receives bounded counts and enum outcomes only; detailed
occurrence data is limited to controlled forensic capture.

Rollback is configuration-only: select `baseline` or `v3`; no database,
Qdrant, index, embedding, or document migration is required.

Rollout progression:

`INTEGRATED → LOCAL/STAGING SHADOW → SHADOW REVIEW → PRODUCTION SHADOW → CANARY → PRIMARY CONSIDERATION`

Only the integration step is complete. Architecture V2 is not activated,
shadow is not enabled, and canary/primary consideration are not authorized.
