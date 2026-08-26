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

`/ui/*` endpoints are read-only presentation aggregations over existing domain
logic. They do not accept a caller-selected tenant, do not expose internal
clients or credentials, and do not create a privileged request path.
