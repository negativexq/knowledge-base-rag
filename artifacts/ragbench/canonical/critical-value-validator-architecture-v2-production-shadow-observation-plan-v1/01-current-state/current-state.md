# Current rollout state

Architecture V2 is integrated behind the server-side selector
`baseline | v3 | architecture_v2`. The repository default is `baseline` and
`CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`.

Completed state:

```text
INTEGRATED
→ LOCAL_SHADOW_RUNTIME_VERIFIED
→ PRODUCTION_SHADOW_NOT_STARTED
```

The future observation keeps `baseline` authoritative and enables only the
diagnostic Architecture V2 shadow. V3 shadow remains false for the clean
observation window unless a separately approved operational change is made.

This task made no runtime, provider, retrieval, BGE, or production-config
changes.
