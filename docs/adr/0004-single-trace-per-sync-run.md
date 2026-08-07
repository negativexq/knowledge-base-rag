# 0004 — One Jaeger trace per sync run, via a top-level span

## Context

Sprint 8 extended OpenTelemetry tracing (already covering the query path
since Sprint 0) to the sync/ingestion pipeline. Reading the code before
running anything against a real Jaeger surfaced three real blind spots:

1. `ingest_connector` opened no span of its own. Every child
   `ingest_document`/`delete_document` span had no parent context, and
   OpenTelemetry's rule is that a span with no parent starts a *new*
   trace — so a sync touching 3 documents produced 3 separate,
   unrelated traces in Jaeger, not one. This directly violated the
   sprint's own DoD ("a sync run can be traced end to end").
2. Connector I/O (`list_documents()`, per-document `get_content_hash()`)
   was never spanned — for `NotionConnector` these are real network
   requests plus 429-backoff sleeps, completely invisible.
3. Skipped (unchanged) documents produced zero trace evidence they were
   even checked — only a counter incremented.

## Decision

Wrap the entire `ingest_connector` call body in one `"ingest_connector"`
span (attributes: `source_type`, final
`files_processed`/`files_skipped`/`files_deleted`/`chunks_upserted`).
Every other span opened during that call — `fetch_documents`,
`check_document` (opened for *every* document, including skipped ones,
with a `check.changed` attribute), `ingest_document`, `delete_document`,
and so on — becomes its child automatically through OpenTelemetry's
context propagation, no manual trace ID threading required.

`SyncManager.trigger_sync()` (Sprint 7) does the same one level up: a
`"sync_run"` span wraps the *whole* attempt, including a rejected
concurrent-sync attempt, so even a 409-rejected trigger leaves trace
evidence. Its trace ID is extracted (`format(span.get_span_context().trace_id,
"032x")`, the same pattern `app/llm/generate.py` already used for the
query path since Sprint 0) and written into `sync_runs.trace_id`
(Sprint 8's own schema addition) — available before the sync even
finishes, since `SyncHistory.start_run()` is called early.

## Consequences

- A sync run — successful, failed, or rejected — is always exactly one
  Jaeger trace, verified for real against a live Jaeger instance in
  Sprint 8 (not mocked): a real filesystem sync produced 9 spans under
  one trace ID with the expected hierarchy.
- `POST /sync/{source_type}` and `GET /sync/{source_type}/history` both
  expose `trace_id` in their response, letting the Sync Status UI page
  (Sprint 10) link directly to Jaeger.
- Sprint 12's real browser verification (of the *query*-side trace panel,
  `app/ui/trace_client.py`) hit a related but distinct bug: Jaeger's
  OTLP ingestion is async and batched (`BatchSpanProcessor`), so a trace
  can appear *partially* indexed — some child spans present, the
  last-closing span (the root, guaranteed to close last) not yet
  flushed. The fix there was specific to the read side: retry until the
  root span by name is present, not just until "any spans exist" — see
  `app/ui/trace_client.py::fetch_trace_spans`. That fix is about
  *reading* a trace after the fact, not about how sync spans are
  produced, but the same "wait for the root span specifically" principle
  applies to both.
