# Bounded production metrics

Required aggregate fields:

- eligible requests, shadow executions, and coverage;
- authoritative and Architecture V2 normalized outcomes;
- `SAME` and disagreement counts/rates;
- shadow errors and classified environment errors;
- Architecture V2 duration p50/p95/p99/max and baseline duration when
  available;
- occurrence, VALIDATE, SKIP_REJECTED_PREMISE, and AMBIGUOUS counts;
- visible/support-ID/citation/forced-abstain mutation counts;
- security regressions, missing telemetry fields, privacy leaks, unsafe
  suspects, and unresolved UNKNOWN disagreements;
- bounded CPU/memory/event-loop/resource stability indicators when already
  available.

Required Architecture V2 metadata must be present for 100% of successful
shadow executions. The OTel schema is bounded enums, booleans, counters, and
durations only.
