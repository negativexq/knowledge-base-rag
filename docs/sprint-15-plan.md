# Sprint 15 Plan — Documentation and Cleanup

## Goal

No new features, no behavior changes to tested code paths. Reduce
sprint-history comment bloat by extracting the real multi-sprint design
narratives into ADRs, fix the one confirmed stale comment (plus a scan
for others), fill in two known Known Limitations gaps, and check/fix
FastAPI shutdown handling for long-lived clients.

## 1. Which comments become ADRs

Scanned every `.py` file under `app/` for "Sprint N" mentions (22 files).
Most are single, brief pointers to one sprint's decision ("(Sprint 7)")
— normal, useful inline context, not bloat, left alone. Four files
contain genuine multi-sprint *narratives* — a comment describing how a
decision evolved across several sprints inline, which is exactly what
the task calls out ("Sprint 4'te şöyleydi, Sprint 6'da böyle değişti"):

- `app/ingestion/ingest.py::ingest_connector`'s docstring — narrates
  Sprint 0→3→4→6→8→13 across ~45 lines, covering four separate real
  decisions (three-phase incremental sync, connector protocol going
  async, one-span-per-sync-run tracing, deferred-cleanup re-index).
- `app/main.py::create_app`'s docstring — narrates Sprint 7→10→11 (who
  wires real components, and when the scheduler got started).
- `app/ui/trace_client.py::fetch_trace_spans`'s docstring — narrates
  Sprint 8→12 (why the root-span-specific retry exists).
- `app/connectors/base.py`'s `Connector` Protocol docstring — narrates
  Sprint 3→4 (why the three methods are `async def`).

Six ADRs extracted, each grounded in the actual `docs/PLANNING.md`
closing note for the sprint(s) that made the decision (not invented):

1. `0001-connector-interface-is-async.md` (Sprint 3 → Sprint 6)
2. `0002-incremental-sync-three-phase-registry-diff.md` (Sprint 4)
3. `0003-deferred-cleanup-versioned-reindex.md` (Sprint 13)
4. `0004-single-trace-per-sync-run.md` (Sprint 8, retry fix in Sprint 12)
5. `0005-real-wiring-pulled-forward.md` (Sprint 7 plan → Sprint 10 → 11)
6. `0006-scheduler-wired-via-fastapi-lifespan.md` (Sprint 7 → 10 → 11)

Each docstring above is condensed to what a reader actually needs at the
call site (what it does, one-line why) plus a `See docs/adr/000N-....md`
pointer — the full historical narrative moves to the ADR, not deleted.

## 2. Stale comment: confirmed and scanned for siblings

`tests/test_ingest_connector.py:151` — `# unchanged re-run — this sprint
doesn't skip, but the registry itself must still report "unchanged"
correctly` — written when this test file was created (Sprint 3, before
incremental sync existed) and never updated. `ingest_connector` has
skipped unchanged documents since Sprint 4
(`if not changed: files_skipped += 1; continue`) — confirmed by reading
the current code, not assumed. Fixed to describe what's actually true
now.

Scanned the rest of `app/` and `tests/` for the same failure class
(`grep` for "doesn't yet", "not yet", "for now", "currently", "at the
moment", "this sprint doesn't/does") — every other hit describes
something still true today (checked each individually against current
code), so this was the only real stale comment found.

## 3. Known Limitations additions

- **Process-local sync lock**: `SyncManager._running` (Sprint 7) is a
  plain in-memory `dict` on one `SyncManager` instance — confirmed by
  reading `app/sync/manager.py`. The Dockerfile currently runs a single
  `uvicorn` process (`CMD ["uvicorn", "app.server:app", ...]`, no
  `--workers`), so this is a *latent*, not currently-manifesting, gap —
  but if the backend were ever scaled to multiple worker processes or
  replicas, each would have its own independent `_running` state, and
  the "reject a second concurrent sync of the same connector" guarantee
  (Sprint 7's whole point) would silently stop holding across processes.
- **Notion connector detail sharpened**: the existing Known Limitations
  bullet said "never tested against a real workspace"; true but
  incomplete. `app/connectors/notion.py`'s own comment already states it
  plainly: "Deliberately not recursive into nested children" and lists
  exactly which block types are skipped (anything outside headings +
  paragraph/list/quote/to_do/code — images, tables, dividers, embeds,
  etc. carry no citable text and are silently dropped). Added to the
  README bullet directly, not just "mock-tested" — the recursion/coverage
  gap is real independent of whether a real workspace was ever used.
- The stale "Sprint 12" reference in the existing "No Confluence
  connector" bullet (renumbered to Sprint 15 stretch, then Sprint 16 as
  of this sprint) gets corrected too — found while auditing this section
  for other drift.

## 4. Shutdown handling: a real, confirmed gap

`app/main.py::create_app()`'s `lifespan` only calls `scheduler.start()`/
`scheduler.stop()` (Sprint 11). It does not close any of the long-lived
clients `app/wiring.py::build_app()` constructs:

- `OllamaClient` used for embedding (`ollama` in `build_app`) — wraps an
  `httpx.AsyncClient`, already has `aclose()` (Sprint 0), never called.
- `OllamaClient`/`ClaudeProvider` used for chat generation
  (`build_chat_dependencies`'s `chat_provider`, a *second*, separate
  instance from the embedding one) — both already have `aclose()`
  (Sprint 0/1), never called.
- `NotionConnector`, when `notion_api_key` is set — owns its own
  `httpx.AsyncClient`, already has `aclose()` (Sprint 6), never called.

All three already implement `aclose()` correctly — the gap is purely
that nothing in the real app lifecycle ever calls it. Fixed by giving
`create_app()` an optional `on_shutdown: list[Callable[[], Awaitable[None]]]`
parameter (same optional-hook pattern already used for `scheduler`),
invoked after `scheduler.stop()` during lifespan shutdown; every existing
test passes `None` (default), so no existing test's behavior changes.
`build_app()` collects the real hooks: the embedding `OllamaClient`, the
chat `chat_provider` (whichever provider `get_chat_provider` returned),
and every constructed connector's `aclose` if it has one (currently just
Notion; `LocalFilesystemConnector` has no such resource).

Verified for real (not just structurally): a scratch script constructs
the same real components `build_app()` does (real `OllamaClient`,
`NotionConnector` with a fake key), runs the lifespan's shutdown path,
and confirms all `aclose()` calls complete without error — safe to call
even when no request was ever made through the client.
