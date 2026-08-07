# 0005 — Real component wiring (`app/wiring.py` + `app/server.py`) built in Sprint 10, not Sprint 11

## Context

Sprint 7's plan deliberately kept `app/main.py::create_app()` a pure
factory — tests always pass fake `SyncManager`/`SyncHistory` components,
and no code path anywhere constructed the app with real Qdrant/Ollama/
SQLite. That sprint's plan explicitly deferred real service wiring to
"Sprint 11 (docker compose)."

Sprint 10's job was the multi-page Streamlit UI, whose own DoD required
real browser verification: triggering a manual sync from the Sources
page and seeing it reflected in Sync Status, asking a real question in
Chat and seeing a real streamed, cited answer. None of that is possible
without a real, running backend — but this project's sprint order put UI
(10) before Docker Compose Polish (11), the reverse of production-rag-
platform's order (where the backend was already containerized before its
own UI sprint).

## Decision

Pull forward the minimal slice of "real wiring" needed for Sprint 10's
own verification, without doing Sprint 11's full job (no containerization,
no fresh-clone `docker compose up` proof):

- `app/wiring.py::build_connectors()` / `build_app()` — constructs real
  `OllamaClient`, `QdrantStore`, `DocumentRegistry`, `SyncHistory`,
  `SparseEncoder`, the connectors dict, a `SyncManager`, and
  `ChatDependencies`, then calls `create_app(...)`.
- `app/server.py` — a module-level `app = build_app(settings)`, the
  actual target for `uvicorn app.server:app`. Kept as a separate module
  from `app/main.py` specifically so *importing* `app/server.py` is the
  only thing that touches real services at import time; every existing
  test still only imports `app/main.py`.

Sprint 11 then built directly on this rather than duplicating it — the
Dockerfile's `CMD` targets `app.server:app` unchanged, and Sprint 11's
job was purely the container/volume/CI layer around wiring that already
existed.

## Consequences

- `app/wiring.py` became the one real place every subsequent sprint's
  "real component" additions get wired in — the `embedding_concurrency`
  setting (Sprint 14), the shutdown-hook collection
  ([0006](0006-scheduler-wired-via-fastapi-lifespan.md) and Sprint 15's
  client-cleanup fix) all extend this same function rather than inventing
  a second wiring path.
- `create_app()`'s signature grew several optional, default-`None`
  parameters over time (`chat_deps`, `list_ollama_models`, `scheduler`,
  `on_shutdown`) specifically so it stays usable with zero real
  components in every existing test — each addition was verified not to
  change any existing test's behavior before being merged.
