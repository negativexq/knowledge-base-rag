# Sprint 11 Plan — Docker Compose Polish

## Goal

`docker compose up` brings up Qdrant + Jaeger + the backend (new — this
project's backend has never run in a container before), Ollama stays
native, and the registry/sync-history SQLite file survives a container
restart.

## Ollama stays native — reason unchanged, re-confirmed still applies

production-rag-platform's reasoning was Docker Desktop on macOS having no
Metal GPU passthrough, so a containerized Ollama would fall back to slow
CPU inference. This machine is still macOS/Docker Desktop — the same
constraint holds, nothing to re-litigate. `OLLAMA_BASE_URL=http://host.docker.internal:11434`
is the existing default (Sprint 0) and has never actually been exercised
from inside a container before — this sprint is the first real test of
that assumption (see verification plan below).

## Dockerfile: the CUDA/torch lesson, ported before it bites again

production-rag-platform discovered (not assumed) that `sentence-transformers`
pulls `torch` as a transitive dependency, and pip's default resolution on
manylinux picks the CUDA-enabled wheel (~2GB of `nvidia_*` packages) even
though the container has no GPU (Ollama is native, this container never
touches a GPU). This project's `app/reranker/cross_encoder.py` uses the
exact same library — same bug, guaranteed, if not preempted. Fix ported
unchanged: install the CPU-only torch wheel from PyTorch's own CPU index
*before* `pip install -r requirements.txt`, so the later install sees
torch already satisfied and never resolves the CUDA variant.

Base image `python:3.12-slim` (matches this project's `requires-python
>=3.11` and the reference project's choice), `curl` installed for the
Docker healthcheck, `COPY app/ ./app/` + `COPY prompts/ ./prompts/`
(`app/llm/prompt.py` loads `prompts/answer_v{1,2}.txt` at runtime — would
break silently at request time, not build time, if forgotten). `CMD
uvicorn app.server:app` — this project's real entrypoint is
`app.server:app` (Sprint 10), not `app.main:app` (the bare, real-service-
free factory tests use).

## New: `/health` and `/health/ollama`

Neither existed before this sprint (no prior deployment target needed
them). `GET /health` — plain liveness, used by the Docker healthcheck.
`GET /health/ollama` — a REAL connectivity check reusing
`OllamaClient.list_models()` (already exists, unused until now), returns
the actual model list. This is deliberately ported from
production-rag-platform's Sprint 10, which used the identical endpoint to
prove `host.docker.internal` really resolves from inside a container
rather than trusting the `.env.example` comment — the same unverified
assumption exists in this project and gets the same real proof this
sprint (see verification plan).

## Registry/sync-history persistence: named volume, not bind mount

`DocumentRegistry` and `SyncHistory` share one SQLite file
(`registry_db_path`, default `data/registry.db`, resolved under the
container's `WORKDIR /app`) — this is genuinely new in this project (the
reference project never had a registry; its "Docker Compose Polish"
sprint had no analogous stateful-file question). Decision: a **named
volume** (`registry_data:/app/data`), not a bind mount to a host path —
this is opaque runtime state (a SQLite file, not something a user edits
directly), matching the existing `qdrant_storage` named-volume precedent
in this same compose file, and avoiding host-OS file-permission
mismatches a bind mount can introduce for a file the container process
owns exclusively.

`data/documents/` (the `LocalFilesystemConnector`'s scan root, Sprint 10)
is the opposite case — a user-facing folder people drop real files into —
so it gets a **bind mount** instead: `./data/documents:/app/documents`,
with `FILESYSTEM_ROOT_PATH=documents` set in the backend service's
`environment:` block to point at the bind-mounted path rather than
`/app/data/documents` (which would sit *inside* the named volume's mount
point and create an ambiguous overlapping-mount setup between the two
volumes — kept them at non-overlapping paths instead of relying on
Docker's most-specific-path-wins mount resolution).

`hf_cache:/root/.cache/huggingface` — same named-volume precedent as the
reference project's Sprint 10, so `docker compose down`/`up` doesn't
re-download the cross-encoder/sparse-encoder models every time.

## Sync scheduler: wired via FastAPI lifespan, not started ad hoc

Sprint 10's closing note explicitly deferred this: `build_app()` never
started `SyncScheduler` (Sprint 7), noting it "needs a proper ASGI
lifespan hook, not sketched here to avoid speculative design." This
sprint builds that hook for real: `create_app()` gains an optional
`scheduler: SyncScheduler | None = None` parameter; when provided, a
`lifespan` context manager (FastAPI's native startup/shutdown mechanism)
calls `scheduler.start()` on startup and `await scheduler.stop()` on
shutdown. Default `None` keeps every existing test (`test_api_sync.py`,
`test_api_chat.py`, `test_api_sources.py`) behavior-identical — none of
them want a real background asyncio loop running during a unit test.
`app/wiring.py::build_app()` is the one real caller that constructs a
`SyncScheduler` from `sync_intervals_from_settings(settings)` (Sprint 7's
existing helper — unchanged) and passes it through. Testable without a
real Ollama/Qdrant: FastAPI's `TestClient` used as a context manager
(`with TestClient(app) as client:`) triggers real lifespan events, so a
spy `SyncScheduler`-shaped fake can assert `start()`/`stop()` were
actually called by the app's own startup/shutdown, not just wired and
never exercised.

## README: architecture diagram + setup

A Mermaid diagram (GitHub renders these natively in a README) showing the
now-complete picture: Streamlit UI → FastAPI backend → {Qdrant, native
Ollama, the registry/sync-history SQLite file, Jaeger}, plus
Connectors → SyncManager → SyncScheduler feeding into that same backend.
Setup steps get a native-Ollama prerequisite (unchanged reasoning, now
also needed for the containerized backend to reach it) and a callout that
`NOTION_API_KEY` is optional — set it before `docker compose up` only if
the Notion connector should actually run; nothing else needs it, matching
the honest "not covered without a key" pattern used everywhere else in
this project (Sprints 1, 6, 9).

## Deliberately out of scope

`make ingest`/`app.evaluation.cli`/the Streamlit UI itself do NOT move
into containers — same reasoning the reference project used for its CLI:
they're host-side, on-demand tools (a batch job, a manual eval run, and a
UI that already runs from its own venv per Sprint 10), and containerizing
them would add mount/venv complexity this sprint's actual DoD (fresh
install + persistence) doesn't need.

## Verification plan (both required by DoD, neither assumed)

1. **Fresh install**: `docker compose down -v` (removes ALL volumes,
   including `registry_data`/`qdrant_storage`/`hf_cache`) then `docker
   compose up -d --build`. Confirm `/health` and `/health/ollama` return
   200 with a real model list (proves `host.docker.internal` resolution
   from inside the container, not assumed from the `.env.example`
   comment). Trigger a real sync (`POST /sync/filesystem` against the
   containerized backend) and a real `/chat` question end to end.
2. **Restart persistence**: with that sync history already recorded,
   `docker compose restart backend` (container recreated/restarted,
   volumes untouched) — confirm `GET /sync/filesystem/history` still
   returns the pre-restart run. This is the one that actually proves the
   named-volume decision, not just that volumes exist in the compose
   file.
