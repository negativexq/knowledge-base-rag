# Canary-review eligibility

Successful production shadow observation is necessary but does not authorize
canary or promotion. Canary-review eligibility requires:

- PS1–PS18 all pass;
- both 1,000 eligible executions and 24 hours are complete within 7 days;
- baseline was authoritative for 100% of observed eligible requests;
- shadow coverage and required telemetry are 100%;
- security, privacy, visible mutation, and unsafe-suspect counts are zero;
- unexplained validator-caused shadow errors and unresolved UNKNOWNs are zero;
- disagreement attribution is complete;
- latency/resource thresholds and rollback verification pass.

Result: `CANARY_REVIEW_ELIGIBLE=YES` only. `CANARY_ENABLED` remains false and
requires a separate canary review.
