"""Deterministic, shadow-mode answerability signals.

This module deliberately does not decide whether an answer is sufficient.
It describes only the authorized, post-rerank evidence that the existing
pipeline is about to send to generation. BGE scores are raw ranking signals,
not probabilities or calibrated confidence values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from app.retrieval.hybrid_search import SearchResult

AnswerabilityReason = Literal[
    "NO_RETRIEVAL_CANDIDATES",
    "NO_AUTHORIZED_EVIDENCE",
    "EMPTY_RERANK_RESULT",
    "FEATURES_AVAILABLE",
]


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
    feature_latency_ms: float

    def as_dict(self) -> dict:
        return {
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
        feature_latency_ms=(time.perf_counter() - started) * 1000,
    )
    return AnswerabilityObservation(
        reason=reason,
        features=features,
        top_authorized_source_ids=valid_source_ids,
        top_raw_reranker_scores=[round(score, 6) for score in scores],
    )
