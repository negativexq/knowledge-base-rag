# Selector review

Current selector is `baseline | v3`, default `baseline`, and must remain so.

The minimal future extension is:

`baseline | v3 | architecture_v2`

with an explicit server-side setting only. The future configuration change
must extend the existing Literal/allow-list validation rather than introduce a
free-form selector. Invalid values such as `banana` must fail closed at
startup/configuration validation.

The following controls are explicitly not authorized by this review:

- query parameter or request-body validator selection;
- HTTP-header validator selection;
- frontend-controlled mode;
- changing the default away from `baseline`;
- automatic Architecture V2 shadow enablement.

The proposed optional future flag is:

`CRITICAL_VALIDATOR_ARCH_V2_SHADOW_ENABLED=false`

It must be server-side, default false, and independent from the authoritative
selector.
