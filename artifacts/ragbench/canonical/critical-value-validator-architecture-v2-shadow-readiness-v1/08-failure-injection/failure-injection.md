# Failure injection

Deterministic test-only injection passed:

- V2 shadow exception: baseline authoritative execution continued, result and
  failure codes were preserved, and bounded `SHADOW_ERROR` / shadow-error state
  was produced.
- V2 authoritative exception: the existing application-abstain path returned
  `CRITICAL_VALIDATOR_INFRASTRUCTURE_FAILURE`; no fail-open answer was allowed.

No unsafe runtime hook was exposed to the user-facing request.
