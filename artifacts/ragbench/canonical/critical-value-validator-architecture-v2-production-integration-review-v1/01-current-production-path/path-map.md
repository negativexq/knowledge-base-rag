# Current production path

## Authoritative path

`app/wiring.py:179-193` selects `stream_support_unit_answer` whenever
`support_ids_enabled` is active and passes the server-owned
`critical_validator_version` and V3 shadow flag.

The current path is:

`generation → parse support-unit output → support-ID authorization →
audit_support_relevance → claim_local_critical_value_audit →
forced abstain → render support IDs/citations`

- `app/evidence/support_relevance.py:122-142` invokes the critical-value audit
  after lexical support relevance is computed.
- `app/llm/structured_output.py:753-832` validates support IDs, runs the
  critical validator, aggregates result codes, and sets application abstain.
- `app/llm/structured_output.py:870-936` records bounded validator metadata on
  the current OTel span.
- `app/llm/structured_output.py:1095-1105` renders the validated support IDs;
  invalid parts cannot become visible citations.
- `app/api/chat.py:286-300` forwards the generated events over SSE without
  changing the validator contract.

## Selector

`app/shared/config.py:70-71` currently defines:

`CRITICAL_VALIDATOR_VERSION = baseline | v3`, default `baseline`.

`app/shared/config.py:326-329` validates the server-owned selector. Invalid
values fail configuration validation; they do not silently choose a validator.

## Existing shadow

`app/evaluation/critical_values.py:1097-1116` runs V3 shadow only when the
authoritative selector is baseline. It catches shadow exceptions and preserves
the authoritative result.

## Forced abstain

`app/llm/structured_output.py:829-832` sets application abstain when no
support-backed answer parts survive validation. The visible rendering at
`app/llm/structured_output.py:1096-1105` emits the unavailable response in
that case.

## Citation resolution

Support IDs are validated before rendering. The rendered application citation
identity is derived from accepted support IDs, not from model text. No API
request or SSE schema change is needed for Architecture V2.
