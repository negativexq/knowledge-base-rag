# Critical Value Validator Architecture V2 Production Integration V1

## Decision

`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_PRODUCTION_INTEGRATION_PASSED`

Architecture V2 is now present in the production runtime path behind the
server-owned selector, but it is not activated. The default remains
`CRITICAL_VALIDATOR_VERSION=baseline`; the Architecture V2 shadow flag remains
`false`. Canary and primary use are not authorized.

## What changed

- Added the explicit selector value `architecture_v2` through the existing
  server settings and validator interface.
- Added the server-only `CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`
  control.
- Added a runtime adapter that invokes the frozen Architecture V2 entry point
  and preserves frozen V3 comparison semantics.
- Added bounded Architecture V2 role/count/shadow telemetry.
- Preserved local forensic compatibility while keeping raw OTel content out of
  telemetry.
- Added config and rollout documentation plus reusable integration tests.

Architecture V2 authoritative execution remains one canonical extraction →
immutable occurrence ledger → occurrence-local role classification →
structured VALIDATE filter → frozen V3 semantics. There is no raw masking,
role rediscovery, global value role, or post-role re-extraction.

## Compatibility and safety

No request, response, SSE, structured-output, support-ID, citation, frontend,
database, Qdrant, indexing, embedding, or stored-document change was needed.
Rollback is configuration-only to `baseline` or `v3`. Invalid selectors fail
closed. An authoritative validator infrastructure exception follows the
existing fail-closed abstention path; a shadow exception is isolated and does
not affect the visible response.

The focused integration suite passed 47 tests. The full deterministic suite
passed 1241 tests, skipped 1 environment-gated Notion test, and deselected 6
Ollama E2E tests. No task-caused regression was observed. Local synthetic
microbenchmarking found no material adapter blocker; its timings are not
production latency claims.

## Explicit non-activation

Architecture V2 authoritative: **NO**  
Architecture V2 shadow: **NO**  
Canary: **NO**  
Primary: **NO**

Next step is the separate
`CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_SHADOW_READINESS_V1`, which may
enable shadow only in controlled local/staging runtime and must keep baseline
authoritative.
