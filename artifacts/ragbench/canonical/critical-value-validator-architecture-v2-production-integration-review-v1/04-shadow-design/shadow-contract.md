# Architecture V2 shadow contract

Architecture V2 can run as a diagnostic shadow over the same parsed model
answer, authorized support units, and evidence context used by the
authoritative validator.

Authoritative result remains unchanged. Shadow execution must not mutate:

- structured answer objects;
- support-ID lists;
- validated parts;
- citation objects;
- forced-abstain state;
- HTTP/SSE response payloads.

Recommended bounded comparison enum:

`AUTHORITATIVE_PASS_ARCHV2_PASS`,
`AUTHORITATIVE_PASS_ARCHV2_REJECT`,
`AUTHORITATIVE_PASS_ARCHV2_IND`,
`AUTHORITATIVE_REJECT_ARCHV2_PASS`,
`AUTHORITATIVE_REJECT_ARCHV2_REJECT`,
`AUTHORITATIVE_REJECT_ARCHV2_IND`,
`AUTHORITATIVE_IND_ARCHV2_PASS`,
`AUTHORITATIVE_IND_ARCHV2_REJECT`,
`AUTHORITATIVE_IND_ARCHV2_IND`.

Additional bounded role counters are feasible:

`occurrence_count`, `validate_role_count`, `skip_rejected_premise_count`,
`ambiguous_keep_validating_count`, `occurrence_identity_error_count`, and
`role_classification_error_count`.

If shadow execution raises, the authoritative path continues with
`shadow_error=true` and a bounded error class. Shadow failure must never become
a user-visible error.
