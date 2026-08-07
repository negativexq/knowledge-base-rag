# 0006 — `SyncScheduler` started via FastAPI's `lifespan`, not ad hoc

## Context

Sprint 7 built `SyncScheduler` (a per-connector `asyncio` loop calling
`SyncManager.trigger_sync()` on a fixed interval) but never started it
anywhere real — `app/main.py::create_app()` didn't know about it, and no
code path constructed one against real components. Sprint 10's UI work
needed `build_app()` to exist ([0005](0005-real-wiring-pulled-forward.md))
but deliberately did *not* start the scheduler there either — that
sprint's DoD only required manual "sync now" to work, and starting a
real background loop is exactly the kind of thing that needs a proper
ASGI lifecycle hook, not a bare function call at import time.

## Decision

Give `create_app()` an optional `scheduler` parameter
(`SchedulerProtocol` — `start() -> None`, `async def stop() -> None`,
kept as a `Protocol` rather than importing `SyncScheduler` directly so
tests can pass a plain spy). When provided, a FastAPI `lifespan`
async context manager calls `scheduler.start()` before the `yield`
(startup) and `await scheduler.stop()` after it (shutdown). Every
existing test passes `scheduler=None` (the default), so none of them get
a real background loop running during a unit test.

`app/wiring.py::build_app()` is the one real caller: it constructs a real
`SyncScheduler` from `sync_intervals_from_settings(settings)` (Sprint 7's
existing helper, unchanged) and passes it through.

## Consequences

- Verified two ways, not just one: a unit test
  (`tests/test_app_lifespan.py`) uses `TestClient` as a context manager
  (which triggers real ASGI lifespan events) with a spy scheduler to
  prove `start()`/`stop()` are actually called by the app's own
  lifecycle, not just wired and never exercised; separately, a real
  container run with a shortened `FILESYSTEM_SYNC_INTERVAL_SECONDS`
  showed a `trigger=scheduled` sync run appear in `sync_runs` with zero
  manual API calls.
- The same `lifespan`/optional-hook pattern was reused directly in
  Sprint 15 for closing long-lived HTTP clients on shutdown
  (`on_shutdown`) — the scheduler's `start`/`stop` shape was the
  precedent, not a one-off.
