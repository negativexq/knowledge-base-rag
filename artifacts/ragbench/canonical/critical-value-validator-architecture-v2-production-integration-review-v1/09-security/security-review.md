# Security review

Architecture V2 is eligible only after support-ID authorization has selected
the model-visible, authorized support units. Its role filter changes which
critical-value occurrences are sent to frozen V3 comparison; it does not
authorize support units or create citation identities.

Review findings:

- tenant isolation: unchanged;
- hidden/cross-tenant support rejection: unchanged;
- support-ID authorization: unchanged;
- citation ownership: unchanged;
- selector control: server-side only;
- raw production telemetry: not required and forbidden;
- new dependency/service/model: none;
- mutable global or cross-request occurrence state: none in the frozen V2
  implementation.

Shadow errors must be isolated. An authoritative V2 validator error must not
fail open; it must be treated as validator infrastructure failure.
