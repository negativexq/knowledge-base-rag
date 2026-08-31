# Forensic compatibility

The existing `ForensicCapture` stage receives the Architecture V2 adapter
result through the existing `critical_validator` validation stage. This makes
the architecture ID, occurrence ledger metadata, role decisions, filtered
VALIDATE IDs, and frozen V3 delegation result locally inspectable.

`RAG_FORENSIC_CAPTURE_ENABLED=false` and
`RAG_FORENSIC_CAPTURE_RAW_TEXT=false` remain the defaults. Metadata mode omits
raw claim/literal content; raw mode is explicitly local and opt-in. Normal
OTel redaction remains independent and never receives the forensic payload.
