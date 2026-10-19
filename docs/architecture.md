# Knowledge Base Research Workspace architecture

The product combines a document research workspace with an application-controlled
agentic backend. PydanticAI handles typed semantic calls; the application owns
research state, authorization, tools, computation, budgets, and answer release.
See the [detailed research graph and contracts](adaptive-workflow.md) and
[answered-question ledger](adaptive-solved-questions.md).

```mermaid
flowchart TD
    UI["React research workspace"] -->|"HTTP / SSE"| API["FastAPI"]
    API --> Access["Authentication, tenant and document permissions"]
    Access --> Retrieval["Dense + BM25 search, fusion, BGE reranking"]
    Retrieval --> Ledger["Authorized evidence ledger"]
    Ledger --> Research["PydanticAI agents + typed research graph"]
    Research <--> State["Application-owned ResearchState"]
    Research --> Tools["Scoped search, reads, PDF inspection and extraction"]
    Tools --> State
    State --> Calculate["Deterministic calculations and counts"]
    Calculate --> State
    State --> Finalize["Independent finalization"]
    Finalize --> Verify["Source, value and scope verification"]
    Verify -->|"Cited result"| UI
    Research -. "Stage metadata" .-> Trace["OpenTelemetry / Jaeger"]
```

## Service responsibilities

React owns presentation state and client-observed stream timing. FastAPI owns
identity, role and document checks, retrieval scope, research orchestration,
SSE production, and read-only `/ui/*` aggregation. Qdrant stores indexed knowledge;
the selected provider supplies model calls; Jaeger exposes trace spans.

The workspace presents citations, source inspection, stage progress, research
notes, projects, feedback, and trace details. Backend orchestration changes do
not require replacing its existing presentation model or screenshots.

`/ui/*` endpoints aggregate existing domain logic. They do not accept a
caller-selected tenant, expose internal clients/credentials, or create a privileged
request path. Application settings are injected at boot, so index reporting,
tracing, and runtime wiring read the same `Settings` instance.

## Research graph

The adaptive runner evaluates evidence, answers directly when possible, and
opens focused research for a concrete gap. Tools return evidence or structured
inputs, never permission to bypass release checks. The application can execute
a prepared calculation without another model planning turn.

`ResearchState` stores evidence needs, checked observations, source versions,
calculations, unresolved issues, and diagnostics. Each model receives a focused
projection. Research closure preserves successful work for independent finalization.
Serializable state does not imply automatic cross-request checkpoint recovery.

The implemented graph uses explicit async application control flow around
PydanticAI calls. GraphBuilder and durable workflow persistence are separate
composition decisions discussed in the [design rationale](adaptive-rag-research-design.md).

## Evidence and computation

Initial retrieval combines dense and BM25 search, rank fusion, and multilingual
BGE reranking. Section-aware assembly preserves nearby headers and captions.
Research tools reuse this authorized index and document reader; the adaptive
layer does not replace embeddings or re-ingest documents to answer a question.

Quantitative source inspection checks whether a bounded PDF page has usable
native text. Image-heavy pages can be read from the immutable original snapshot.
Extracted values retain labels, series, period, unit, scale, and witnesses.
Numeric evidence and definition/entity-relationship evidence are carried
separately and meet again at final scope verification.

Arithmetic uses permitted expressions and evidence-bound operands. Counts use
checked inventories and source positions. Application results are saved before
release, and checked transcriptions are explicitly distinguished from original
PDF text. Source routing and two-model agreement do not guarantee OCR accuracy.

Before source selection, a bounded native-PDF page catalog exposes location hints
inside already admitted page ranges. It carries document versions, physical pages,
original header/footer lines and live support IDs in typed application state.
This distinguishes printed page labels from physical positions and makes pages
inside broad indexed ranges individually discoverable. Catalog hints locate
sources; they do not certify answer values or layout. The catalog uses local PDF
reading, not an additional model call, and is bounded to 36 pages across at most
three source snapshots per attempt.

Source selection also identifies the required operation: direct numeric reading,
arithmetic, counting, minimum/maximum selection, or listing. The application
exposes only that operation's typed extraction contract. Arithmetic extraction
carries a reviewed output unit and explicit interpretation, which are displayed
with the application result. It cannot emit count settings or a model-written
result; a direct value reading
does not require artificial comparison operands. This reuses the source-selection
call rather than adding a planning call.

For image extraction, the application assigns source-image handles and stores
their document version and physical-page mapping. The model selects supplied
handles; printed page labels are not accepted as physical-page identity. Text
extraction selects bounded line ranges from the supplied support IDs.

```mermaid
flowchart LR
    Select["Select source + operation"] --> Contract["Application selects typed contract"]
    Contract --> Extract["Extract inputs + evidence handles"]
    Extract --> Bind["Resolve source identity in code"]
    Bind --> Review["Check inputs, coverage and operation"]
    Review -->|Supported and complete| Execute["Read / calculate / count / select / list"]
    Review -->|Incomplete list| Complete["Seek missing coverage; preserve list goal"]
    Complete --> Contract
    Execute --> Receipt["Persist checked result for independent finalization"]
```

Coverage completion differs from correcting an invalid input slot. An incomplete
or unknown coverage assessment with a grounded inventory gap can request the
missing source; unknown alone cannot. Repair candidates are ranked against the
concrete evidence gap within already authorized units. A list repair
keeps verified existing items, seeks a new source view for missing items, and
preserves the original listing operation. The combined inventory is checked
again before execution. If the existing bindings are unresolved, the repair reads
a fresh inventory instead of unioning unconfirmed items. Parent receipts remain
in state; completion is not an
implicit approval of the larger inventory. Existing request, source-window and
repair budgets still bound this path. If retaining old source images would
exceed the window, the old receipt stays in state while a full replacement
inventory is checked in a fresh bounded window. Coverage review checks that
prior supported items remain represented in the new source; spelling/alias
variants require source support rather than literal answer-format matching.

A grounded final-scope objection can also trigger one bounded source-repair
attempt. The original input receipt and objection stay in state, the operation
stays fixed, and replacement evidence passes input review and final scope review
again. An ungrounded objection does not authorize a repair. A known scope-rejected
receipt is not repeatedly retried as a complete answer during finalization.
Arithmetic review asks whether the explicitly presented interpretation is valid;
another possible interpretation alone does not invalidate a defensible answer.
Reviewer contracts expose only the actual operation slots: a list issue targets
an item or the operation, never a nonexistent numeric operand. One bounded
diagnostic-receipt correction is separate from the source-repair slot; both share
the same hard request, token and time ceilings.
The input checker reserves a final scope call, since an accepted prepared result
can be finalized directly by application code without another answer-writing call.

## Trust and release boundaries

```mermaid
flowchart LR
    Policy["Trusted system policy and server identity"] --> Request["User question"]
    Request --> Data["Authorized, explicitly untrusted evidence"]
    Data --> Candidate["Typed candidate and source IDs"]
    Candidate --> Code["Identity, access, literals and calculation checks"]
    Code --> Scope["Semantic source and question-scope check"]
    Scope --> Render["Application-resolved citations and release"]
```

Document body and metadata remain data rather than provider system instructions.
`app/llm/trust_boundary.py` defines the fixed-path serialization boundary; agent
roles use explicit task/data contracts. Unknown, hidden, cross-tenant, or stale
source references cannot be authorized by a model decision.

Support IDs are request-scoped. The application resolves them to exact source
text; a valid ID proves provenance, not semantic entailment. Claim-local critical
value checks evaluate literals and their bindings. Independent semantic review
checks the requested entity, period, population, condition, and operation.
Gold answers are excluded from runtime generation and scope verification.

Both supported answers and explicit evidence limits are legitimate release
outcomes. API failure, exhausted budget, absent evidence, and reviewer uncertainty
are recorded separately. Finalization remains subject to hard shared ceilings.

Normal telemetry is bounded metadata. Raw questions, answers, model outputs, and
evidence require explicit forensic capture settings and remain local in the
adaptive diagnostic workflow. Git retains small Markdown reports rather than
raw traces, images, and source capsules.

## Runtime profiles

`ADAPTIVE_RAG_ENABLED=true` selects the typed research graph.
`AGENTIC_RAG_ENABLED=true` selects the alternative single-agent tool runner;
the two flags are mutually exclusive. Their tools reuse existing retrieval,
PDF inspection, source contracts, and final validators. With neither selected,
the fixed answer path remains available. See [configuration](../.env.example).

The fixed path supports `fast` streaming and `strict` buffered release behavior.
Its short policy is in `prompts/answer_v3.txt`. Phase 6 answerability classifiers
and shadow evaluators are separate evaluation components, not mandatory semantic
calls in that fixed path. These components should not be confused with the
adaptive graph's own input and scope checks.

## Further reading

- [Agentic graph, state, tools, and budgets](adaptive-workflow.md)
- [Architectural rationale and persistence choices](adaptive-rag-research-design.md)
- [PydanticAI orchestration research](pydantic-workflow-research.md)
- [Source-grounded validation](rag-validation-research.md)
- [Security model](security.md)
- [Alternative agent runner](agentic-rag.md)
