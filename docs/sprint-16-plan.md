# Sprint 16 — Re-index Failure Semantics & Hardening

## Context (read before planning, not assumed)

Sprint 15's closing note reported 365 tests green, `ruff` clean, and a
shutdown-handling gap found and fixed. It did not touch `ingest_connector`'s
actual re-index loop. [ADR 0003](adr/0003-deferred-cleanup-versioned-reindex.md)
documents Sprint 13's deferred-cleanup ordering and its measured ~12µs
duplicate-visibility window — but re-reading `app/ingestion/ingest.py`
(lines 268–294) alongside that ADR exposes a real gap the ADR doesn't
mention: the "new version fully embedded and upserted before cleanup"
guarantee is only true **within a single batch**. The embed/upsert loop
runs batch-by-batch (`for batch_start in range(0, len(chunks),
upsert_batch_size)`), with no try/except around it. If batch 1's embed
and upsert succeed but batch 2's embed raises, batch 1's chunks are
already committed to Qdrant under the new `document_version`, the
exception propagates out of `ingest_connector` unhandled, and
`delete_stale_chunks` never runs. Contents left behind: the OLD
version's points (untouched, so far so good) **plus a partial NEW
version** — some but not all of the new document's chunks. The
Sprint 13 ADR's core claim ("a failure mid-embed... leaves the OLD
version fully intact") is still true, but it's incomplete: it doesn't
disclose that a *partial* NEW version can now also be sitting there,
polluting search results with truncated/inconsistent new content
alongside the still-complete old content. This is the bug an external
review flagged and item 1 below fixes.

Confirmed directly against code (not assumed) for the other items:
- `Settings` (`app/shared/config.py`) has zero Pydantic `Field`
  constraints anywhere — `embedding_concurrency: int = 4` is a bare
  annotation. `EMBEDDING_CONCURRENCY=0` passes construction silently and
  would deadlock `asyncio.Semaphore(0)` the first time
  `embed_texts_concurrently` is called (confirmed by reading
  `app/ingestion/ingest.py::embed_texts_concurrently` — `Semaphore(0)`
  never allows any `_bounded` coroutine past `async with`, so
  `asyncio.gather` never completes for a non-empty batch).
- `app/ui/pages/chat.py` (lines 61–66) already branches on
  `has_citations` but treats every citation-free answer as the neutral
  "ℹ️ No citations" case — including a citation-free answer that ISN'T
  the model's honest `NOT_FOUND_PHRASE` ("I could not find this in the
  document.", `app/llm/prompt.py`), which is actually a silent
  hallucination (the model claimed something with no citation to back
  it at all, worse than a wrong citation).
- `QdrantStore.ensure_collection()` (`app/ingestion/qdrant_store.py`)
  only checks `SPARSE_VECTOR_NAME in (info.config.params.sparse_vectors
  or {})` on an existing collection — it never inspects
  `info.config.params.vectors[VECTOR_NAME].size` or `.distance`. A
  collection created with the right sparse config but a stale/wrong
  dense dimension (e.g. an old `768`-dim collection reused after
  switching to a different embedding model) would pass `ensure_collection`
  silently and then fail loudly and confusingly at the first `upsert`
  instead.
- `app/main.py`'s `lifespan` already runs `for hook in on_shutdown or
  []: await hook()` with no try/except — one hook raising (e.g. Notion's
  `aclose()` erroring on a half-open connection) would abort the loop
  and skip closing the Ollama/chat-provider clients that come after it
  in the list. `app/wiring.py::build_app()`'s `on_shutdown` list also
  never includes `qdrant_client` itself — only `ollama.aclose`,
  `chat_provider.aclose`, and connector `aclose`s. `QdrantClient.close()`
  is sync, not async (confirmed via `qdrant_client`'s installed
  signature), so it needs a small async wrapper to fit the hook shape.
- README's opening paragraph says "ingesting multiple document types
  (PDF, Markdown, web pages, Notion, Confluence) through a shared
  `Connector` interface" — false as written for two of five: `web_parser.py`
  exists and is tested (Sprint 6) but there is no `WebConnector` (already
  correctly disclosed in Known Limitations, just not in the intro), and
  Confluence has never been started (Sprint 16 stretch, not this sprint).
  Separately, `## Status` still says "Sprints 0–11 complete" even though
  Sprints 12–15 are done and this plan is Sprint 16.
- `scripts/benchmark_embedding_concurrency.py`'s current methodology: one
  run per (chunk_count, concurrency) pair, no warmup, concurrency levels
  always tested in the same fixed order `[1, 2, 4, 8]` (so any
  monotonic warm-up/cache effect across the whole run gets misread as a
  concurrency effect), and no variance reported at all — the README's
  "plateau within measurement noise" framing (Sprint 14 closing note)
  is asserted, not backed by a stddev number.
- `.github/workflows/ci.yml`'s lint job runs `ruff check app tests` —
  `scripts/` is never linted, confirmed by grepping the workflow file.

## Scope, in priority order

### 1. Multi-batch partial-new re-index bug (critical)

**Fix**: add `QdrantStore.delete_version(source_type, source_id,
document_version)` — deletes points matching a specific version (the
mirror image of `delete_stale_versions`, which deletes everything
*except* one version; this deletes everything *matching* one version).
Wrap `ingest_connector`'s per-document embed/upsert loop in
try/except: on any exception, call
`store.delete_version(connector.source_type, document.source_id,
content_hash)` to remove whatever partial NEW-version points made it in
across however many batches succeeded before the failure, then
re-raise the original exception unchanged (propagation behavior is
otherwise untouched — Sprint 13 already relies on "the error escapes
`ingest_connector`", and this sprint doesn't change that contract).
After rollback, the collection is back to exactly what it was before
this document's re-index attempt: only the OLD version's points,
nothing from the NEW one — restoring the ADR 0003 guarantee for the
*whole* document, not just its first batch.

**Test-first** (`tests/test_versioned_reindex.py`, new test): a document
that chunks into at least 6 pieces, `upsert_batch_size=2` (3 batches),
an `embed_fn` that succeeds for batch 1 then raises on batch 2. Assert:
(a) every one of the OLD version's points is still present with its
original text, (b) **zero** points anywhere carry the NEW
`document_version` (proving the partial batch-1 write was rolled back,
not just left alone), (c) the registry's `content_hash` is still the
OLD hash (so a retry sees this document as still "changed").

### 2. Re-measure the duplicate-visibility window honestly

The existing `test_duplicate_visibility_window_duration_is_measured_via_real_spans`
test measures from the LAST `upsert_batch` span's end to
`delete_stale_chunks`'s start — using a document that fits in a single
batch, so "last upsert_batch" and "first upsert_batch" are the same
span. That's the wrong number for the real multi-batch case: once
batch 1 of a multi-batch re-index is upserted, its NEW-version chunks
are searchable immediately, side by side with the (still fully intact)
OLD version — and stay that way until `delete_stale_chunks` finally
runs after the LAST batch. The true window is measured from the
**first** `upsert_batch` span's end to `delete_stale_chunks`'s start,
and only equals the old number when there's exactly one batch.

**Fix**: new test using a real multi-batch document (`upsert_batch_size`
small enough to force 3+ batches) measuring `first upsert_batch end` →
`delete_stale_chunks start`, printed and asserted `>= 0` the same way
the existing test does (not tightly bounded — it's an observed real
number). Keep the original single-batch test as-is (it's still a valid,
correct measurement of the single-batch case) and add the new
multi-batch one alongside it, not replacing it — both are real, they
just measure different scenarios. README's "~12 microseconds" claim
gets updated with whichever real number the new multi-batch measurement
produces, and the prose is adjusted to state plainly that the window
scales with re-index duration for multi-batch documents (more batches =
more time between the first partial-new-version write and final
cleanup), not a fixed ~12µs regardless of document size.

### 3. Config validation

Add `pydantic.Field(ge=1, le=32)` to `embedding_concurrency` (32 is a
generous ceiling — 8 already showed zero measured benefit over 4 per
Sprint 14's benchmark; 32 just needs to be "clearly beyond any sane
value" for the constraint to matter, not a tuned number) and
`Field(gt=0)` to `filesystem_sync_interval_seconds` /
`notion_sync_interval_seconds` (an interval of 0 or negative has no
sane meaning for a periodic scheduler — `SyncScheduler`'s loop would
either busy-spin or misbehave). Pydantic raises `ValidationError` at
`Settings()` construction time, i.e. at process startup, which is the
whole point — fail loud before the deadlock has a chance to happen, not
after. Test: `EMBEDDING_CONCURRENCY=0` via `monkeypatch.setenv` +
`pytest.raises` around `Settings()`, mirroring the existing
`test_generation_provider_rejects_unknown_value` pattern already in
`tests/test_config.py`.

### 4. UI citation-free distinction

`app/ui/pages/chat.py`, the `if not grounding_event["has_citations"]:`
branch: check `full_answer.strip() == NOT_FOUND_PHRASE` (imported from
`app.llm.prompt`). If it matches, keep today's neutral `ℹ️ No relevant
source found` framing (a legitimate "not found" answer needs no
citations). If it doesn't match, switch to `⚠️ Answer contains no
verifiable citations` — the model asserted something with zero
citations backing it, which per `grounding.py`'s own docstring is "the
most dangerous hallucination shape: no citation tag at all to even
question." No test infrastructure exists for the Streamlit pages today
(confirmed: no `tests/test_chat_page.py` or similar) — this is a
plain-text branch change, verified by reading the diff and by real
browser interaction (ask a question that legitimately has no answer in
the corpus vs. one that provokes a no-citation non-`NOT_FOUND_PHRASE`
response) rather than a unit test, consistent with how the rest of the
Streamlit pages are verified in this project (browser only, no
Streamlit-specific test harness was ever built).

### 5. Complete Qdrant schema validation

`ensure_collection()`: after confirming the sparse vector exists, also
check `info.config.params.vectors[VECTOR_NAME].size == EMBEDDING_DIM`
and `.distance == qmodels.Distance.COSINE`; raise the existing
`UnexpectedCollectionSchemaError` (extended message) on either
mismatch, same "don't touch it, tell the human" policy as the sparse
check. Test-first against `QdrantClient(":memory:")`: create a
collection with the right sparse config but a wrong dense size (e.g.
384 instead of 768), assert `ensure_collection()` raises without
deleting; same for wrong distance metric (e.g. `EUCLID` instead of
`COSINE`).

### 6. Failure-safe shutdown

`app/main.py`'s `lifespan`: wrap each `on_shutdown` hook call in its
own try/except, logging (not raising) on failure, so one broken hook
can't block the rest from running. Test-first
(`tests/test_app_lifespan.py`, extending the Sprint 15 pattern): a
hook list `[raising_hook, tracking_hook]` where the first raises —
assert `tracking_hook` still ran. `app/wiring.py::build_app()`: add
`qdrant_client` to the `on_shutdown` list via a small async wrapper
(`QdrantClient.close()` is sync) so all four real long-lived clients
(Ollama embed, chat provider, Notion, Qdrant) get closed on shutdown,
not three.

### 7. README consistency fixes

Intro paragraph: rephrase to "PDF, Markdown, and Notion through a
shared `Connector` interface, plus a standalone web-page parser
(`app/parsing/web_parser.py`) not yet wired into a connector" — stops
implying Confluence exists and stops implying the web parser has sync
support it doesn't. `## Status`: "Sprints 0–11 complete" → "Sprints
0–15 complete", with the bullet list re-checked against what's actually
true today (tracing, evaluation, UI, Docker Compose, grounding fix,
CI, versioned re-index, embedding concurrency, ADRs/shutdown-hooks —
all real, all already covered by their own README sections elsewhere,
so the Status bullets just need the count and any since-changed claims
fixed, not a rewrite).

### 8. Benchmark methodology hardening

`scripts/benchmark_embedding_concurrency.py`: add one untimed warmup
call per chunk-count before the timed runs (rules out first-request
connection/model-load overhead skewing concurrency=1's numbers low);
run each (chunk_count, concurrency) pair 3 times and report
mean/median/stddev, not a single sample; use `random.shuffle` on the
concurrency-level order per chunk-count-and-repeat (rules out any
monotonic drift across the whole script's runtime being misattributed
to concurrency itself). This is a **manual, Ollama-requiring script**
(same as Sprint 14 — CI has no Ollama), so it is run for real against
native Ollama during this sprint if available, exactly like Sprint 14
did; if it isn't reachable at implementation time, that's stated
explicitly and honestly in the closing note (not silently skipped) and
the README table is left with a note that the stats-hardened numbers
are pending a re-run, rather than fabricating variance figures.

### 9. CI lint scope

`.github/workflows/ci.yml`: `ruff check app tests` → `ruff check app
tests scripts`. Run `ruff check scripts` locally first to fix whatever
it finds before landing the workflow change, so CI doesn't immediately
go red on the next push.

## Rules carried over

- Test-first, especially item 1's rollback test — it's the one thing
  this sprint cannot get away with asserting from reading code alone.
- No AI co-author line in commits.
- Closing note must include: the real new duplicate-window measurement
  (a number, not "roughly the same"), the rollback behavior's proof,
  and the benchmark's actual new result (or an honest "Ollama
  unreachable, not re-run" if that's what happened).

## Definition of Done

Multi-batch partial failure scenario is proven to roll back
(test-verified, not just implemented); duplicate window re-measured
with a real multi-batch document; config validation rejects
out-of-range values at startup; UI distinguishes citation-free
NOT_FOUND from citation-free-and-not: the latter now warns; Qdrant
schema validation checks dense dim + distance, not just sparse
presence; shutdown hooks are failure-isolated and `QdrantClient` is
among them; README's connector claims and Status sprint count are
accurate; benchmark methodology has repeats/warmup/randomization and
reports variance; CI lints `scripts/` too; full suite + `ruff` clean.
