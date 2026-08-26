# RAG Operations Console Architecture

```text
React UI
   ↓ HTTP / SSE
FastAPI
   ↓
Authentication / tenant ACL
   ↓
Qdrant + Ollama + Jaeger
```

The React UI owns presentation state and client-observed stream timings. FastAPI
owns authentication, role checks, tenant scoping, retrieval ACL enforcement,
SSE production, and read-only `/ui/*` aggregation. Qdrant stores the indexed
knowledge, Ollama provides embedding/generation, and Jaeger provides trace
spans.

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
canonical citation and output-policy validation
```

`prompts/answer_v3.txt` defines the short policy. `app/llm/trust_boundary.py`
serializes document body and metadata as length-prefixed JSON records;
document text never becomes a provider `system` or `assistant` message. The
server-generated canonical citation is validated against the authorized chunk
set by `app/llm/grounding.py`. This is citation integrity, not claim-level
semantic grounding.

`fast` preserves token-by-token delivery and reports policy results after the
stream. `strict` buffers the generated answer and releases it only after
deterministic citation/disclosure/suppression checks pass.

`/ui/*` endpoints are read-only presentation aggregations over existing domain
logic. They do not accept a caller-selected tenant, do not expose internal
clients or credentials, and do not create a privileged request path.
