# Knowledge Base RAG

Multi-source knowledge base RAG platform with automatic incremental sync.

Builds on [production-rag-platform](https://github.com/negativexq/production-rag-platform)'s
proven core pipeline (chunking, hybrid dense+sparse search, cross-encoder
reranking, grounded generation with citations, OpenTelemetry tracing) rather
than rewriting it from scratch. The new value-add here: ingesting multiple
document types (PDF, Markdown, web pages, Notion, Confluence) through a
shared `Connector` interface, and automatic incremental re-sync — only
changed content gets re-indexed.

Full sprint-by-sprint plan: [docs/PLANNING.md](docs/PLANNING.md).

## Status

**Sprint 0** (foundation + core pipeline port) and **Sprint 1** (LLM
provider abstraction) are complete — see `docs/PLANNING.md`'s closing
notes and [docs/sprint-00-plan.md](docs/sprint-00-plan.md) /
[docs/sprint-01-plan.md](docs/sprint-01-plan.md).

## LLM providers

Generation (chat) and embedding are independent, config-driven choices —
Claude has no embedding endpoint, so embedding always stays on Ollama
regardless of which chat provider is selected:

```bash
GENERATION_PROVIDER=ollama   # or claude — local-first default
EMBEDDING_PROVIDER=ollama    # only option today
CLAUDE_API_KEY=sk-ant-...    # required if GENERATION_PROVIDER=claude
```

## Citation format

Citations are multi-source from the start:

```
[s.<source_type>:<source_id>/<page>/<paragraph>]
example: [s.pdf:handbook/2/0]
```

Grounding is checked against the full `(source_type, source_id, page,
paragraph)` tuple, so two different sources can safely share the same
page/paragraph coordinates without one masquerading as the other.

## Getting started

Requires Python 3.11+ and a native [Ollama](https://ollama.com) install
(runs on the host, not in Docker — no Metal GPU passthrough on macOS).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
docker compose up -d   # Qdrant + Jaeger
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

Run the test suite:

```bash
make test
```

Tests that require live Ollama/Qdrant skip automatically when those
services aren't reachable.

## License

MIT — see [LICENSE](LICENSE).
