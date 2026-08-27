import pytest

import scripts.benchmark_candidate_k as benchmark_module
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings


class _FakeOllama:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def embed(self, text, model, prefix="", dimensions=None):
        return [0.0] * (dimensions or 1024)

    async def aclose(self):
        return None


class _FakeSparse:
    def embed_query(self, text):
        return object()


class _FakeReranker:
    def __init__(self):
        self.calls = []

    def rerank(self, query, candidates, top_n):
        self.calls.append((query, candidates, top_n))
        return candidates[:top_n]


@pytest.mark.asyncio
async def test_candidate_runner_forwards_candidate_k_and_acl_before_rerank(monkeypatch):
    captured = {}

    def fake_hybrid_search(*args, **kwargs):
        captured.update(kwargs)
        return [SearchResult(score=1.0, payload={"source_id": "source-a"})]

    monkeypatch.setattr(benchmark_module, "OllamaClient", _FakeOllama)
    monkeypatch.setattr(benchmark_module, "SparseEncoder", _FakeSparse)
    monkeypatch.setattr(benchmark_module, "hybrid_search", fake_hybrid_search)

    question = {
        "id": "q-1",
        "case_family": "family-1",
        "category": "standard_answerable",
        "query_language": "en",
        "evidence_language": "en",
        "language_pair": "en-en",
        "tenant_id": "tenant-a",
        "answerability": "answerable",
        "difficulty": "standard",
        "question": "What is the standard return window?",
        "expected_source_ids": ["source-a"],
    }
    reranker = _FakeReranker()

    result = await benchmark_module.run_candidate_k(
        [question], 10, Settings.benchmark_reference(), object(), "kb_active", reranker
    )

    assert captured["top_k"] == 10
    assert captured["filters"] is not None
    assert result["candidate_k"] == 10
    assert reranker.calls[0][1][0].payload["source_id"] == "source-a"
    assert reranker.calls[0][2] == 5
