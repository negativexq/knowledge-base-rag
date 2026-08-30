# Security review

Decision: `SECURITY_BOUNDARY_UNCHANGED = YES`

The frozen V3 validation path did not alter authorization or provenance
semantics. Independent validation recorded zero security regressions, zero
unauthorized acceptance, zero hidden-support acceptance, zero cross-tenant
acceptance, zero spoofed-support acceptance, and zero injection bypass.

The future integration must keep support-ID validation before any value-level
normalization and must continue to pass only authorized, model-visible
support units to the claim-local validator. V3 must not search global
evidence or treat normalized values as authorization evidence.

Required security invariants:

- tenant ACL enforcement remains unchanged;
- unknown, hidden, unauthorized, cross-tenant, and spoofed IDs fail closed;
- prompt-injection content cannot change validator authorization;
- signs, CVE identifiers, and technical identifiers remain identity-sensitive;
- no raw claims or support text are emitted to telemetry.
