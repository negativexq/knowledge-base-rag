"""Deterministic, model-free reporting helpers for the Phase 5.5 closure."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable
from typing import Any


def records_by_candidate(payload: dict[str, Any]) -> dict[int, dict[str, dict[str, Any]]]:
    return {
        result["candidate_k"]: {record["query_id"]: record for record in result["records"]}
        for result in payload["results"]
    }


def first_rank(ranked_ids: list[str], source_id: str) -> int | None:
    try:
        return ranked_ids.index(source_id) + 1
    except ValueError:
        return None


def final_hit(record: dict[str, Any], top_n: int = 5) -> bool:
    return bool(set(record["ranked_source_ids"][:top_n]) & set(record["expected_source_ids"]))


def numerator_denominator(
    records: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool] | None = None
) -> dict[str, int | float | None]:
    selected = [record for record in records if predicate is None or predicate(record)]
    eligible = [record for record in selected if record["expected_source_ids"]]
    numerator = sum(final_hit(record) for record in eligible)
    return {
        "record_count": len(selected),
        "eligible_count": len(eligible),
        "numerator": numerator,
        "denominator": len(eligible),
        "recall_at_5": numerator / len(eligible) if eligible else None,
    }


def changed_queries(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_k = records_by_candidate(payload)
    changed: dict[str, list[dict[str, Any]]] = {"k20_hit_k15_miss": [], "k20_miss_k15_hit": []}
    for query_id in sorted(set(by_k[20]) & set(by_k[15])):
        k20 = by_k[20][query_id]
        k15 = by_k[15][query_id]
        hit20 = final_hit(k20)
        hit15 = final_hit(k15)
        if hit20 == hit15:
            continue
        expected = sorted(k20["expected_source_ids"])
        changed_key = "k20_hit_k15_miss" if hit20 else "k20_miss_k15_hit"
        changed[changed_key].append(
            {
                "query_id": query_id,
                "case_family": k20["case_family"],
                "category": k20["category"],
                "query_language": k20["query_language"],
                "evidence_language": k20["evidence_language"],
                "language_pair": k20["language_pair"],
                "tenant_id": k20["tenant_id"],
                "expected_source_ids": expected,
                "pre_rerank_k20_ranks": {
                    source_id: first_rank(k20["candidate_source_ids"], source_id)
                    for source_id in expected
                },
                "pre_rerank_k15_ranks": {
                    source_id: first_rank(k15["candidate_source_ids"], source_id)
                    for source_id in expected
                },
                "post_rerank_k20_first_ranks": {
                    source_id: first_rank(k20["ranked_source_ids"], source_id)
                    for source_id in expected
                },
                "post_rerank_k15_first_ranks": {
                    source_id: first_rank(k15["ranked_source_ids"], source_id)
                    for source_id in expected
                },
                "post_rerank_k20_top5_hit": hit20,
                "post_rerank_k15_top5_hit": hit15,
                "k20_ranked_top5": k20["ranked_source_ids"][:5],
                "k15_ranked_top5": k15["ranked_source_ids"][:5],
            }
        )
    return changed


def family_impact(
    payload: dict[str, Any], changed: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    by_k = records_by_candidate(payload)
    query_ids = sorted(
        item["query_id"]
        for direction in changed.values()
        for item in direction
    )
    output = []
    for query_id in query_ids:
        family = by_k[20][query_id]["case_family"]
        family_ids = sorted(
            item_id
            for item_id, item in by_k[20].items()
            if item["case_family"] == family and item["expected_source_ids"]
        )
        k20_values = [final_hit(by_k[20][item_id]) for item_id in family_ids]
        k15_values = [final_hit(by_k[15][item_id]) for item_id in family_ids]
        output.append(
            {
                "query_id": query_id,
                "case_family": family,
                "family_query_ids": family_ids,
                "family_query_count": len(family_ids),
                "k20_family_hits": sum(k20_values),
                "k20_family_recall_at_5": sum(k20_values) / len(k20_values),
                "k15_family_hits": sum(k15_values),
                "k15_family_recall_at_5": sum(k15_values) / len(k15_values),
            }
        )
    return output


def cross_lingual_membership(payload: dict[str, Any]) -> dict[str, Any]:
    by_k = records_by_candidate(payload)
    members = [
        record
        for record in by_k[20].values()
        if record["category"] == "cross_lingual"
    ]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in members:
        groups[record["language_pair"]].append(record)
    pair_data = {}
    for pair in sorted(groups):
        ids = sorted(record["query_id"] for record in groups[pair])
        pair_data[pair] = {"query_ids": ids}
        for candidate_k in (20, 15):
            rows = [by_k[candidate_k][query_id] for query_id in ids]
            counts = numerator_denominator(rows)
            pair_data[pair][f"k{candidate_k}"] = counts
    return {
        "category": "cross_lingual",
        "member_count": len(members),
        "member_ids": sorted(record["query_id"] for record in members),
        "language_pair_groups": pair_data,
        "other_or_mixed_pairs": sorted(
            pair for pair in groups if pair not in {"tr->en", "en->tr"}
        ),
    }


def ndcg_breakdown(
    record: dict[str, Any], top_n: int = 5, candidate_k: int | None = None
) -> dict[str, Any]:
    expected = set(record["expected_source_ids"])
    unique_ranked = list(dict.fromkeys(record["ranked_source_ids"]))
    top = unique_ranked[:top_n]
    dcg = sum(
        1 / math.log2(rank + 2)
        for rank, source_id in enumerate(top)
        if source_id in expected
    )
    ideal_hits = min(len(expected), top_n)
    idcg = sum(1 / math.log2(rank + 2) for rank in range(ideal_hits))
    return {
        "query_id": record["query_id"],
        "candidate_k": candidate_k,
        "expected_source_ids": sorted(expected),
        "unique_ranked_top5": top,
        "dcg": round(dcg, 6),
        "idcg": round(idcg, 6),
        "ndcg_at_5": round(dcg / idcg, 6) if idcg else 0.0,
    }
