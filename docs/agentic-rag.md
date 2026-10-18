# PydanticAI agentic RAG

The optional agent replaces answer orchestration while retaining production
retrieval, reranking, section-aware evidence, arithmetic/operand binding,
visual reading and confirmation, and support-ID validation. The original path
remains the default until paired benchmark measurements justify a rollout.
There is one research agent, a stateless scope verifier, and no application
graph or multi-agent research workflow.

Enable with `AGENTIC_RAG_ENABLED=true` and `SUPPORT_IDS_ENABLED=true`. Generation
uses the configured provider/model: native OpenAI Responses, Anthropic, or the
Ollama OpenAI-compatible endpoint. The pinned PydanticAI 1.107.7 release is
compatible with the existing SDK pins. Its transitive `pydantic-graph`
dependency does not introduce a graph into the application.

## Request flow

1. Existing search/reranker and section expansion produce the initial evidence.
2. A request-local, append-only ledger assigns stable `E1.S1` support IDs.
   Complete blocks fitting the evidence budget are admitted in retrieval order.
   Unauthorized/hidden blocks, duplicates and blocks exceeding the remaining
   budget are excluded. This can reduce visible context when budgets are tight.
3. The agent answers immediately or chooses tools. An empty first search can
   still be followed by an alternate query under the same authorization scope.
4. The output validator checks the existing support-ID contract and validators.
   Rejections return reason codes so the agent can correct, search or abstain.
5. The candidate is checked again by the existing release path. Refreshed source
   cards and the final support-ID map arrive before any answer text is released.

Tools:

| Tool | Behavior |
| --- | --- |
| `search` | Calls the request's existing scoped retrieval and reranker, then section expansion; admits new evidence within the ledger budget. |
| `read_document_section` | Reopens the already admitted evidence block containing a known support ID. |
| `navigate_document` | Lists headings, searches document terms, reads unseen sections/pages or adjacent passages. Keeps the anchor source/version and request scope; newly admitted passages receive stable support IDs. |
| `calculate` | Evaluates restricted arithmetic and verifies every operand against cited evidence with the existing calculator. |
| `resolve_calculation` | Uses the existing operand planner, binding checks and deterministic computation. Missing operands must be searched through `search`, keeping IDs and budgets consistent. |
| `read_pages` | Uses the existing page reader and separate claim/condition check for an admitted source. The final answer selects the verified reading without rewriting it. |

Search has no tenant, ACL, collection or document-scope argument. Those values
are captured by the application, including question-document scope in the
MMLongBench runner. New evidence retains provenance and is never promoted to
instructions. Disabled tools are removed from the model's available tools.
Derived and visual tools follow the existing feature flags. Operand/visual
model calls share the agent's request/token budgets; SDK retries on the native
agent clients are disabled. Tool-provider usage is counted when its existing
adapter supplies usage metadata.

Visual answers retain the existing independently confirmed, explicitly marked
page-image contract. They are not presented as text-validated support claims.
All released text answer parts still pass the existing support-ID validators.
The model's ability to interpret a question, detect sufficient evidence, or
read an image is not guaranteed by structured output.

## Bounds and tracing

| Setting | Default |
| --- | ---: |
| `AGENTIC_MAX_REQUESTS` | 6, including resolver/visual calls |
| `AGENTIC_MAX_TOOL_CALLS` | 8 |
| `AGENTIC_MAX_TOKENS` | 60000 cumulative reported input/output tokens |
| `AGENTIC_TIMEOUT_SECONDS` | 120 for the agent run and tools |
| `AGENTIC_OUTPUT_RETRIES` | 2 |
| `AGENTIC_EVIDENCE_TOKEN_BUDGET` | 24000, capped at half the configured context window |

The context cap leaves room for instructions, tool schemas and subsequent
messages; it is not an exact provider context-size calculation. Large histories
can still reach a provider limit, in which case the run fails closed. Token
usage limits are checked around calls; the current call can exceed the remaining
token budget before its reported usage is available.

Budget exhaustion, timeout, provider errors and exhausted validation retries
release no draft. They produce an application abstention with
`AGENT_BUDGET_EXCEEDED`, `AGENT_TIMEOUT` or `AGENT_RUN_FAILED`. Tool choices,
request/token counts and failure codes appear in metadata and the optional
forensic capture's `agentic` stage. No raw question, evidence, tool arguments or
model conversation is added to normal tracing. Native clients close after each
request. The deployment environment and existing `.env` remain unchanged.

## Measurement and rollout

Use new output directories for every configuration. Keep the same dataset
revision, corrected labels, model, corpus, retrieval scope, reranker, feature
flags and validator version between the baseline and challenger. In particular,
compare against the latest version-guard fix, not just an older saved report.
Do not reuse existing result/checkpoint directories with changed settings.

For TechQA, run `scripts/benchmarks/run_techqa_production.py` with the pinned
`--parquet`, `--skip-ingest` and a fresh `--out`; run once with
`AGENTIC_RAG_ENABLED=false` and once with `true`. Grade both result files blindly
using the same semantic rubric. Existing semantic scores must not be reused
for newly generated answers.

For MMLongBench, run `scripts/benchmarks/run_mmlongbench_pilot.py` with
`--manifest artifacts/mmlongbench-v2/manifest.json`,
`--labels data/benchmarks/mmlongbench-doc-v2/samples.json`, `--skip-ingest`
and fresh `--out` directories for the two values of `AGENTIC_RAG_ENABLED`.
Keep the established question-document scope; use `--open-corpus` only for a
separate, explicitly labeled experiment. `--no-generation` disables the agent
too, so retrieval-only runs make no model calls.

Report correct, partial, materially incorrect and unavailable answers; refusal
accuracy on unanswerable questions; validator failures, citations and ACL
leaks; and request/token counts and latency. Inspect per-question gains/losses
and repeat variable cases. Existing MMLongBench scoring is a lenient numeric/
contains match, not the official score. Previously inspected holdout rows are
regression data, so improvements also need a fresh untouched evaluation set
before claiming generalization.

Validation so far: deterministic tests exercise the real PydanticAI loop,
scoped follow-up search, calculation, operand resolution, visual selection,
validation retries, budget/timeout failures and final release checks. A native
`gpt-6-luna` synthetic-evidence smoke call passed. These establish integration,
not an improvement on TechQA or MMLongBench; a paired full benchmark run and
semantic grading remain necessary before enabling the feature by default.


## Research workspace features

The Research toolbar's **Compare documents** control scopes a question to two
through five selected documents. When the agent returns a comparison, each cell
must cite its own source and pass the existing validators. The UI renders a
citation-linked table; Markdown export preserves its aspects and footnotes.
A missing cell does not assert that a feature is absent. With the agent disabled,
the same scope can be used by the original answer path, which returns ordinary
text rather than the agent comparison contract.

When ambiguity requires user input, the agent may return a `clarification`
outcome with choices. It contains no answer draft. A reply starts a new,
authorized request with the original question, reply and source scope. There is
no suspended provider session or server conversation to resume. The original
permissions are re-evaluated on each request. Clarification replies and completed
comparison results are included in the existing browser research history and
export. Benchmark runners save clarification outcomes as unanswered questions;
they do not invent a user reply or count them as correct answers.

Research activity lists operation names and running/completed/retrying/failed
states through SSE `research_progress` events, not model reasoning or raw tool
arguments. Closing the response or cancelling in the composer closes the nested
streams and cancels pending agent work. Already issued external operations cannot
be undone. The client ignores late events after cancellation. SSE events retain
their type and content when transport chunks split a frame at arbitrary bytes.

**Read full context** on a source card, or opening a document in Knowledge, shows
a text reader backed by the active Qdrant index. It can list headings, find terms,
read sections/pages and fetch surrounding passages without embeddings or an LLM.
It displays the evidence version, last synchronization and a version mismatch
when registry metadata is available. This is indexed text, not a PDF page-image
viewer. Manually viewed passages do not retroactively become verified evidence
for an earlier answer.

Document reads preserve source type, source ID and document version. The service
applies the existing server-owned tenant ACL and chat source scope and verifies
returned payloads again. Reads scan at most 2000 chunks, paginate up to 50
results, and return whole passages within a 60000-character response budget.
`scan_limited`, `has_more` and `next_offset` make incomplete results visible. The API also enforces server-managed user/group document grants; connector-native
permissions are not synchronized automatically.

### Answer feedback

**Report an issue** saves a selected/entered claim, issue category, explanation,
question/answer snapshot, citation IDs and optional trace ID. The snapshot is
explicitly user-submitted and never reintroduced as trusted retrieval evidence.
The `/feedback` page shows a user's own reports; OPERATOR/ADMIN users can review
only their tenant's reports, assign triaged/resolved/dismissed status and save a
reviewer note. Submitted snapshots are stored on the server, unlike the existing
browser-local research sessions.

Set `RESEARCH_FEEDBACK_DB_PATH` to a persistent SQLite path (default
`data/research-feedback.db`). Treat this database as application data: it contains
submitted question and answer text. This implementation does not automatically
train on reports or provide a retention scheduler.

Authenticated endpoints:

- `POST /research/documents/read`: versioned document reference plus read action.
- `POST /research/feedback`: submit a bounded user report; shares the chat rate limiter.
- `GET /research/feedback/mine?offset=0`: a user's reports in pages of 50.
- `GET /research/feedback?status=open&offset=0`: tenant reviewer queue (OPERATOR+).
- `POST /research/feedback/{id}/review`: update a report's review (OPERATOR+).

The new workflow was developed without live LLM calls. Tests use FunctionModel,
mock transports, in-memory Qdrant and temporary SQLite. Full backend validation:
1803 passed, 4 skipped, 5 live-service tests deselected; mypy checked 133 modules.
Browser component/interaction and production-build checks cover the UI. A visual
browser preview was unavailable in the development environment; it remains a
manual deployment check alongside real-model behavior and benchmark quality.

Final UI checks: 106 tests passed; TypeScript, ESLint and production build passed.

## Request observability

The authenticated **Traces** page now lists agentic chat requests as well as sync
runs. A content-free SQLite index (`REQUEST_TRACE_DB_PATH`, default
`data/request-traces.db`) records start/final status, duration, caller ownership,
clarification parent and usage totals. Regular users see their own requests;
OPERATOR/ADMIN can inspect requests within their tenant. Knowing a trace ID
alone grants no access. Clarification replies use a fresh authorization check
and an owned `parent_trace_id`; the UI links back to the previous request.

Each chat receives a server-generated trace identity. An incoming HTTP trace is
retained as an OTel link rather than allowed to select the ownership index key.
The request subtree includes query rewriting, retrieval and evidence preparation,
`agent.run`, every actual `llm.request`, `tool.*`, `document.read`, validation and
retry spans, and the final `answer.validate` release check. Resolver and visual
reading/checking model calls are nested under their tools. Wrapper spans are not
also recorded as generations, avoiding double-counted calls. The root closes
last, including on cancellation. Outcomes distinguish answered, abstained,
clarification, rejection, timeout, exhausted budget, provider failure and cancel.

Only operational values are recorded by the new agent spans: provider/model,
call counts, tokens/cache, tool name and ID, retry counts, validator reason codes,
and outcomes. New span contexts suppress automatic raw exception events. The
browser endpoint forwards an explicit attribute allowlist and excludes arbitrary
SDK attributes, events, prompts, evidence, answers, credentials and raw exception
messages. Existing opt-in forensic captures are a separate, sensitive facility.

Set `MODEL_PRICING_JSON` to an object keyed by `provider:model` (preferred) or
model name. Each entry requires nonnegative `input_per_million` and
`output_per_million` USD rates; add `cached_input_per_million` and
`cache_write_per_million` when those token classes are reported. Example shape,
with illustrative rates, not a price recommendation:

```json
{"openai:your-model":{"input_per_million":1,"output_per_million":4,"cached_input_per_million":0.1}}
```

Prices are operator-managed estimates, not fetched automatically or treated as
provider invoices. Missing usage, an unconfigured model, or an unpriced cache
class makes total cost **Unknown**; a known subtotal can still be shown. An
unpriced model is never assigned zero cost. Request-local usage includes query
rewriting; agent request/token limits apply to the agent and nested tool calls,
while rewriting retains its own timeout. Embedding/reranking infrastructure cost
is not included. Provider observations are task-local to prevent concurrent
requests from mixing usage records.

Jaeger/Langfuse export still uses the existing OTel configuration. The index can
show completed/cancelled request summaries while Jaeger is unavailable; span
waterfalls require successful export/indexing. SQLite write failures do not
block answers and are logged by error class. There is no retention scheduler or
crash recovery yet: a process killed before finalization can leave a `running`
index record. Operators must manage persistent storage, access and retention.
Direct Jaeger links are disabled by default; enabling
`EXTERNAL_TRACE_LINKS_ENABLED` permits them only for ADMIN. Jaeger itself still
requires deployment-level authentication/network protection.

See [the security review](agentic-security-review.md) for audited boundaries,
regression coverage and remaining limitations.

Validation for this observability/security update: full backend suite 1821 passed,
4 skipped and 5 live-service tests deselected; targeted PDF raster-bound checks
followed the full run. Mypy checked 135 modules and Ruff passed. Frontend 109
tests, TypeScript, ESLint and production build passed. No live LLM calls or new
benchmark grading were performed.

## Claim-scope validation and document grants

`AGENTIC_SCOPE_VALIDATION_ENABLED=true` is the production agentic default. After
existing deterministic validators accept a text/comparison candidate, a separate
stateless PydanticAI checker assesses each claim's entity/product/service,
version, period, population, unit and environment against the question and that
claim's cited authorized units. It has no research tools and does not receive the
answer agent's conversation or its reasoning. This is an output-validation call,
not another autonomous research agent or an application graph.

The checker returns supported/mismatch/insufficient, claim indexes, bounded reason
codes and exact evidence excerpts. Every claim must be covered exactly once;
supported checks need real excerpts from their own cited text/section. Fabricated
witnesses and incomplete judgments fail closed. No entity/product vocabulary or
benchmark-specific scope rule was added to the answer prompt.

Mismatch or uncertainty returns `SCOPE_*` reason codes through the existing
bounded retry path. The answer agent can search, inspect, correct/omit an
unsupported claim, ask for clarification or abstain. This does not force a
clarification when research can establish the missing fact. A server-owned
receipt binds a successful check to the exact question, candidate, cited content
and provenance. The release path rejects missing/mismatched receipts with
`SCOPE_RELEASE_UNVERIFIED`; it does not blindly trust a model-supplied approval.
Receipt reuse within a request avoids repeating the verifier on unchanged input.

Verifier calls share the agent's request/token/time limits and appear as real
`llm.request` spans with `research.model_role=scope_validator` under
`answer.scope_validate` (candidate phase). The release receipt check has its own
release-phase span. Ordinary supported answers generally need one extra call;
repair may need another. The verifier payload is capped at 120000 characters;
oversized candidates must reduce claims/focus citations. Tight budgets can cause
an application abstention instead of releasing an unchecked draft. The explicit
flag can disable this new semantic guard for controlled comparisons/debugging;
it does not disable existing validators. Visual results retain their existing
separate image-reading/condition-confirmation contract rather than pretending
that page images are text-verified. Clarification/abstention carries no factual
answer to certify.

The checker is a probabilistic model judgment, even with literal-witness and
receipt checks. It can still make semantic errors, particularly on complex or
poisoned evidence. Keep paired quality and adversarial evaluation requirements.

User/group document permissions are enforced independently of the agent flag.
The production default is **deny until granted**. ADMIN manages policies in
Knowledge → Document permissions. See [document permissions](document-permissions.md)
for migration, API, identity groups, revocation and connector limitations.

Live validation of this change: the four previously failing ambiguous-scope
runs now reject the initial candidate with `SCOPE_NOT_ESTABLISHED`, search and
answer SSH from the new evidence. A further 17-case run passed its checks,
including version/environment/period binding, aliases and translated evidence.
See [the measured follow-up](../artifacts/agentic-security-luna6/SCOPE-GUARD.md).

A later real MMLongBench mini-10 run exposed limitations beyond the synthetic
smoke: automatic scoring gave 5/8 answerable correct, but cited-evidence review
accepted only 4/8. The extra numeric match used a Twitter count to answer a
figure-count question; scope verification accepted it. One of two labeled
unanswerable questions was also answered. Two answerable questions exhausted
shared budgets. This is a concrete reason to keep rollout opt-in and evaluate
semantic quantity binding and recovery further. See
[the mini-10 audit](../artifacts/mmlongbench-v2/agentic-mini10-20261018/REVIEW.md).

## Targeted research tools

The agent now supports scoped hybrid/literal search, document discovery, PDF
structure enumeration, citable table reading, selected-region/page visual checks
and provenance comparison. Research preserves a final response/scope-check
request budget and performs local token preflight. See
[research-tools.md](research-tools.md) for exact contracts, bounds, dynamic
availability, extraction limitations and validation coverage. These additions do
not establish that semantic scope checking is infallible or that detected images
are an exhaustive list of figures.
