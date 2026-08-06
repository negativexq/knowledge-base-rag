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

**Sprints 0–4** are complete: foundation + core pipeline port, LLM provider
abstraction (Ollama + Claude), a SQLite-backed document registry, a
filesystem `Connector` that ingests mixed PDF/Markdown folders, and
hash-based incremental sync (skip unchanged, update changed, delete
vanished — no orphan chunks). See `docs/PLANNING.md`'s closing notes and
the `docs/sprint-0{0..4}-plan.md` files for the design decisions behind
each.

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
[s.<source_type>:<source_id>/<location>]
examples: [s.filesystem:handbook_pdf/2/0]           (PDF: page/paragraph)
          [s.filesystem:readme_md/Kurulum/Adım 1]   (Markdown: heading path)
```

`source_type` identifies the connector a document came from (`filesystem`
today; `notion`/`confluence` later), not its file format — the same
connector can ingest multiple formats. Grounding is checked against the
full `(source_type, source_id, location)` triple, so two different sources
can safely share the same location without one masquerading as the other.

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
