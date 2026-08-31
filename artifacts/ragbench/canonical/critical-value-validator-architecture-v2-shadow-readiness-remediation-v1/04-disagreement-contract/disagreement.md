# Disagreement normalization

The comparison unit is the request-level aggregate validator outcome for both
arms. Each arm is normalized to one of `PASS`, `REJECT`, `INDETERMINATE`,
`MIXED`, or `NO_VALIDATOR_RESULT`. More than one validator invocation in the
aggregate is represented as `MIXED`, matching the existing authoritative span
contract; one invocation preserves its outcome. `SAME` means the two normalized
states are equal. Otherwise the bounded value is
`AUTHORITATIVE_<state>_ARCHV2_<state>`.

Per-part disagreement diagnostics remain in the local result/forensic data.
The aggregate shadow span no longer joins per-part states and cannot label a
request-level `MIXED` versus an occurrence-level `PASS` as `SAME`.
