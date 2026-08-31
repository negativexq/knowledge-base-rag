# T10 version disagreement

- Claim wording: “Which Nimbus API version **family** should new integrations
  use, and what happens if the version header is omitted?”
- User-visible answer: new integrations use v3; omission defaults to
  deprecated v2.
- Application-owned support ID: `E1.S6`.
- Baseline: `PASS`, reason `NO_CRITICAL_VALUE`.
- V3: `INDETERMINATE` inferred from the bounded disagreement
  `BASELINE_PASS_V3_IND`; the V3 reason was not persisted.
- Raw model claim, raw support text, and support specificity: not recoverable
  from the frozen artifacts.

The wording is explicitly family-scoped at the user-question level, but the
exact claim/support values reaching the validator are unavailable. Therefore
V3 frozen-contract compliance, baseline over-permissiveness, and V3
availability conservatism cannot be adjudicated from this run.

Disagreement classification: **FORENSIC_INCONCLUSIVE**. It must not be used
as evidence for or against canary entry. Shadow disagreement is not ground
truth.
