import math
from dataclasses import dataclass

from app.evaluation.retrieval_metrics import Location


@dataclass(frozen=True)
class RankMetrics:
    """Rank-aware retrieval metrics — Sprint 18 adds these because
    app/evaluation/retrieval_metrics.py's precision/recall treat the
    top-k result set as unordered (correct for the golden-set harness's
    "did the right chunk make the cut" question), but a benchmark
    comparing two embedding models needs to know WHERE in the ranking the
    right chunk landed, not just whether it's in the top 5.
    """

    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    reciprocal_rank: float
    ndcg_at_5: float


def _recall_at_k(ranked: list[Location], expected: set[Location], k: int) -> float:
    if not expected:
        return 0.0
    top_k = set(ranked[:k])
    return sum(1 for loc in expected if loc in top_k) / len(expected)


def _reciprocal_rank(ranked: list[Location], expected: set[Location]) -> float:
    for rank, loc in enumerate(ranked, start=1):
        if loc in expected:
            return 1.0 / rank
    return 0.0


def _ndcg_at_k(ranked: list[Location], expected: set[Location], k: int) -> float:
    if not expected:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1) for rank, loc in enumerate(ranked[:k], start=1) if loc in expected
    )
    ideal_hits = min(len(expected), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def compute_rank_metrics(
    ranked_locations: list[Location], expected_locations: list[Location]
) -> RankMetrics:
    """ranked_locations must already be in retrieval-score order (best
    first) — the caller (the benchmark script) is responsible for that,
    this function trusts list order as rank.
    """
    expected = set(expected_locations)
    return RankMetrics(
        recall_at_1=_recall_at_k(ranked_locations, expected, 1),
        recall_at_3=_recall_at_k(ranked_locations, expected, 3),
        recall_at_5=_recall_at_k(ranked_locations, expected, 5),
        reciprocal_rank=_reciprocal_rank(ranked_locations, expected),
        ndcg_at_5=_ndcg_at_k(ranked_locations, expected, 5),
    )


def aggregate_rank_metrics(per_question: list[RankMetrics]) -> dict[str, float]:
    """Mean of each field across questions — 0.0 (not None) when the list
    is empty is a deliberate choice for this module: the benchmark script
    always calls this with a non-empty cell, and an empty-list caller
    asking for a mean has no sensible non-zero answer anyway.
    """
    if not per_question:
        return {
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "ndcg_at_5": 0.0,
        }
    n = len(per_question)
    return {
        "recall_at_1": sum(m.recall_at_1 for m in per_question) / n,
        "recall_at_3": sum(m.recall_at_3 for m in per_question) / n,
        "recall_at_5": sum(m.recall_at_5 for m in per_question) / n,
        "mrr": sum(m.reciprocal_rank for m in per_question) / n,
        "ndcg_at_5": sum(m.ndcg_at_5 for m in per_question) / n,
    }
