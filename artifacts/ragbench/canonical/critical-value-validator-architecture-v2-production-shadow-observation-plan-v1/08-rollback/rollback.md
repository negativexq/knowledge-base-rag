# Rollback and pause policy

## Immediate shadow rollback

Set `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false` and restart/redeploy
according to the current environment configuration model when any of these is
confirmed: security regression, privacy leak, visible/support-ID/citation/
forced-abstain mutation, fail-open behavior, repeated validator-caused shadow
exceptions, or material/unbounded latency or resource instability.

Rollback is configuration-only. No DB/Qdrant migration, reindex, embedding
regeneration, or data rewrite is required. Verify after restart that baseline
is still authoritative and shadow execution is disabled.

## Pause and investigate

Pause the window, without collecting raw content, for unexplained coverage
loss, a disagreement spike, accumulating UNKNOWN events, or environment
instability that makes the sample incomparable. Resume only with the same
candidate and a documented clean window; otherwise invalidate the window.

The rollback is not hot reload: environment-variable changes require the
normal process restart/redeploy.
