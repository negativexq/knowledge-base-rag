# RAG Operations Console Architecture

```text
React UI
   ↓ HTTP / SSE
FastAPI
   ↓
Authentication / tenant ACL
   ↓
Qdrant + generator provider + Jaeger
```

The React UI owns presentation state and client-observed stream timings. FastAPI
owns authentication, role checks, tenant scoping, retrieval ACL enforcement,
SSE production, and read-only `/ui/*` aggregation. Qdrant stores the indexed
knowledge, the configured provider supplies generation, and Jaeger provides
trace spans. The evaluated Luna generator is the planned hosted profile;
local Ollama remains available for development and historical reproduction.

Generation keeps the control plane separate from retrieved data:

```text
trusted system policy
       ↓
server-owned security rules and UserContext
       ↓
user question (request semantics)
       ↓
explicit JSON-encoded UNTRUSTED retrieved context
       ↓
generation
       ↓
support-ID and claim-local critical-value validation
       ↓
canonical citation and output-policy validation
```

`prompts/answer_v3.txt` defines the short policy. `app/llm/trust_boundary.py`
serializes document body and metadata as length-prefixed JSON records;
document text never becomes a provider `system` or `assistant` message.
Deterministic support units are request-scoped and validated against the
authorized, model-visible evidence set. The application resolves support IDs
to exact citation text; a valid support ID proves provenance, not semantic
entailment. The critical-value guard is claim-local: unrelated values in another
selected support unit do not invalidate a claim, while unresolved or directly
conflicting values remain conservative. It is a deterministic consistency check,
not a semantic verifier.

`fast` preserves token-by-token delivery and reports policy results after the
stream. `strict` buffers the generated answer and releases it only after
deterministic citation/disclosure/suppression checks pass.

## Active runtime versus evaluated experiments

The intended request path is deliberately:

```text
query → tenant ACL → dense + BM25 + RRF → authorized Top20
      → BGE Top5 → graceful SectionAware evidence assembly
      → deterministic support units → Luna generation
      → support-ID validation → claim-local critical-value validation
      → application-resolved citations
```

Phase 6 answerability classifiers and semantic evaluators are evaluated or
shadow-only research components, not active production gates. Their settings
are disabled by default. No semantic LLM call is required by the active
runtime path.

`/ui/*` endpoints are read-only presentation aggregations over existing domain
logic. They do not accept a caller-selected tenant, do not expose internal
clients or credentials, and do not create a privileged request path.

Runtime configuration is injected into the application state at boot. UI
settings, active-index reporting, and tracing all read the same `Settings`
instance used by the real wiring, so a custom runtime configuration cannot
silently diverge from the values shown in the console.
