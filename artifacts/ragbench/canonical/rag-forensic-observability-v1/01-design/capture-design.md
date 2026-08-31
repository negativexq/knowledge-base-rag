# RAG forensic observability V1

This is an explicit, server-owned, local/debug capture path for controlled
replay. It is not general production logging.

## Controls

- `RAG_FORENSIC_CAPTURE_ENABLED=false` by default.
- `RAG_FORENSIC_CAPTURE_RAW_TEXT=false` by default.
- Raw mode is valid only when capture is also enabled.
- The capture directory is server-configured; request data cannot select it.
- OpenTelemetry receives only bounded metadata already suitable for tracing.

## Captured boundaries

One JSON record is written per enabled request. It contains request identity,
retrieval candidate metadata, reranker metadata, EvidenceBuildResult metadata,
generation contract and raw structured output (only in raw mode), support-ID
validation, critical-validator input/result, abstain transition, citation
resolution, and visible outcome.

Chunk/evidence text, query text, model answer text, and local token context are
local-only and are included only with both explicit switches enabled. API keys,
authorization headers, cookies, passwords, database URLs, and secrets are
always redacted.

Capture write errors are logged as bounded warnings and never change answer
delivery. The existing validator, retrieval, evidence, generation, support-ID,
and citation decisions are not changed by this instrumentation.
