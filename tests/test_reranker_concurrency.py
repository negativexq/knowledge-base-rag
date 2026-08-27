import asyncio
import time

import pytest

from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.hybrid_search import SearchResult


def _result(text: str) -> SearchResult:
    return SearchResult(score=0.5, payload={"text": text})


@pytest.mark.asyncio
async def test_async_rerank_respects_shared_model_concurrency_limit(monkeypatch):
    class _FakeCrossEncoder:
        def __init__(self, model, **kwargs):
            pass

    monkeypatch.setattr("app.reranker.cross_encoder.CrossEncoder", _FakeCrossEncoder)
    reranker = CrossEncoderReranker("candidate-model", max_concurrency=1)
    active = 0
    max_active = 0

    def fake_rerank(query, candidates, top_n):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.02)
        active -= 1
        return candidates[:top_n]

    reranker.rerank = fake_rerank
    results = await asyncio.gather(
        *(reranker.async_rerank(f"query-{i}", [_result(str(i))], 1) for i in range(4))
    )

    assert len(results) == 4
    assert max_active == 1


@pytest.mark.asyncio
async def test_async_rerank_propagates_worker_exception(monkeypatch):
    class _FakeCrossEncoder:
        def __init__(self, model, **kwargs):
            pass

    monkeypatch.setattr("app.reranker.cross_encoder.CrossEncoder", _FakeCrossEncoder)
    reranker = CrossEncoderReranker("candidate-model", max_concurrency=1)

    def failing_rerank(query, candidates, top_n):
        raise RuntimeError("reranker failed")

    reranker.rerank = failing_rerank
    with pytest.raises(RuntimeError, match="reranker failed"):
        await reranker.async_rerank("query", [_result("text")], 1)
