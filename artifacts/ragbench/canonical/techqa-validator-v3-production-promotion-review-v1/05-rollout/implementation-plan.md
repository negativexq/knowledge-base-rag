# Future production integration plan

This review authorizes a separate implementation task only. It does not
change the production default.

1. Port the frozen V3 semantics into a production-compatible helper module;
   do not import calibration scripts at runtime.
2. Preserve claim-local support boundaries and all frozen behavior invariants.
3. Add reusable contract tests for locale ambiguity, numeric grouping,
   signed identifiers, CVE/SQLCODE identity, family-versus-exact versions,
   and ambiguous versions.
4. Add a server-side selector such as
   `CRITICAL_VALIDATOR_VERSION=baseline|v3`, defaulting to `baseline` and
   unavailable to end users.
5. Add the telemetry in `04-observability/telemetry-plan.md`.
6. Keep V3 disabled, run deterministic tests, and deploy only to shadow mode.
7. Review shadow disagreements before any canary activation.

No BGE, retrieval, embedding, prompt, Top-N, authorization, or API change is
part of this integration.
