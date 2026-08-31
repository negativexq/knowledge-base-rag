# Forensic capture

The deterministic controlled forensic suite passed the metadata-only and raw
local-capture contracts (included in the focused 65-test run).

Metadata-only mode (`RAG_FORENSIC_CAPTURE_ENABLED=true`, raw text false)
exposes bounded stage data and omits raw query/model/evidence text. The
Architecture V2 structured diagnostic includes the occurrence ledger metadata,
role decisions, filtered validate IDs, and delegated V3 result where the V2
result is present.

Controlled raw mode (raw text true) is accepted only when capture is explicitly
enabled, persists synthetic local fixture content in the forensic artifact, and
redacts secret-like fields. The same content is excluded by `redact_for_otel`.

Clean defaults remain:

- `RAG_FORENSIC_CAPTURE_ENABLED=false`
- `RAG_FORENSIC_CAPTURE_RAW_TEXT=false`

No production-wide forensic capture was enabled.
