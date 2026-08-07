# Architecture Decision Records

Short, focused records of real design decisions that used to live as
multi-sprint narrative comments inline in the code (Sprint 15's cleanup —
see its closing note in [../PLANNING.md](../PLANNING.md)). Each one is
grounded in the actual sprint closing note(s) that made the decision, not
reconstructed after the fact.

Format: Context / Decision / Consequences.

| ADR | Decision |
|---|---|
| [0001](0001-connector-interface-is-async.md) | `Connector` Protocol methods are `async def` |
| [0002](0002-incremental-sync-three-phase-registry-diff.md) | Incremental sync: three-phase diff against the registry |
| [0003](0003-deferred-cleanup-versioned-reindex.md) | Zero-downtime versioned re-index with deferred cleanup (not atomic) |
| [0004](0004-single-trace-per-sync-run.md) | One Jaeger trace per sync run, via a top-level span |
| [0005](0005-real-wiring-pulled-forward.md) | Real component wiring built in Sprint 10, not Sprint 11 |
| [0006](0006-scheduler-wired-via-fastapi-lifespan.md) | `SyncScheduler` started via FastAPI's `lifespan` |
