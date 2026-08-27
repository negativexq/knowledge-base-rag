"""Deterministic, shadow-mode answerability signals.

This module deliberately does not decide whether an answer is sufficient.
It describes only the authorized, post-rerank evidence that the existing
pipeline is about to send to generation. BGE scores are raw ranking signals,
not probabilities or calibrated confidence values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import log
from typing import Literal

from app.retrieval.hybrid_search import SearchResult

AnswerabilityReason = Literal[
    "NO_RETRIEVAL_CANDIDATES",
    "NO_AUTHORIZED_EVIDENCE",
    "EMPTY_RERANK_RESULT",
    "FEATURES_AVAILABLE",
]


@dataclass(frozen=True)
class StructuralAnswerabilityFeatures:
    """Relative and source-level signals derived from authorized top-five hits."""

    score_decay_1_2: float | None
    score_decay_1_3: float | None
    score_decay_1_5: float | None
    top1_to_mean_top5_ratio: float | None
    top1_to_median_top5_ratio: float | None
    top2_to_mean_top5_ratio: float | None
    score_range_top5: float | None
    score_iqr_top5: float | None
    unique_source_ratio_top5: float | None
    duplicate_source_ratio_top5: float | None
    max_chunks_from_same_source: int | None
    top_source_chunk_share: float | None
    source_rank_entropy: float | None
    source_score_entropy: float | None
    source_top1_score: float | None
    source_top2_score: float | None
    source_margin: float | None
    source_mean_score: float | None
    source_count: int | None

    def as_dict(self) -> dict:
        return {
            "score_decay_1_2": self.score_decay_1_2,
            "score_decay_1_3": self.score_decay_1_3,
            "score_decay_1_5": self.score_decay_1_5,
            "top1_to_mean_top5_ratio": self.top1_to_mean_top5_ratio,
            "top1_to_median_top5_ratio": self.top1_to_median_top5_ratio,
            "top2_to_mean_top5_ratio": self.top2_to_mean_top5_ratio,
            "score_range_top5": self.score_range_top5,
            "score_iqr_top5": self.score_iqr_top5,
            "unique_source_ratio_top5": self.unique_source_ratio_top5,
            "duplicate_source_ratio_top5": self.duplicate_source_ratio_top5,
            "max_chunks_from_same_source": self.max_chunks_from_same_source,
            "top_source_chunk_share": self.top_source_chunk_share,
            "source_rank_entropy": self.source_rank_entropy,
            "source_score_entropy": self.source_score_entropy,
            "source_top1_score": self.source_top1_score,
            "source_top2_score": self.source_top2_score,
            "source_margin": self.source_margin,
            "source_mean_score": self.source_mean_score,
            "source_count": self.source_count,
        }


@dataclass(frozen=True)
class AnswerabilityFeatures:
    """Raw features measured after ACL and reranking.

    ``None`` means that the current pipeline does not expose a trustworthy
    value. In particular, the single Qdrant RRF query does not expose the
    independent dense/sparse ranks, and asking again would change retrieval
    semantics and duplicate work.
    """

    pre_acl_candidate_count: int | None
    authorized_candidate_count: int
    reranked_count: int
    top1_score: float | None
    top2_score: float | None
    top3_score: float | None
    top1_top2_margin: float | None
    top1_top3_margin: float | None
    mean_top3_score: float | None
    mean_top5_score: float | None
    min_top5_score: float | None
    max_top5_score: float | None
    std_top5_score: float | None
    distinct_source_count_top5: int | None
    distinct_document_count_top5: int | None
    top1_fused_rank: int | None
    top1_dense_rank: int | None
    top1_sparse_rank: int | None
    dense_sparse_agreement: float | None
    fused_rerank_agreement: float | None
    source_score_concentration: float | None
    duplicate_source_chunk_count_top5: int | None
    structural: StructuralAnswerabilityFeatures
    feature_latency_ms: float

    def as_dict(self) -> dict:
        output = {
            "pre_acl_candidate_count": self.pre_acl_candidate_count,
            "authorized_candidate_count": self.authorized_candidate_count,
            "reranked_count": self.reranked_count,
            "top1_score": self.top1_score,
            "top2_score": self.top2_score,
            "top3_score": self.top3_score,
            "top1_top2_margin": self.top1_top2_margin,
            "top1_top3_margin": self.top1_top3_margin,
            "mean_top3_score": self.mean_top3_score,
            "mean_top5_score": self.mean_top5_score,
            "min_top5_score": self.min_top5_score,
            "max_top5_score": self.max_top5_score,
            "std_top5_score": self.std_top5_score,
            "distinct_source_count_top5": self.distinct_source_count_top5,
            "distinct_document_count_top5": self.distinct_document_count_top5,
            "top1_fused_rank": self.top1_fused_rank,
            "top1_dense_rank": self.top1_dense_rank,
            "top1_sparse_rank": self.top1_sparse_rank,
            "dense_sparse_agreement": self.dense_sparse_agreement,
            "fused_rerank_agreement": self.fused_rerank_agreement,
            "source_score_concentration": self.source_score_concentration,
            "duplicate_source_chunk_count_top5": self.duplicate_source_chunk_count_top5,
            "feature_latency_ms": round(self.feature_latency_ms, 3),
        }
        output.update(self.structural.as_dict())
        return output


@dataclass(frozen=True)
class AnswerabilityObservation:
    reason: AnswerabilityReason
    features: AnswerabilityFeatures
    top_authorized_source_ids: list[str]
    top_raw_reranker_scores: list[float]

    def as_dict(self) -> dict:
        return {
            "reason": self.reason,
            "features": self.features.as_dict(),
            "top_authorized_source_ids": self.top_authorized_source_ids,
            "top_raw_reranker_scores": self.top_raw_reranker_scores,
        }


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _relative_gap(first: float, second: float) -> float:
    denominator = max(abs(first), abs(second), 1e-12)
    return (first - second) / denominator


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if abs(denominator) > 1e-12 else None


def _normalized_entropy(values: list[float]) -> float | None:
    total = sum(values)
    if not values or total <= 1e-12:
        return 0.0 if values else None
    probabilities = [value / total for value in values if value > 0]
    entropy = -sum(probability * log(probability) for probability in probabilities)
    return entropy / log(len(values)) if len(values) > 1 else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight


def extract_structural_features(
    scores: list[float], source_ids: list[str | None]
) -> StructuralAnswerabilityFeatures:
    """Compute finite, authorized top-five structural signals only."""
    if not scores:
        return StructuralAnswerabilityFeatures(*(None for _ in range(19)))

    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores) // 2]
    if len(sorted_scores) % 2 == 0:
        median_score = (sorted_scores[len(sorted_scores) // 2 - 1] + median_score) / 2
    q1 = _percentile(sorted_scores, 0.25)
    q3 = _percentile(sorted_scores, 0.75)
    source_counts: dict[str, int] = {}
    source_scores: dict[str, list[float]] = {}
    for source_id, score in zip(source_ids, scores):
        if source_id:
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
            source_scores.setdefault(source_id, []).append(score)
    source_max_scores = sorted(
        (max(values) for values in source_scores.values()), reverse=True
    )
    source_top1 = source_max_scores[0] if source_max_scores else None
    source_top2 = source_max_scores[1] if len(source_max_scores) > 1 else None
    absolute_scores = [abs(score) for score in scores]
    source_absolute_scores = [
        sum(abs(score) for score in values) for values in source_scores.values()
    ]
    max_source_count = max(source_counts.values()) if source_counts else None
    unique_count = len(source_counts) if source_counts else None
    count = len(scores)
    return StructuralAnswerabilityFeatures(
        score_decay_1_2=_rounded(
            _relative_gap(scores[0], scores[1]) if len(scores) >= 2 else None
        ),
        score_decay_1_3=_rounded(
            _relative_gap(scores[0], scores[2]) if len(scores) >= 3 else None
        ),
        score_decay_1_5=_rounded(
            _relative_gap(scores[0], scores[4]) if len(scores) >= 5 else None
        ),
        top1_to_mean_top5_ratio=_rounded(
            _safe_ratio(abs(scores[0]), sum(absolute_scores) / count)
        ),
        top1_to_median_top5_ratio=_rounded(
            _safe_ratio(abs(scores[0]), abs(median_score))
        ),
        top2_to_mean_top5_ratio=(
            _rounded(_safe_ratio(abs(scores[1]), sum(absolute_scores) / count))
            if len(scores) >= 2
            else None
        ),
        score_range_top5=_rounded(max(scores) - min(scores)),
        score_iqr_top5=_rounded(q3 - q1),
        unique_source_ratio_top5=_rounded(
            unique_count / count if unique_count is not None else None
        ),
        duplicate_source_ratio_top5=_rounded(
            (count - unique_count) / count if unique_count is not None else None
        ),
        max_chunks_from_same_source=max_source_count,
        top_source_chunk_share=_rounded(
            max_source_count / count if max_source_count is not None else None
        ),
        source_rank_entropy=_rounded(
            _normalized_entropy([float(value) for value in source_counts.values()])
        ),
        source_score_entropy=_rounded(_normalized_entropy(source_absolute_scores)),
        source_top1_score=_rounded(source_top1),
        source_top2_score=_rounded(source_top2),
        source_margin=(
            _rounded(source_top1 - source_top2)
            if source_top1 is not None and source_top2 is not None
            else None
        ),
        source_mean_score=(
            _rounded(sum(source_max_scores) / len(source_max_scores))
            if source_max_scores
            else None
        ),
        source_count=unique_count,
    )


def extract_answerability_observation(
    reranked_results: list[SearchResult],
    *,
    authorized_candidate_count: int,
    pre_acl_candidate_count: int | None = None,
) -> AnswerabilityObservation:
    """Extract features from only the authorized final result list.

    ``pre_acl_candidate_count`` is optional because the production Qdrant
    query pushes ACL into retrieval and intentionally does not perform a
    second unrestricted query merely to count unauthorized points.
    """
    started = time.perf_counter()
    top = reranked_results[:5]
    scores = [float(result.score) for result in top]
    source_ids = [result.payload.get("source_id") for result in top]
    valid_source_ids = [source_id for source_id in source_ids if source_id]
    document_ids = [result.payload.get("doc_id") for result in top]
    valid_document_ids = [document_id for document_id in document_ids if document_id]

    top1 = scores[0] if len(scores) >= 1 else None
    top2 = scores[1] if len(scores) >= 2 else None
    top3 = scores[2] if len(scores) >= 3 else None
    mean_top3 = sum(scores[:3]) / len(scores[:3]) if scores else None
    mean_top5 = sum(scores) / len(scores) if scores else None
    concentration_denominator = sum(abs(score) for score in scores)
    concentration = (
        max(abs(score) for score in scores) / concentration_denominator
        if concentration_denominator
        else None
    )

    if authorized_candidate_count == 0:
        reason: AnswerabilityReason = (
            "NO_AUTHORIZED_EVIDENCE"
            if pre_acl_candidate_count is not None and pre_acl_candidate_count > 0
            else "NO_RETRIEVAL_CANDIDATES"
        )
    elif not reranked_results:
        reason = "EMPTY_RERANK_RESULT"
    else:
        reason = "FEATURES_AVAILABLE"

    features = AnswerabilityFeatures(
        pre_acl_candidate_count=pre_acl_candidate_count,
        authorized_candidate_count=authorized_candidate_count,
        reranked_count=len(reranked_results),
        top1_score=_rounded(top1),
        top2_score=_rounded(top2),
        top3_score=_rounded(top3),
        top1_top2_margin=_rounded(top1 - top2 if top1 is not None and top2 is not None else None),
        top1_top3_margin=_rounded(top1 - top3 if top1 is not None and top3 is not None else None),
        mean_top3_score=_rounded(mean_top3),
        mean_top5_score=_rounded(mean_top5),
        min_top5_score=_rounded(min(scores) if scores else None),
        max_top5_score=_rounded(max(scores) if scores else None),
        std_top5_score=_rounded(
            (sum((score - mean_top5) ** 2 for score in scores) / len(scores)) ** 0.5
            if scores and mean_top5 is not None
            else None
        ),
        distinct_source_count_top5=len(set(valid_source_ids)) if valid_source_ids else None,
        distinct_document_count_top5=len(set(valid_document_ids)) if valid_document_ids else None,
        # These are intentionally unavailable: hybrid_search receives RRF's
        # fused result from one Qdrant call and does not expose branch ranks.
        top1_fused_rank=None,
        top1_dense_rank=None,
        top1_sparse_rank=None,
        dense_sparse_agreement=None,
        fused_rerank_agreement=None,
        source_score_concentration=_rounded(concentration),
        duplicate_source_chunk_count_top5=(
            len(valid_source_ids) - len(set(valid_source_ids))
            if valid_source_ids
            else None
        ),
        structural=extract_structural_features(scores, source_ids),
        feature_latency_ms=(time.perf_counter() - started) * 1000,
    )
    return AnswerabilityObservation(
        reason=reason,
        features=features,
        top_authorized_source_ids=valid_source_ids,
        top_raw_reranker_scores=[round(score, 6) for score in scores],
    )
