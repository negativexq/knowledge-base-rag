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

**Sprint 0** (foundation + core pipeline port) is complete — see the
[Sprint 0 closing note](docs/PLANNING.md#kapan%C4%B1%C5%9F-notu) in
`docs/PLANNING.md` and the module-by-module port table in
[docs/sprint-00-plan.md](docs/sprint-00-plan.md).

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
