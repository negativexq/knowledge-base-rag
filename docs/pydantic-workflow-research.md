# PydanticAI orchestration, graph stages, and tool selection

Research recorded: 18 October 2026. This note separates SDK mechanisms from
application responsibilities. For the implemented runner, see the
[agentic workflow](adaptive-workflow.md). The original local API probes used
synthetic data and no provider calls; they were not model-quality measurements.

## Recommendation

Use an explicit outer workflow, with small PydanticAI calls or tool loops where
semantic uncertainty requires them. Known transitions can be ordinary async
Python hand-offs. A prepared computation does not need another planning turn.
GraphBuilder is an available composition option when branching warrants it;
the current project controls its transitions in application code.

The recorded installation pins `pydantic-ai-slim[openai,anthropic]==1.107.7` and
includes `pydantic-graph==1.107.7`. Installing an SDK does not provide a completed
visual extraction system: its schema, source binding, review, and evaluation
remain application work.

## Reusable mechanisms

| Need | SDK mechanism | Application responsibility |
| --- | --- | --- |
| Agent invocation and tool loop | `Agent` | Task contract and scope. |
| Structured output | `output_type`, Pydantic models | Field meaning and source truth. |
| Service dependencies | `deps_type`, `RunContext.deps` | Authorized readers, clients, and limits. |
| Grouped tools | `FunctionToolset` | Narrow responsibilities. |
| Dynamic visibility | `FilteredToolset`, `prepare`, `PreparedToolset`, `PrepareTools` | Capability and stage rules plus execution-time authorization. |
| Straight hand-offs | Async Python / programmatic delegation | Whether another semantic stage is needed. |
| Explicit SDK graph composition | GraphBuilder steps and decisions | State, branches, loop limits, and continuation semantics. |
| Usage and retry limits | `RunUsage`, `UsageLimits`, retry settings | Shared accounting across runs and finalization reserve. |
| Tests and timing | FunctionModel and SDK invocation controls | End-to-end deadline, source contracts, and quality evaluation. |

Recorded primary references: [graph](https://pydantic.dev/docs/ai/graph/graph/),
[steps](https://pydantic.dev/docs/ai/graph/builder/steps/),
[decisions](https://pydantic.dev/docs/ai/graph/builder/decisions/),
[toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/),
[advanced tools](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/),
[dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/), and
[output](https://pydantic.dev/docs/ai/core-concepts/output/).
Version-specific compatibility must be checked before adopting a newer API.

## Who chooses a tool?

1. The application determines which actions are available for the current stage,
   permissions, source, provider capabilities, and remaining allowance.
2. The model sees those descriptions and input schemas, then selects an action
   or a supported answer. A toolset itself is not a semantic router.
3. SDK and application validation check the arguments before execution.
4. The function rechecks source and access boundaries. Hiding a tool is not an
   authorization boundary.
5. The result returns to the next semantic step or moves directly to a known
   application stage. An extra routing model is not required for a fixed transition.

For example, extraction can expose only source-reading responsibilities, while
final writing has research tools closed. A bounded return to research may be
allowed before closure if evidence is genuinely missing. Tools being closed is
not itself a factual judgment or proof that the model cannot answer.

## Data between stages

Application contracts retain:

- The immutable original task and any versioned interpretation.
- Evidence IDs, source versions, physical pages, and regions.
- Raw/canonical values, category and series labels, units, headers, footnotes,
  readability, extraction method, and original witnesses.
- Computation inputs, permitted formula, conversions, and result.
- Natural answer candidates and claim/citation bindings.
- Review outcomes that distinguish contradiction, missing evidence, uncertainty,
  and operational failure.

Typed Python objects can pass directly between functions. The application
serializes only the fields needed by a model role. It does not have to copy the
entire conversation or ask another model to summarize the sole copy of the data.
Internal clients, credentials, and authorization context remain server-side.

## Short path and research path

The conceptual sequence is retrieval → evidence assessment → extraction if
needed → question binding → computation if needed → answer → verification.
The first assessment can return either an answer or a concrete evidence gap.
A separate routing call is optional, not an architectural requirement.

When text is sufficient, a tool loop and visual extraction can be skipped.
Independent semantic checking still has its own cost when enabled. Question
keywords such as “table” or “graph” are not a complete source-quality test.
A model can propose a region or missing relationship; the application checks
its execution conditions. Valid routing JSON does not prove correct routing.

Ready operands and a known formula can execute directly. Use semantic planning
when the definition or inputs are unresolved, rather than making a model choose
an already determined calculation again.

## Shared budgets and useful progress

Native retries correct malformed arguments; they should not encode the entire
research policy. Missing data can be a normal typed outcome. A retry limit is
not a total cost limit, and SDK successful-call accounting can differ from an
application's count of failed execution attempts.

Nested agent delegation needs shared usage passed explicitly, such as
`usage=ctx.usage`. Separate runs need a common usage ledger and hard limits;
a graph builder does not automatically combine independently created runs.
See [programmatic hand-off and delegation](https://pydantic.dev/docs/ai/guides/multi-agent-applications/).

Track repeated operation signatures, evidence revisions, successful reads and
computations, elapsed time, and finalization allowance. No new text does not
mean no progress. Close research early enough to attempt a final answer from
saved results, while retaining the total deadline and request/token ceilings.

## Recorded local compatibility probe

The investigation inspected GraphBuilder, StepContext, FunctionToolset,
FilteredToolset, PreparedToolset, PrepareTools, and shared usage in the installed
1.107.7 environment. Older `pydantic_graph.Graph` runner and beta import paths
produced deprecation warnings in that probe. This is a recorded version-specific
finding, not a claim about all current SDK releases.

Without live models or network calls:

- Typed Ready/NeedData branches ran a short route→answer path and a
  route→extract-fixture→answer path.
- FunctionModel checks exposed only extraction tools during extraction, only
  calculation during calculation, and no tools during writing.
- The synthetic tool examples used two model turns and tool-free writing one.

The probe demonstrated API composition and visibility. It did not establish
real model routing, OCR accuracy, latency improvement, or production quality.
It was not installed as an additional project runner.

## Working state, checkpoints, and memory

| Layer | Stored data | Purpose |
| --- | --- | --- |
| Working state | Current facts, gaps, attempts, computations, and review state. | Choose the next step coherently. |
| Checkpoint | Versioned application state and continuation point. | Inspection and recovery. |
| Extraction cache | Structured data for one source version/region. | Avoid repeated extraction cost. |
| Long-term memory | Preferences or reviewed persistent knowledge. | Cross-session continuity. |

[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
and its [memory overview](https://docs.langchain.com/oss/python/concepts/memory)
illustrate the distinction between thread-scoped state and cross-thread stores.
The distinction is useful without requiring a migration to LangGraph.

Working state should distinguish checked evidence, model hypotheses, extraction
errors, and unsuccessful searches. Tool results update it directly; memory
maintenance does not require a summarizer at each step. Numbers, conditions, and
source bindings stay structured when active context is compacted. This aligns
with [selective context and structured notes](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

Collection-independent research asks what is missing, which permitted action
can address it, what changed, and whether an answer is now supported. Document
terms and definitions come from evidence. Authorization comes from the server.
No benchmark-specific hidden definitions or collection-specific refusal rules
are required by this architecture.

## Persistence boundary

The recorded [GraphBuilder documentation](https://pydantic.dev/docs/ai/graph/builder/#persistence-and-resumability)
does not imply automatic application-state snapshots.
[Harness StepPersistence](https://pydantic.dev/docs/ai/harness/step-persistence/)
message checkpoints are different from checkpoints of the whole application's
graph state. Mid-step/process recovery is a further durable-execution concern.
Newer documentation must be checked against the installed SDK before adoption;
this investigation did not upgrade dependencies.

A future checkpoint must retain schema/state versions, sources, consumed budget,
completed/pending work, and the continuation point. Resume revalidates access
and document versions and does not reset usage. Saving chat history alone is
not equivalent. Extraction cache keys include source hash, region, render settings,
model, prompt/schema versions, and relevant question/context. A cache hit cannot
bypass authorization or turn an old result into current evidence. Gold answers
and previous generated answers are not verified document memory.

## Adoption sequence

1. Preserve existing dependencies, ledger, ACL/version checks, and observability.
2. Separate task, extraction, computation, and answer contracts.
3. Use simple programmatic hand-offs before introducing more orchestration layers.
4. Narrow tool responsibilities and measure capability/keyword gates separately.
5. Evaluate structured extraction independently of direct visual answer reading.
6. Introduce SDK graph composition or persistence when the actual branching or
   recovery requirement justifies it.
7. Compare fixed-evidence routing, unnecessary calls, supported answers, refusals,
   total usage, latency, and cost before claiming a gain.

Reuse SDK mechanics to focus application work on evidence and meaning. See the
[implemented workflow](adaptive-workflow.md) for the project's current boundaries.
