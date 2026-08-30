# VALIDATOR V3 production promotion review V1

## Decision

`VALIDATOR_V3_PRODUCTION_PROMOTION_REVIEW_PASSED`

`PROMOTION_IMPLEMENTATION_AUTHORIZED = YES`

This authorizes a separate implementation review. It does not enable V3,
change traffic, or deploy anything. `CANARY_READY = NO` until the required
telemetry and server-side feature control are implemented.

## Candidate and validation integrity

Candidate: `VALIDATOR_CANDIDATE_V3_44dd8bdd2c0b`

Candidate source SHA256:
`44dd8bdd2c0b5468248870563d305773d1931ef7709ecf2ed145188b708a54b1`

The V3 DEBUG tree and independent-validation tree match the captured review
identities. Independent validation passed all G1-G12 on 60 cases. It recorded
18/18 true-conflict recall, 2 false positives, zero unsafe indeterminate
acceptances, zero locale unsafe acceptances, zero identifier unsafe
acceptances, zero version-specificity errors, and zero security regressions.

The two residual false positives are:

- `IV3-EQ-16`: `12.00 hours` versus `12 hours`;
- `IV3-EQ-17`: `100.0%` versus `100%`.

Both are representation-related availability risks. They are not unsafe
acceptances, security bypasses, or evidence of a hidden safety defect. They
remain unfixed because this review does not patch V3.

## Production integration boundary

Current production calls `app/evaluation/critical_values.py` from the support
relevance and structured-output validation paths. V3 currently exists as an
offline experiment path in `scripts/run_validator_calibration_debug_v3.py` and
is not directly production-integratable without a clean port.

The separate implementation task must port the exact frozen semantics into a
production-compatible helper. It must not import experiment scripts, broaden
claim-local evidence search, or change authorization. No public response,
citation, support-ID, SSE, storage, model, retrieval, or external-dependency
change is required.

## Safety and operations

V3 adds bounded deterministic parsing only: no model loading, network calls,
blocking I/O, external state, or mutable global state. The relevant operations
are local regular-expression/token comparisons with bounded input-dependent
work and are suitable for concurrent requests after a production-compatible
port.

Failure behavior remains conservative: ambiguous locale and ambiguous version
specificity produce `INDETERMINATE`; claim-local conflicts reject; missing
comparable values remain indeterminate; authorization failures remain fail
closed.

The existing OpenTelemetry path does not expose the required validator-specific
metrics, so telemetry is a promotion prerequisite. The future selector must be
server-controlled, default to `baseline`, and appear in the configuration
fingerprint. It must never be user-controlled.

Rollback is a server-side switch back to `baseline`; it requires no reindex,
data migration, model reload, or artifact regeneration.

## Gate result

R1-R12 all pass. R7 and R8 pass with prerequisites explicitly recorded. The
candidate is suitable for a separate implementation task, but the rollout
remains blocked pending telemetry and feature control.

Final BGE verdict remains `BGE_REMOVAL_NOT_SUPPORTED`. Corrected HOLDOUT was
not reused and remains consumed. No provider call, production mutation,
deployment, or traffic change was made.
