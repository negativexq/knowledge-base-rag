# Invalid runtime attempts

The first six controlled HTTP requests reached the local API, but the client-side
SSE summarizer used for capture contained an invalid inline-Python newline escape.
Those attempts are not canonical evidence and are preserved here under the
invalid-run policy. No source, labels, or runtime configuration were changed.

Reason: `SCORING_CLIENT_PARSE_ERROR`
Canonical execution: not established by these attempts.
