import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from sentence_transformers import CrossEncoder

from app.reranker.config import RERANKER_BACKEND
from app.retrieval.hybrid_search import SearchResult

# Model load and inference latency depend on the selected model and hardware;
# see docs/reranking.md and artifacts/reranker-benchmark-sprint26/.


class CrossEncoderReranker:
    backend = RERANKER_BACKEND

    def __init__(
        self,
        model_name: str,
        trust_remote_code: bool = False,
        device: str | None = None,
        max_concurrency: int = 1,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.model_name = model_name
        self.trust_remote_code = trust_remote_code
        self.max_concurrency = max_concurrency
        self._async_semaphore = asyncio.Semaphore(max_concurrency)
        kwargs = {"trust_remote_code": True} if trust_remote_code else {}
        if device is not None:
            kwargs["device"] = device
        self.device = device
        self._model = CrossEncoder(model_name, **kwargs)

    async def async_rerank(
        self, query: str, candidates: list[SearchResult], top_n: int
    ) -> list[SearchResult]:
        """Run sync inference off-loop with a per-instance concurrency bound."""
        async with self._async_semaphore:
            return await asyncio.to_thread(self.rerank, query, candidates, top_n)

    def rerank(self, query: str, candidates: list[SearchResult], top_n: int) -> list[SearchResult]:
        if not candidates:
            return []

        pairs = [[query, candidate.payload["text"]] for candidate in candidates]
        scores = self._model.predict(pairs)

        reranked = sorted(zip(candidates, scores), key=lambda pair: -pair[1])
        return [
            SearchResult(score=float(score), payload=candidate.payload, id=candidate.id)
            for candidate, score in reranked[:top_n]
        ]

    def rerank_many(
        self,
        requests: list[tuple[str, list[SearchResult]]],
        top_n: int,
    ) -> list[list[SearchResult]]:
        """Rerank independent requests with bounded offline concurrency.

        This is used only by offline benchmarks. Production ``search`` uses
        ``async_rerank`` to keep sync inference off the event loop while
        bounding access to the shared model instance.
        """
        ranked, _timings = self.rerank_many_with_timings(requests, top_n)
        return ranked

    def rerank_many_with_timings(
        self,
        requests: list[tuple[str, list[SearchResult]]],
        top_n: int,
    ) -> tuple[list[list[SearchResult]], list[float]]:
        """Return offline batch results and measured per-request durations."""
        if not requests:
            return [], []

        def rerank_one(request: tuple[str, list[SearchResult]]) -> tuple[list[SearchResult], float]:
            started = time.perf_counter()
            result = self.rerank(request[0], request[1], top_n=top_n)
            return result, (time.perf_counter() - started) * 1000

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            measured = list(executor.map(rerank_one, requests))
        return (
            [result for result, _duration in measured],
            [duration for _result, duration in measured],
        )

    def rerank_batch_with_amortized_timing(
        self,
        requests: list[tuple[str, list[SearchResult]]],
        top_n: int,
    ) -> tuple[list[list[SearchResult]], float]:
        """Score an offline matrix in one model batch.

        Benchmarking all 220 questions as 220 independent CrossEncoder calls
        makes model-call overhead dominate the retrieval experiment. This
        method keeps request boundaries for ranking while using one local
        inference batch; callers must label its duration as amortized.
        Production ``search`` never uses this path.
        """
        if not requests:
            return [], 0.0
        pairs: list[list[str]] = []
        widths: list[int] = []
        for query, candidates in requests:
            pairs.extend([[query, candidate.payload["text"]] for candidate in candidates])
            widths.append(len(candidates))
        started = time.perf_counter()
        batch_size = 8 if self.device == "mps" else 64
        scores = self._model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked: list[list[SearchResult]] = []
        cursor = 0
        for width in widths:
            scored = list(zip(requests[len(ranked)][1], scores[cursor : cursor + width]))
            cursor += width
            scored.sort(key=lambda pair: -pair[1])
            ranked.append(
                [
                    SearchResult(score=float(score), payload=candidate.payload, id=candidate.id)
                    for candidate, score in scored[:top_n]
                ]
            )
        return ranked, elapsed_ms / len(requests)
