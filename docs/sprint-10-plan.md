# Sprint 10 Plan — UI (Multi-page Streamlit)

## Goal

Three Streamlit pages via `st.navigation`: Chat (streaming + citations +
pipeline trace, ported from production-rag-platform's Sprint 11/12), Sources
(connector list, document counts, manual sync trigger), Sync Status (run
history, per-source document counts, Jaeger links).

## venv: separate `.venv-ui`, confirmed by a real conflict, not assumed

production-rag-platform hit a real `streamlit`/`fastapi` dependency conflict
and used a separate `.venv-ui` + `requirements-ui.txt`. Rather than copy
that decision on faith, it was re-verified in *this* project's own
dependency versions:

```
$ pip install fastapi==0.115.6 streamlit==1.61.1
ERROR: Cannot install fastapi==0.115.6 and streamlit==1.61.1 because
these package versions have conflicting dependencies.
The conflict is caused by:
    fastapi 0.115.6 depends on starlette<0.42.0 and >=0.40.0
    streamlit 1.61.1 depends on starlette<1.4.0 and >=0.46.0
```

Same conflict, same versions as the reference project (this project pinned
the identical `fastapi==0.115.6`). Decision: `.venv-ui` + `requirements-ui.txt`,
unchanged from the reference project's reasoning. This project's UI needs
even less than the reference project's did — no direct Qdrant/ingestion
access (see below), so `requirements-ui.txt` is just `streamlit`, `httpx`,
`pandas` (for the trace bar chart). No `qdrant-client`, `pymupdf`,
`fastembed`, `sentence-transformers`, or `deepeval` — this UI never touches
ingestion or embedding directly, it only calls HTTP endpoints.

## Everything through HTTP, not direct component access

production-rag-platform's Streamlit UI called its ingestion pipeline
in-process (`ingest_helper.py::ingest_uploaded_file`) because file upload
had no existing HTTP endpoint. This project's scope is different — Sources
needs connector counts and a sync trigger, both of which map cleanly onto
HTTP: the sync trigger already exists (`POST /sync/{source_type}`, Sprint
7); a new `GET /sources` endpoint is added for connector + document-count
listing. No file upload is in this sprint's scope (the filesystem
connector scans a fixed root folder — see `filesystem_root_path` below),
so the UI never needs direct Qdrant/registry/ingestion access at all. This
keeps `requirements-ui.txt` minimal and keeps the "UI is a read-only(-ish)
HTTP client to the backend" pattern the reference project's Sprint 11/12
already established for `/chat` and Jaeger.

## A real backend has never been wired in this project — closing a gap

`app/main.py::create_app()` has been a factory since Sprint 7, deliberately
never called with real components — Sprint 7's plan explicitly deferred
real service wiring to "Sprint 11 (docker compose)". But *this* project's
Sprint 10 (UI) comes *before* its Sprint 11 (Docker Compose Polish) —
unlike production-rag-platform, where the backend was already
containerized and running before its UI sprint. This sprint's own DoD
("gerçek tarayıcıda doğrulanmış") is impossible to satisfy without a real,
running backend, so a minimal piece of that wiring has to move earlier:

- `app/wiring.py::build_connectors(settings)` / `build_app(settings)` —
  constructs real `OllamaClient`, `QdrantStore`, `DocumentRegistry`,
  `SyncHistory`, `SparseEncoder`, the connectors dict (filesystem always;
  Notion only if `notion_api_key` is set — reusing
  `app.sync.scheduler.sync_intervals_from_settings`'s same "is this
  connector actually configured" logic so there's one definition of
  "active connectors", not two), and a `SyncManager`, then calls
  `create_app(manager, history, registry)`.
- `app/server.py` — a module-level `app = build_app(settings)` for
  `uvicorn app.server:app` (kept separate from `app/main.py` so
  `create_app()` itself stays a pure, import-side-effect-free factory —
  existing tests construct fake components and never import `server.py`).
- `Makefile`: new `dev` target (`uvicorn app.server:app --reload`).

This is deliberately *not* Sprint 11's full docker-compose polish (no
containerization, no fresh-clone `docker compose up` proof) — just enough
real wiring to run the backend once, locally, for this sprint's own
browser verification. Sprint 11 can build on `app/wiring.py` rather than
duplicate it.

**New setting**: `filesystem_root_path: str = "data/documents"` — the
`LocalFilesystemConnector`'s scan root needed real wiring; no such setting
existed before (only `registry_db_path` pointed at a real path). A
`data/documents/.gitkeep` keeps the (otherwise empty) folder in git.

**Scope line held**: `SyncScheduler` (periodic sync, Sprint 7) is *not*
started by `build_app()` — this sprint only needs manual "sync now" to
work for the DoD; wiring the periodic loop into a real process is a
Sprint 11 concern (needs a proper ASGI lifespan hook, not sketched here to
avoid speculative design).

## New endpoints

- **`POST /chat`** (`app/api/chat.py`) — ported from production-rag-
  platform's `app/api/chat.py`, adapted to this project's provider
  abstraction: `get_chat_provider(settings)` / `get_embedding_provider(settings)`
  / `default_chat_model(settings)` / `default_embed_model(settings)`
  (Sprint 1) instead of a hardcoded `OllamaClient`, so the chat endpoint
  respects `GENERATION_PROVIDER=claude` the same way every other call site
  does. Same `chat_request`/`load_models` span names as the reference
  project (kept identical on purpose — `app/ui/trace_client.py`'s root-span
  detection is ported unchanged and expects `chat_request`).
- **`GET /sources`** (`app/api/sources.py`, new — no reference-project
  equivalent, this project's connector/registry model doesn't exist there)
  — `[{"source_type": str, "document_count": int, "is_running": bool}]`,
  built from `SyncManager.known_source_types` + `DocumentRegistry.list_documents(source_type)`
  counts + `SyncManager.is_running(source_type)`. Requires `create_app()`
  to gain a `registry` parameter (existing tests updated accordingly).

## Chat page — ported pieces, adapted regex already done

`app/ui/sse_client.py` (`parse_sse_lines`) and `app/ui/trace_client.py`
(`fetch_trace_spans`, with its Sprint 12 partial-trace retry fix) port
unchanged — both are protocol-shaped (SSE line parsing, Jaeger's JSON
response shape) with nothing PDF/single-source-specific in them.
`app/ui/citation_formatting.py` was already adapted in Sprint 0/7 for the
multi-source citation regex (`[s.source_type:source_id/location]`) — no
further change needed. The trace panel's bar chart and "Open in Jaeger"
link port unchanged (`JAEGER_URL` env var, same default `:16686`).

## Sources / Sync Status pages

`app/ui/sources_client.py` (new) — thin `httpx` wrappers:
`fetch_sources()`, `trigger_sync(source_type)`, `fetch_sync_history(source_type)`.
Sources page renders one row per connector (name, document count, running
badge) with a "Sync now" button calling `trigger_sync` — its own page, not
a tab inside Chat, per the dbt-feature-lineage lesson this sprint's
instructions call out (`st.tabs()` isn't lazy; an expensive action must not
sit behind a tab that renders eagerly with the rest of the page). Sync
Status page loops over the same connector list and renders each one's
`fetch_sync_history()` as a table, with a Jaeger link built from each row's
`trace_id` (`{JAEGER_URL}/trace/{trace_id}`, same pattern as the chat trace
panel).

## Test-first scope

Testable without a browser (real unit/integration tests): `parse_sse_lines`
(pure function, ported tests), `fetch_trace_spans` (httpx `MockTransport`,
ported tests including the partial-trace-retry regression), the new
`app/ui/sources_client.py` wrappers (httpx `MockTransport`), `GET /sources`
and `POST /chat` (FastAPI `TestClient`, fake components — same pattern as
`tests/test_api_sync.py`). Not unit-tested: the Streamlit page scripts
themselves (`st.navigation`, `st.chat_message`, `st.button` wiring) — these
are verified by a real browser session per the DoD, not simulated.

## Real browser verification plan

1. Bring up real Qdrant + Jaeger (`docker compose up -d`), real native
   Ollama, run `app.server:app` for real (`make dev`), run Streamlit for
   real (`make ui`).
2. Put a real Markdown file into `data/documents/`, open the Sources page,
   click "Sync now" for `filesystem` — confirm the document count updates.
3. Open Sync Status — confirm the just-triggered run appears with
   `status=success`, correct file counts, and a working Jaeger trace link.
4. Open Chat, ask a real question against the synced content — confirm
   token-by-token streaming, a bold citation tag, a grounding caption, and
   a working pipeline-trace expander (bar chart matching a direct
   `curl {JAEGER_URL}/api/traces/{trace_id}` check, same cross-check
   production-rag-platform's Sprint 12 used).
