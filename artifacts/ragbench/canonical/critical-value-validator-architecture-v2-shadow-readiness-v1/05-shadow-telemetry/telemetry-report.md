# Shadow telemetry report

Jaeger service: `knowledge-base-rag`.

Six controlled HTTP requests were observed. Five produced support-backed
answer parts and therefore reached the critical-value validator; all five had
`validator.version=baseline`, `validator.shadow.architecture_v2_enabled=true`,
`validator.shadow.architecture_v2.outcome` and
`validator.shadow.architecture_v2.disagreement` attributes. Normal shadow
requests had `validator.shadow.architecture_v2_error=false`.

Coverage among validator-capable requests: 5/5 = 100%.

Observed bounded fields:

- authoritative validator version and outcome
- V2 shadow enabled flag, outcome, disagreement, and error flag
- validator duration and baseline duration
- forced-abstain flag
- question character count only

Telemetry gap blocking SR6:

- `validator.architecture_id` was `none` on baseline-authoritative shadow
  spans; the frozen implementation does not promote the shadow architecture ID
  into the aggregate telemetry.
- `validator.occurrence_count`, `validator.validate_role_count`,
  `validator.skip_rejected_premise_count`, and
  `validator.ambiguous_keep_validating_count` remained zero/default on the
  aggregate span even when V2 shadow executed.
- The detailed V2 occurrence ledger is available through the forensic result
  object, but is not emitted into normal OTel, as required for privacy.

No normal OTel span contained raw query, answer, evidence, raw literal,
occurrence text, prompt, authorization, cookie, or secret-like content.
