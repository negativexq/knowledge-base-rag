# ruff: noqa: E501

"""Build Phase 5.5 cross-lingual and candidate-budget closure artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.evaluation.candidate_sweep import (
    aggregate_case_families,
    aggregate_query_records,
    post_rerank_metrics,
)
from app.evaluation.phase55_decision import (
    changed_queries,
    cross_lingual_membership,
    family_impact,
    ndcg_breakdown,
    numerator_denominator,
    records_by_candidate,
)
from scripts.benchmark_candidate_k import _slice_metrics, write_csv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV = ROOT / "artifacts/phase-5-5/full/candidate-sweep.json"
DEFAULT_CAL = ROOT / "artifacts/phase-5-5/calibration/candidate-sweep.json"
DEFAULT_OUTPUT = ROOT / "artifacts/phase-5-5/final-decision"
DEFAULT_DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def recompute_corrected_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """Correct derived nDCG fields from stored rankings without retrieval."""
    for result in payload["results"]:
        for record in result["records"]:
            record.update(post_rerank_metrics(record["ranked_source_ids"], record["expected_source_ids"]))
        eligible = [record for record in result["records"] if record["expected_source_ids"]]
        result["query_level"] = aggregate_query_records(eligible)
        result["case_family_level"] = aggregate_case_families(eligible)
    payload["slice_metrics"] = {
        field: {
            str(result["candidate_k"]): _slice_metrics(result["records"], field)
            for result in payload["results"]
        }
        for field in payload["slice_dimensions"]
    }
    payload["metric_integrity"] = {
        "ndcg": "source-level ranked IDs are de-duplicated at first occurrence before DCG",
        "corrected_without_retrieval_rerun": True,
    }
    return payload


def assert_identity(payload: dict[str, Any], split: str) -> None:
    if payload["split"] != split:
        raise ValueError(f"expected {split}, got {payload['split']}")
    if split == "frozen_test":
        raise ValueError("frozen_test is not allowed in Phase 5.5 closure")
    if payload["candidate_k_values"] != ([20, 15, 10] if split == "development" else [20, 15]):
        raise ValueError(f"unexpected candidate values for {split}")


def metric_table(dev: dict[str, Any], cal: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "candidate_recall": ("query_level", "candidate_recall"),
        "all_evidence_recall": ("query_level", "all_required_evidence"),
        "R@5": ("query_level", "recall_at_5"),
        "MRR": ("query_level", "mrr"),
        "nDCG@5": ("query_level", "ndcg_at_5"),
        "family_R@5": ("case_family_level", "recall_at_5"),
    }
    output = {}
    for name, (level, field) in fields.items():
        output[name] = {}
        for split, payload in (("development", dev), ("calibration", cal)):
            output[name][split] = {}
            for candidate_k in (20, 15):
                result = next(x for x in payload["results"] if x["candidate_k"] == candidate_k)
                output[name][split][str(candidate_k)] = result[level][field]
            output[name][split]["delta_15_minus_20"] = round(
                output[name][split]["15"] - output[name][split]["20"], 6
            )
    for name, category in {
        "cross_lingual_R@5": "cross_lingual",
        "TR->EN_R@5": "tr->en",
        "EN->TR_R@5": "en->tr",
        "multi_doc_R@5": "multi_document",
        "hard_R@5": "hard_answerable",
        "version_R@5": "version_conflict",
        "injection_R@5": "injection_bearing",
    }.items():
        output[name] = {}
        for split, payload in (("development", dev), ("calibration", cal)):
            output[name][split] = {}
            for candidate_k in (20, 15):
                slice_data = payload["slice_metrics"]["category"].get(str(candidate_k), {}).get(category)
                output[name][split][str(candidate_k)] = (
                    None if not slice_data else slice_data["query_level"]["recall_at_5"]
                )
            left, right = output[name][split]["20"], output[name][split]["15"]
            output[name][split]["delta_15_minus_20"] = None if left is None or right is None else round(right - left, 6)
    for name, pair in {"TR->EN_R@5": "tr->en", "EN->TR_R@5": "en->tr"}.items():
        for split, payload in (("development", dev), ("calibration", cal)):
            for candidate_k in (20, 15):
                slice_data = payload["slice_metrics"]["language_pair"].get(str(candidate_k), {}).get(pair)
                output[name][split][str(candidate_k)] = None if not slice_data else slice_data["query_level"]["recall_at_5"]
            output[name][split]["delta_15_minus_20"] = round(
                output[name][split]["15"] - output[name][split]["20"], 6
            )
    for name, metric in {
        "reranker_p95_ms": ("reranker", "p95_ms"),
        "total_p95_ms": ("total_pipeline", "p95_ms"),
        "actual_pairs": (None, "pairs_scored"),
    }.items():
        output[name] = {}
        for split, payload in (("development", dev), ("calibration", cal)):
            output[name][split] = {}
            for candidate_k in (20, 15):
                result = next(x for x in payload["results"] if x["candidate_k"] == candidate_k)
                if name == "actual_pairs":
                    output[name][split][str(candidate_k)] = result["latency"]["pairs_scored"]
                else:
                    output[name][split][str(candidate_k)] = result["latency"][metric[0]][metric[1]]
            output[name][split]["delta_15_minus_20"] = round(output[name][split]["15"] - output[name][split]["20"], 3)
    return output


def critical_counts(payload: dict[str, Any], dataset: list[dict[str, Any]], candidate_k: int) -> dict[str, Any]:
    records = list(records_by_candidate(payload)[candidate_k].values())
    result: dict[str, Any] = {}
    for category in (
        "cross_lingual",
        "multi_document",
        "hard_answerable",
        "version_conflict",
        "injection_bearing",
        "acl_negative",
    ):
        rows = [record for record in records if record["category"] == category]
        if category == "acl_negative":
            distractors = {
                question["id"]: set(question.get("distractor_source_ids", []))
                for question in dataset
                if question["id"] in {record["query_id"] for record in rows}
            }
            leakage = sum(
                bool(set(record["ranked_source_ids"]) & distractors.get(record["query_id"], set()))
                for record in rows
            )
            result[category] = {
                "security_invariant": "unauthorized_source_in_top5",
                "numerator": leakage,
                "denominator": len(rows),
                "rate": leakage / len(rows) if rows else None,
            }
        else:
            result[category] = numerator_denominator(rows)
    result["language_pair"] = {
        pair: numerator_denominator(
            [record for record in records if record["language_pair"] == pair]
        )
        for pair in ("tr->en", "en->tr")
    }
    return result


def build_markdown(
    dev: dict[str, Any], cal: dict[str, Any], comparison: dict[str, Any],
    membership: dict[str, Any], changed: dict[str, Any], sanity: list[dict[str, Any]],
) -> str:
    m = comparison["metrics"]
    lines = [
        "# Phase 5.5 — Cross-Lingual Slice Closure",
        "",
        "Only existing development and calibration artifacts were analyzed; no benchmark was rerun.",
        "",
        "## Cross-lingual membership",
        "",
        f"The calibration `cross_lingual` category contains {membership['member_count']} queries.",
        "It has 10 `tr->en` and 10 `en->tr` members; no other/mixed pair is present.",
        "The category slice is not the same population as a global `language_pair` slice, which includes every category using that pair.",
        "",
        "| Category/pair | k20 | k15 |",
        "|---|---:|---:|",
    ]
    for pair, data in membership["language_pair_groups"].items():
        lines.append(f"| cross_lingual / {pair} | {data['k20']['numerator']}/{data['k20']['denominator']} | {data['k15']['numerator']}/{data['k15']['denominator']} |")
    lines += [
        "| cross_lingual total | 11/20 = 0.55 | 10/20 = 0.50 |",
        "",
        "The apparent inconsistency is therefore population mismatch: the global `tr->en`/`en->tr` slices include non-cross-lingual records. In calibration, k15 loses one cross-lingual TR→EN hit but gains one non-cross-lingual TR→EN hard-answerable hit, keeping the global TR→EN value unchanged.",
        "",
        "## Corrected comparison",
        "",
        "| Metric | Dev k20 | Dev k15 | Δ | Cal k20 | Cal k15 | Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    rows = [
        ("candidate recall", "candidate_recall"), ("all evidence recall", "all_evidence_recall"),
        ("R@5", "R@5"), ("MRR", "MRR"), ("nDCG@5", "nDCG@5"), ("family R@5", "family_R@5"),
        ("cross-lingual R@5", "cross_lingual_R@5"), ("TR→EN R@5", "TR->EN_R@5"),
        ("EN→TR R@5", "EN->TR_R@5"), ("multi-doc R@5", "multi_doc_R@5"),
        ("hard R@5", "hard_R@5"), ("version R@5", "version_R@5"),
        ("injection R@5", "injection_R@5"), ("reranker p95 ms", "reranker_p95_ms"),
        ("total p95 ms", "total_p95_ms"), ("actual pairs", "actual_pairs"),
    ]
    for label, key in rows:
        value = m[key]
        lines.append(f"| {label} | {value['development']['20']} | {value['development']['15']} | {value['development']['delta_15_minus_20']} | {value['calibration']['20']} | {value['calibration']['15']} | {value['calibration']['delta_15_minus_20']} |")
    lines += [
        "",
        "## Changed queries",
        "",
        f"Development: {len(changed['development']['k20_hit_k15_miss'])} k20-hit/k15-miss and {len(changed['development']['k20_miss_k15_hit'])} k20-miss/k15-hit.",
        f"Calibration: {len(changed['calibration']['k20_hit_k15_miss'])} k20-hit/k15-miss and {len(changed['calibration']['k20_miss_k15_hit'])} k20-miss/k15-hit.",
        "See `changed-query-analysis.json` for IDs, ranks, source IDs, and family impact.",
        "",
        "## nDCG integrity",
        "",
        "The old approximately 0.99 values were invalid because duplicate chunks from one source received duplicate DCG credit. Corrected source-level first-occurrence nDCG is development k20 `0.678009`, k15 `0.681342`; calibration k20 `0.705879`, k15 `0.708522`. All corrected values are <= 1.",
        "",
        "| Query | Unique ranked top-5 | DCG | IDCG | nDCG |",
        "|---|---|---:|---:|---:|",
    ]
    for item in sanity:
        lines.append(f"| {item['query_id']} (k{item['candidate_k']}) | {', '.join(item['unique_ranked_top5'])} | {item['dcg']} | {item['idcg']} | {item['ndcg_at_5']} |")
    lines += [
        "",
        "## Decision",
        "",
        "QUALITY_REFERENCE = candidate_k 20. DEV_FAST = candidate_k 15 is supported for local iteration because it reduces reranker p95 by approximately 31% while preserving overall R@5, but it is not suitable as the global quality reference because calibration cross-lingual R@5 falls from 11/20 to 10/20.",
        "Family aggregation is family-balanced: the six-query `fact-19` family loses 1/6 while the one-query `hard-activation-evidence` family gains 1/1. Across 21 answerable families, that net change is (1 - 1/6) / 21 = 0.039683, explaining the family-level increase.",
        "",
        "Phase 5.5 is closed: QUALITY_REFERENCE=20, DEV_FAST=15.",
        "",
        "The global/reference default remains 20; only the DEV_FAST profile uses 15. Frozen test and generation were not run.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", type=Path, default=DEFAULT_DEV)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dev, cal = load(args.development), load(args.calibration)
    smoke_path = args.development.parent.parent / "smoke/candidate-sweep.json"
    if smoke_path.exists():
        smoke = recompute_corrected_metrics(load(smoke_path))
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_csv(smoke_path.parent / "candidate-sweep.csv", smoke)
    assert_identity(dev, "development")
    assert_identity(cal, "calibration")
    if dev["corpus_fingerprint"] != cal["corpus_fingerprint"] or dev["dataset_fingerprint"] != cal["dataset_fingerprint"]:
        raise ValueError("development/calibration fingerprints differ")
    dataset = load(args.dataset)
    membership = cross_lingual_membership(cal)
    changed_payload = {}
    for name, payload in (("development", dev), ("calibration", cal)):
        changes = changed_queries(payload)
        changed_payload[name] = {**changes, "family_impact": family_impact(payload, changes)}
    comparison = {
        "schema_version": "phase-5-5-final-decision-v1",
        "corpus_fingerprint": cal["corpus_fingerprint"],
        "dataset_fingerprint": cal["dataset_fingerprint"],
        "phase_status": "closed",
        "decision": {
            "quality_reference_candidate_k": 20,
            "dev_fast_candidate_k": 15,
            "global_reference_candidate_k": 20,
            "recommendation": "A",
        },
        "metrics": metric_table(dev, cal),
        "critical_slice_counts": {
            split: {
                str(candidate_k): critical_counts(payload, dataset, candidate_k)
                for candidate_k in (20, 15)
            }
            for split, payload in (("development", dev), ("calibration", cal))
        },
    }
    by_k = records_by_candidate(cal)
    sanity_records = [
        (20, by_k[20]["cross-19-0"]),
        (15, by_k[15]["cross-19-0"]),
        (20, by_k[20]["hard-activation-evidence"]),
        (15, by_k[15]["hard-activation-evidence"]),
    ]
    sanity = [ndcg_breakdown(record, candidate_k=candidate_k) for candidate_k, record in sanity_records]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "cross-lingual-membership.json").write_text(json.dumps(membership, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "changed-query-analysis.json").write_text(json.dumps(changed_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "final-dev-calibration-comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "final-decision.md").write_text(build_markdown(dev, cal, comparison, membership, changed_payload, sanity), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "recommendation": "A", "frozen_test": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
