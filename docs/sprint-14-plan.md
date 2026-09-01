# Sprint 14 Plan — Ingestion Performance

## Goal

Fix a naming mismatch that could mislead a future reader, add real
bounded concurrency for embedding calls (currently strictly sequential —
`[await embed_fn(chunk.text) for chunk in batch]`), and pick a default
concurrency level from a real benchmark against native Ollama rather than
a guess.

## 1. `batch_size` → `upsert_batch_size`

Confirmed by reading `app/ingestion/ingest.py`: `batch_size` controls how
many chunks are grouped into one `store.upsert_chunks(...)` call — it has
never controlled embedding batching (`embed_fn` is called once per chunk,
not once per batch). The name is misleading for exactly the reason this
sprint exists: someone tuning "batch_size" for embedding throughput would
be tuning the wrong knob entirely. Renamed to `upsert_batch_size`
everywhere it appears (`ingest_path`, `ingest_connector`, the loop
variable, span attribute names stay `upsert.chunk_count`/`embed.chunk_count`
— those were already correctly scoped). No caller passes it by keyword
(checked via grep across `app/` and `tests/`), so this is a safe,
mechanical rename with zero behavior change.

## 2. Bounded embedding concurrency

New `embed_texts_concurrently(texts: list[str], embed_fn: EmbedFn,
concurrency: int) -> list[list[float]]` in `app/ingestion/ingest.py`:
an `asyncio.Semaphore(concurrency)` guards each `embed_fn` call, all
launched together via `asyncio.gather` (which preserves input order in
its results — `dense_vectors[i]` still corresponds to `batch[i]`, no
re-sorting needed). Shared by both `ingest_path` and `ingest_connector`'s
per-batch embed step, replacing the sequential list comprehension.
`sparse_encoder.embed_document()` stays sequential and untouched — it's
local CPU work (FastEmbed BM25), not a network call, nothing to overlap.

New `Settings.embedding_concurrency` — default deliberately NOT guessed;
set from the benchmark's actual result (see below), matching this
project's own precedent for tunables discovered by measurement rather
than assumption (Sprint 9's `RERANK_TOP_N`, Sprint 0's chunk size).

### Proving concurrency is real, not just "finished faster"

A wall-clock-only test ("N concurrent calls took less time than N
sequential calls") doesn't distinguish real bounded parallelism from,
say, an accidentally-unbounded `gather` or a semaphore that's a no-op.
The test uses a fake `embed_fn` that increments an in-flight counter on
entry, records the running max, sleeps briefly, then decrements on exit
— this directly measures how many calls were ACTUALLY in flight
simultaneously, and asserts it equals the configured concurrency exactly
(not "at least 1", not "less than the batch size by coincidence").

## 3. Benchmark: real Ollama, not mocked, and not assumed to scale

Task's explicit warning taken seriously: a single native Ollama instance
serving `nomic-embed-text` might not get faster past some concurrency
level — it could plateau (single model, likely serializing internally)
or even get worse (request queuing/context-switching overhead exceeding
any real parallelism gain). The benchmark script
(`scripts/benchmarks/benchmark_embedding_concurrency.py`, not part of the automated
test suite — same reasoning as Sprint 12's CI decision: no Ollama in CI,
and a benchmark isn't a correctness test) runs concurrency levels 1, 2,
4, 8 against real chunk counts 10, 100, 1000, each combination timed with
real wall-clock duration and reported as chunks/sec. Whatever the actual
shape of the result — monotonic speedup, a plateau, or degradation past
some point — gets reported honestly in the closing note and used
directly to justify the chosen default, not fitted to a preconceived
"more concurrency is always better" narrative.

## 4. README

A new throughput section reports the real benchmark table (chunks/sec by
concurrency level and chunk count) plus a real sync run's breakdown
(total duration, embedding duration, Qdrant upsert duration) at the
chosen default concurrency — using the OTel spans already instrumented
since Sprint 8 (`embed_batch`, `upsert_batch`) rather than separate
manual timing.
