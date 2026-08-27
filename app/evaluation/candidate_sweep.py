# ruff: noqa: E501

"""Pure, model-free metrics for the Phase 5.5 candidate-k sweep."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, median
from typing import Any

REFERENCE_CANDIDATE_K = 20
EXPERIMENTAL_CANDIDATE_K = (15, 10)
SWEEP_CANDIDATE_K = (20, 15, 10)
TOP_N = 5
CRITICAL_SLICES = (
    "cross_lingual",
    "hard_answerable",
    "multi_document",
    "version_conflict",
    "injection_bearing",
)


def validate_candidate_k(candidate_k: int, top_n: int = TOP_N) -> None:
    if candidate_k < top_n:
        raise ValueError(f"candidate_k must be >= top_n ({top_n}), got {candidate_k}")


def source_ids(results: list[Any]) -> list[str]:
    return [result.payload["source_id"] for result in results]


def _hits(ranked: list[str], expected: list[str], limit: int | None = None) -> int:
    expected_set = set(expected)
    return sum(1 for source_id in set(ranked[:limit]) if source_id in expected_set)


def recall(ranked: list[str], expected: list[str], limit: int | None = None) -> float:
    if not expected:
        return 0.0
    return _hits(ranked, expected, limit) / len(set(expected))


def pre_rerank_metrics(candidate_ids: list[str], expected_ids: list[str]) -> dict[str, float | None]:
    """Return candidate-set recall plus top-10/15/20 views where available."""
    return {
        "candidate_recall": recall(candidate_ids, expected_ids),
        "recall_at_10": recall(candidate_ids, expected_ids, 10),
        "recall_at_15": recall(candidate_ids, expected_ids, 15) if len(candidate_ids) >= 15 else None,
        "recall_at_20": recall(candidate_ids, expected_ids, 20) if len(candidate_ids) >= 20 else None,
        "any_required_evidence": float(bool(set(candidate_ids) & set(expected_ids))),
        "all_required_evidence": float(set(expected_ids) <= set(candidate_ids)) if expected_ids else 0.0,
    }


def post_rerank_metrics(ranked_ids: list[str], expected_ids: list[str], top_n: int = TOP_N) -> dict[str, float]:
    expected = set(expected_ids)
    # Ground truth is source-level while retrieval returns chunks.  Count a
    # source only at its first ranked occurrence; duplicate chunks must not
    # earn duplicate DCG credit or make nDCG exceed 1.
    unique_ranked_ids = list(dict.fromkeys(ranked_ids))
    top = unique_ranked_ids[:top_n]
    hits = [source_id for source_id in top if source_id in expected]
    dcg = sum(1 / math.log2(rank + 2) for rank, source_id in enumerate(top) if source_id in expected)
    ideal_hits = min(len(expected), top_n)
    idcg = sum(1 / math.log2(rank + 2) for rank in range(ideal_hits))
    # MRR retains the existing chunk-rank semantics.  Only nDCG needs
    # source-level de-duplication because duplicate chunks would otherwise
    # receive duplicate relevance credit.
    first_rank = next((rank for rank, source_id in enumerate(ranked_ids, start=1) if source_id in expected), None)
    return {
        "recall_at_5": len(set(hits)) / len(expected) if expected else 0.0,
        "mrr": 1 / first_rank if first_rank else 0.0,
        "ndcg_at_5": dcg / idcg if idcg else 0.0,
    }


def classify_rescue_drop(
    candidate_ids: list[str], ranked_ids: list[str], expected_ids: list[str], top_n: int = TOP_N
) -> str:
    """Classify any required evidence crossing the pre/post top-n boundary."""
    before = bool(set(candidate_ids[:top_n]) & set(expected_ids))
    after = bool(set(ranked_ids[:top_n]) & set(expected_ids))
    if after and not before:
        return "rescued"
    if before and not after:
        return "dropped"
    return "unchanged"


def _mean_fields(records: list[dict], fields: tuple[str, ...]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for field in fields:
        values = [record[field] for record in records if record.get(field) is not None]
        result[field] = round(mean(values), 6) if values else None
    return result


def aggregate_query_records(records: list[dict]) -> dict[str, Any]:
    fields = (
        "candidate_recall",
        "any_required_evidence",
        "all_required_evidence",
        "recall_at_10",
        "recall_at_15",
        "recall_at_20",
        "recall_at_5",
        "mrr",
        "ndcg_at_5",
    )
    return {"query_count": len(records), **_mean_fields(records, fields)}


def aggregate_case_families(records: list[dict]) -> dict[str, Any]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item["query_id"]):
        groups[record["case_family"]].append(record)
    family_means = [aggregate_query_records(groups[family]) for family in sorted(groups)]
    fields = (
        "candidate_recall",
        "any_required_evidence",
        "all_required_evidence",
        "recall_at_10",
        "recall_at_15",
        "recall_at_20",
        "recall_at_5",
        "mrr",
        "ndcg_at_5",
    )
    return {"case_family_count": len(groups), **_mean_fields(family_means, fields)}


def summarize_latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean_ms": round(mean(values), 3),
        "median_ms": round(median(values), 3),
        "p50_ms": round(ordered[round(0.50 * (len(ordered) - 1))], 3),
        "p95_ms": round(ordered[round(0.95 * (len(ordered) - 1))], 3),
        "max_ms": round(max(values), 3),
    }


def recommend_candidate_k(
    results: list[dict], slice_metrics: dict[str, dict[str, dict[str, dict]]]
) -> dict[str, Any]:
    """Recommend the fastest candidate with no observed critical quality loss."""
    by_k = {result["candidate_k"]: result for result in results}
    reference = by_k[REFERENCE_CANDIDATE_K]
    reference_query = reference["query_level"]
    reference_family = reference["case_family_level"]
    candidates = []
    for candidate_k in EXPERIMENTAL_CANDIDATE_K:
        # Calibration closure intentionally runs only the requested comparison
        # (20 vs 15).  Do not require the previously rejected k=10 result just
        # to build a partial comparison artifact.
        if candidate_k not in by_k:
            continue
        result = by_k[candidate_k]
        query = result["query_level"]
        family = result["case_family_level"]
        regressions = []
        if query["recall_at_5"] < reference_query["recall_at_5"]:
            regressions.append("overall query Recall@5")
        if family["recall_at_5"] < reference_family["recall_at_5"]:
            regressions.append("case-family Recall@5")
        for slice_name in CRITICAL_SLICES:
            reference_slice = slice_metrics["category"][str(REFERENCE_CANDIDATE_K)].get(slice_name)
            candidate_slice = slice_metrics["category"][str(candidate_k)].get(slice_name)
            if not reference_slice or not candidate_slice:
                continue
            reference_r5 = reference_slice["query_level"].get("recall_at_5")
            candidate_r5 = candidate_slice["query_level"].get("recall_at_5")
            if (
                reference_r5 is not None
                and candidate_r5 is not None
                and candidate_r5 < reference_r5
            ):
                regressions.append(f"{slice_name} Recall@5")
        candidates.append(
            {
                "candidate_k": candidate_k,
                "quality_deltas_vs_reference": {
                    "candidate_recall": round(
                        query["candidate_recall"] - reference_query["candidate_recall"], 6
                    ),
                    "all_required_evidence_recall": round(
                        query["all_required_evidence"]
                        - reference_query["all_required_evidence"],
                        6,
                    ),
                    "recall_at_5": round(query["recall_at_5"] - reference_query["recall_at_5"], 6),
                    "mrr": round(query["mrr"] - reference_query["mrr"], 6),
                    "ndcg_at_5": round(query["ndcg_at_5"] - reference_query["ndcg_at_5"], 6),
                    "family_recall_at_5": round(
                        family["recall_at_5"] - reference_family["recall_at_5"], 6
                    ),
                },
                "critical_slice_regressions": regressions,
                "reranker_p95_delta_ms": round(
                    result["latency"]["reranker"]["p95_ms"]
                    - reference["latency"]["reranker"]["p95_ms"],
                    3,
                ),
                "total_p95_delta_ms": round(
                    result["latency"]["total_pipeline"]["p95_ms"]
                    - reference["latency"]["total_pipeline"]["p95_ms"],
                    3,
                ),
            }
        )
    eligible = [candidate for candidate in candidates if not candidate["critical_slice_regressions"]]
    eligible = [
        candidate
        for candidate in eligible
        if candidate["quality_deltas_vs_reference"]["recall_at_5"] >= 0
        and candidate["quality_deltas_vs_reference"]["family_recall_at_5"] >= 0
    ]
    recommendation = (
        f"PROMOTE {min(eligible, key=lambda item: item['candidate_k'])['candidate_k']}"
        if eligible
        else "KEEP 20"
        if candidates
        else "INCONCLUSIVE"
    )
    return {
        "recommendation": recommendation,
        "best_measured_candidate": min(eligible, key=lambda item: item["candidate_k"])["candidate_k"]
        if eligible
        else REFERENCE_CANDIDATE_K,
        "candidates": candidates,
        "automatic_promotion": False,
    }
