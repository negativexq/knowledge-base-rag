# Disagreement and attribution policy

Both arms are compared at the **request-level normalized outcome**:
`PASS`, `REJECT`, `INDETERMINATE`, `MIXED`, or `NO_VALIDATOR_RESULT`.
Occurrence-level or claim-level results must not be compared directly with a
request aggregate.

Allowed interpretation labels are:

`SAME`, `EXPECTED_CORRECTIVE_RECOVERY`, `AUTHORITATIVE_OVER_REJECT`,
`ARCHV2_MORE_CONSERVATIVE`, `ARCHV2_UNSAFE_SUSPECT`,
`UNEXPECTED_V3_SEMANTIC_DIFFERENCE`, `INFRA_ERROR`, and `UNKNOWN`.

Production telemetry records only bounded outcome pairs and enums. Every
non-`SAME` event is reviewed when volume is small; otherwise review uses a
predeclared stratified sample across every outcome pair. The review first uses
bounded metadata, then a safe synthetic/local reproduction with local forensic
capture. Raw production conversations are never copied into artifacts.

An unresolved `ARCHV2_UNSAFE_SUSPECT` or `UNKNOWN` count must be zero at close.
