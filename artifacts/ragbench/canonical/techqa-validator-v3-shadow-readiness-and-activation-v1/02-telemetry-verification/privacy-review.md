# Shadow telemetry privacy review

The integrated validator telemetry uses bounded enums, booleans, counts, and
local durations. It does not emit raw claims, queries, support text, document
content, prompts, secrets, or tenant-sensitive evidence. Support IDs and query
IDs are not telemetry dimensions.

The existing request span remains the reporting boundary. Exporter failures
are contained by the existing telemetry helper and cannot change answer
delivery. Shadow evaluation failures use only the bounded
`SHADOW_EVALUATION_FAILURE` class; arbitrary exception text is not recorded.

The validator version and shadow state are server-owned configuration values.
They are suitable for a bounded configuration fingerprint, but they do not
alter the embedding/index fingerprint.

Decision: `PRIVACY_PASS`.
