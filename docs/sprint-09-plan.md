# Sprint 9 Plan — Evaluation

## Goal

A golden-set-based quality harness, runnable by command, that reports
retrieval + generation metrics broken down by content format (PDF vs.
Markdown — see "content_type vs source_type" below), reusing
`production-rag-platform`'s proven DeepEval + local-judge approach rather
than re-litigating the RAGAS-vs-DeepEval decision.

## RAGAS: not re-attempted

`production-rag-platform` tried RAGAS first and dropped it for a real,
already-documented dependency conflict (not a taste choice) — that
elimination is treated as settled fact here. This sprint starts directly
from DeepEval + a local Ollama judge model, matching
`app/evaluation/generation_metrics.py`'s reference design in that repo.

## Judge model: qwen2.5:7b-instruct

Ported unchanged from production-rag-platform, which found — in real
testing — that `qwen2.5:3b-instruct` produced an internally inconsistent
verdict/reason pair as a judge (the reasoning text disagreed with the
numeric verdict); 7B fixed it on the same test. This project already has
`qwen2.5:7b-instruct` pulled (it's also the default `ollama_model` for
generation — see below for why generation uses a *different*, smaller
model for the golden-set run despite that).

## Two real bugs from production-rag-platform's Sprint 9, and how this
## harness avoids repeating them

**1. Harness model-switching thrashing (interleaved judge/generation
calls forced Ollama to reload the model almost every call, turning an
~11-minute expected run into 40+ minutes).** Avoided structurally, not
situationally: `run_evaluation()` is two-phase — phase 1 runs
retrieval+generation for *every* question first (one model loaded the
whole time), phase 2 runs *all* judge scoring second (the judge model
loaded once, for the whole phase). This is ported directly from
`production-rag-platform/app/evaluation/harness.py`'s `run_evaluation()`.
It costs nothing when generation and judge happen to be the same model,
and is load-bearing the moment they differ — which is a real, supported
configuration here (`Settings.generation_provider`/`ollama_model` are
user-configurable), so the phase separation is kept unconditionally
rather than only added if today's default config would trigger the bug.
To actually exercise the thrash-prone scenario (not just carry the
structure untested), the golden-set run in this sprint deliberately uses
`qwen2.5:3b-instruct` for generation and `qwen2.5:7b-instruct` for
judging — two distinct models, like production-rag-platform's own setup.

**2. `OllamaClient`'s too-short timeout (`httpx.ReadTimeout` mid-call
under a 7B judge's sustained load).** Investigated fresh rather than
assumed fixed, because there are actually *two* separate HTTP paths in
play here, and only one of them was previously touched:

- This project's own `app/llm/ollama_client.py::OllamaClient` (used for
  RAG generation) already carries a `DEFAULT_TIMEOUT_SECONDS = 120.0`
  fix from Sprint 0, with a comment citing this exact
  production-rag-platform bug. No new work needed there.
- DeepEval's judge wrapper (`deepeval.models.OllamaModel`, used by
  `FaithfulnessMetric`/`AnswerRelevancyMetric`) does **not** go through
  `OllamaClient` at all — it uses the official `ollama` PyPI package's
  own `Client`/`AsyncClient` internally. This is a code path this
  project had never inspected before. Traced its source (`ollama`
  v0.6.2): `BaseClient.__init__(..., timeout: Any = None, ...)` passes
  `timeout` straight through to the underlying `httpx.Client`. Verified
  directly (not assumed) what `httpx.Client(timeout=None)` actually does:

  ```python
  >>> httpx.Client(timeout=None).timeout
  Timeout(timeout=None)
  ```

  Per httpx's own semantics, `Timeout(None)` disables the timeout
  entirely (no time limit, not "fall back to httpx's 5s default"). So
  DeepEval's judge HTTP path cannot reproduce a "timeout too short" read
  error — its default is the opposite failure mode (unbounded wait), and
  a 7B judge call finishing in the tens-of-seconds range on this machine
  is nowhere near a real problem worth guarding against speculatively. No
  explicit timeout override is added to `build_default_metrics()`'s
  `OllamaModel(...)` construction — there is nothing to fix here, and the
  original comment risk ("OllamaClient's short timeout") turns out to
  only ever have applied to this project's *own* client, which was
  already fixed in Sprint 0.

## Retrieval metrics: generalized location scheme

production-rag-platform's `Location = tuple[int, int]` (page, paragraph)
is PDF-only and doesn't fit this project's multi-source grounding model.
This project's true chunk identity is the `(source_type, source_id,
location)` triple already used by `app/llm/grounding.py` for citation
checking (`location` itself computed by
`app/llm/citation_location.py::location_for()` — a heading path string
for Markdown, `"page/paragraph"` for PDF). `app/evaluation/retrieval_metrics.py`
uses that same triple and the same `location_for()` function, so a golden
question's `expected_locations` and a retrieved chunk's derived location
are checked against *exactly* the same identity `grounding.py` already
uses to validate real citations — no separate, drifting definition of
"which chunk is this." Precision/recall stay classic set-overlap
(deterministic, no judge needed — ground truth locations make this exact,
unlike faithfulness/relevancy which need a judge because there's no
ground-truth *text* to diff against).

## content_type vs source_type — which one the breakdown is keyed on

The DoD/PLANNING.md wording ("kaynak tipi bazında kırılım") could be
read as `source_type` (the connector — `filesystem`, `notion`), but the
concrete ask in this sprint's instructions is explicit: *"PDF sorularında
mı, Markdown sorularında mı sistem daha zayıf"* — that's a **format**
question, not a **connector** question. In this project's architecture
(Sprint 3), `source_type` identifies the connector and `content_type`
identifies the format — both PDF and Markdown questions here come from
the *same* connector (`LocalFilesystemConnector`, `source_type="filesystem"`),
so breaking down by `source_type` would put them in one indistinguishable
bucket and silently fail to answer the actual question asked. Each
`GoldenQuestion` therefore carries a `content_type: str` field
(`"pdf"` / `"markdown"`), and `build_report()` computes the same mean
metrics once globally and once more per distinct `content_type` value
present in the results.

## Golden set: real content only

- **PDF**: reuses `tests/fixtures/golden_source.py`'s existing "Nimbus
  Cloud Storage" handbook builder (6 pages, already used elsewhere in
  this project's tests) — real, deterministic, already-verified content.
- **Markdown**: a new fixture, `tests/fixtures/golden_markdown_source.py`,
  building a small but real multi-heading "Nimbus CLI" reference doc
  (install steps, auth, sync command flags, troubleshooting) with the
  same "every fact traceable to one exact heading path" discipline as the
  PDF fixture.
- **Notion**: excluded. `NOTION_API_KEY` is unset on this machine (same,
  already-documented gap as Sprints 1 and 6) — no Notion questions are
  added to the golden set, and this is stated plainly rather than
  papered over with a mocked substitute.

Both fixtures are ingested into a real (non-`:memory:`) local Qdrant
collection via the real `ingest_connector()` pipeline and a real Ollama
embedding call — the golden set's `expected_locations` are read back from
what actually got chunked/embedded (via `location_for()` on the real
chunk payloads), not guessed ahead of ingestion.

## Harness design

`app/evaluation/`:

- `retrieval_metrics.py` — `RetrievalMetrics` dataclass,
  `compute_retrieval_metrics(retrieved, expected_locations)`, using the
  `(source_type, source_id, location)` triple.
- `generation_metrics.py` — `compute_generation_metrics(...)` (builds one
  `LLMTestCase` per question, runs each configured metric), and
  `build_default_metrics(judge_model_name, base_url)` wiring
  `FaithfulnessMetric`/`AnswerRelevancyMetric` against
  `deepeval.models.OllamaModel`.
- `harness.py` — `GoldenQuestion` (adds `content_type` vs.
  production-rag-platform's version), `QuestionResult`,
  `load_golden_set(path)`, `run_evaluation(...)` (two-phase, with a
  `progress_callback` for both phases — ported pattern), `build_report(results)`
  (global means + per-`content_type` means + not-found accuracy).
- `cli.py` — `python -m app.evaluation.cli --golden-set <path>` wires real
  `OllamaProvider`/`EmbeddingProvider`, real `QdrantStore` +
  `SparseEncoder` (+ optional `CrossEncoderReranker`), builds
  `search_fn`/`generate_fn` closures around `app.retrieval.search.search`
  / `app.llm.generate.stream_answer`, and prints the JSON report —
  satisfies "golden set komutla çalıştırılabiliyor."

## Test-first scope

Per the instructions, metric *computation* logic is unit-tested
(retrieval precision/recall math, generation metric aggregation, two-phase
ordering via fakes, report breakdown math including the `content_type`
split) — the real, live golden-set run itself (real Ollama, real Qdrant,
real 7B judge) is verified as a manual e2e run with captured, honest
output in the Sprint 9 closing note, not asserted in CI (too slow/
environment-dependent, consistent with how Sprint 8's real-Jaeger check
was handled).
