# Production versus frozen V3

Current production uses `app/evaluation/critical_values.py` through
`app/evidence/support_relevance.py` and
`app/llm/structured_output.py`. It performs claim-local critical-value
checking together with the existing support-ID and authorization validation.

The frozen V3 behavior is currently implemented in
`scripts/run_validator_calibration_debug_v3.py`. Its `v3_status` path layers
numeric/identifier handling, conservative locale handling, and explicit
version-specificity handling over the offline calibration helpers. It is not
wired into the API and must not be imported directly by production.

If integrated later, the observable semantic delta is limited to:

- unambiguous numeric/identifier normalization;
- ambiguous numeric locale forms remaining conservative;
- explicit family-scoped version compatibility;
- exact version component equality;
- unspecified version specificity remaining `INDETERMINATE`.

No ACL, tenant-isolation, support-ID, provenance, public response, citation,
SSE, storage, model, retrieval, or external dependency change is required.
The smallest safe implementation is a production-compatible helper port with
the same behavior, a disabled server-side selector, telemetry, reusable
contract tests, and a default of the current baseline.
