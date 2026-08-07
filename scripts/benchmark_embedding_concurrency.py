"""Sprint 14: real embedding-concurrency benchmark against native Ollama.

Not part of the automated test suite (CI has no Ollama, see the Sprint 12
closing note in docs/PLANNING.md) — run manually:

    .venv/bin/python scripts/benchmark_embedding_concurrency.py

Measures real chunks/sec for concurrency levels 1/2/4/8 at chunk counts
10/100/1000, against the real embedding model this project uses
(nomic-embed-text). Does NOT assume higher concurrency is always faster —
a single native Ollama instance serving one model may serialize
internally past some point, which would show up as a plateau or a
regression in the numbers below, and this script reports whatever the
real numbers are.
"""

import asyncio
import time

from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX, embed_texts_concurrently
from app.llm.ollama_client import OllamaClient
from app.shared.config import settings

CHUNK_COUNTS = [10, 100, 1000]
CONCURRENCY_LEVELS = [1, 2, 4, 8]

# Representative of a real chunk: a few sentences, not a single word —
# short enough to keep the benchmark's own runtime reasonable, long
# enough that embedding cost isn't dominated by fixed per-request
# overhead alone.
_TEXT_TEMPLATE = (
    "This is benchmark chunk number {i}, representative of a real "
    "document paragraph with several sentences of content. It exists "
    "purely to measure embedding throughput, not to carry any real "
    "meaning. The quick brown fox jumps over the lazy dog near the "
    "riverbank at dawn."
)


async def main() -> None:
    ollama = OllamaClient(base_url=settings.ollama_base_url)

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

    texts = [_TEXT_TEMPLATE.format(i=i) for i in range(max(CHUNK_COUNTS))]

    print(f"{'chunks':>7} {'concurrency':>11} {'elapsed_s':>10} {'chunks/sec':>11}")
    results = []
    try:
        for n in CHUNK_COUNTS:
            batch = texts[:n]
            for concurrency in CONCURRENCY_LEVELS:
                start = time.perf_counter()
                await embed_texts_concurrently(batch, embed_fn, concurrency)
                elapsed = time.perf_counter() - start
                rate = n / elapsed
                results.append(
                    {"chunks": n, "concurrency": concurrency, "elapsed_s": elapsed, "rate": rate}
                )
                print(f"{n:7d} {concurrency:11d} {elapsed:10.2f} {rate:11.2f}")
    finally:
        await ollama.aclose()

    print("\nSummary (chunks/sec by concurrency, averaged across chunk counts):")
    for concurrency in CONCURRENCY_LEVELS:
        rates = [r["rate"] for r in results if r["concurrency"] == concurrency]
        print(f"  concurrency={concurrency}: avg {sum(rates) / len(rates):.2f} chunks/sec")


if __name__ == "__main__":
    asyncio.run(main())
