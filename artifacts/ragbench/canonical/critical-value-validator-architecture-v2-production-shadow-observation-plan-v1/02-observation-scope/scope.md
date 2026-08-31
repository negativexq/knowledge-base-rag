# Observation scope

## Eligible traffic

Count a request only when it is a server-side RAG request that:

- reaches the support-ID and authorized-evidence path;
- reaches the structured-output path capable of critical-value validation;
- is eligible for Architecture V2 shadow execution; and
- is not health, readiness, bootstrap, admin, test, or debug traffic.

The denominator is `eligible_validator_requests`, not total HTTP traffic.

## Excluded traffic

Exclude health/readiness probes, static assets, admin endpoints, non-RAG
requests, requests bypassing support-ID validation, requests without a
validator-capable output structure, synthetic monitors unless separately
labeled, and traffic outside the approved observation environment.

## Frozen stopping rule

The observation closes only after **at least 1,000 eligible shadow executions
and at least 24 continuous hours**. It must stop no later than **7 days**. If
the count and time requirements are not both met by the maximum window, the
observation is inconclusive/failed and is not extended silently.

The dual rule covers both traffic variety and operational time variability.
