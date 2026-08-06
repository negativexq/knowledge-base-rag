import pytest

from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.hybrid_search import SearchResult


@pytest.fixture(scope="module")
def reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


def _result(text: str) -> SearchResult:
    return SearchResult(score=0.5, payload={"text": text})


def test_reranker_scores_relevant_chunk_higher_than_irrelevant(reranker):
    query = "What is the return policy for a defective product?"
    candidates = [
        _result("Sourdough bread requires flour, water, salt, and a starter left overnight."),
        _result(
            "Defective products can be returned within 30 days for a full refund, no "
            "questions asked, as long as the original packaging is intact."
        ),
    ]

    results = reranker.rerank(query, candidates, top_n=2)

    assert results[0].payload["text"].startswith("Defective products")
    assert results[0].score > results[1].score


def test_reranker_respects_top_n(reranker):
    query = "hybrid search"
    candidates = [_result(f"chunk {i} about hybrid search and retrieval") for i in range(5)]

    results = reranker.rerank(query, candidates, top_n=3)

    assert len(results) == 3


def test_reranker_results_are_sorted_descending_by_score(reranker):
    query = "printer driver troubleshooting"
    candidates = [
        _result("Reinstalling the printer driver resolves most connectivity issues."),
        _result("The recipe calls for two cups of flour and a pinch of salt."),
        _result("Restart the print spooler service if jobs are stuck in queue."),
    ]

    results = reranker.rerank(query, candidates, top_n=3)

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
