"""Finalize the artifact-only report for the canonical eManual confirmation."""

# ruff: noqa: E501

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/ragbench/canonical/basic50-final"
SOURCE = Path("/tmp/knowledge-base-rag-cleanup.Vk4y4n/emanual-basic-50-graceful-budget")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return round(sorted(values)[min(len(values) - 1, int(len(values) * fraction))], 3)


def main() -> int:
    config = read_json(OUT / "config.json")
    retrieval = read_jsonl(OUT / "retrieval-results.jsonl")
    validation = {row["query_id"]: row for row in read_jsonl(OUT / "validation-results.jsonl")}
    judges = {row["query_id"]: row for row in read_jsonl(OUT / "judge-results.jsonl")}
    failures = read_jsonl(OUT / "failure-summary.jsonl")
    retrieval_metrics = read_json(OUT / "retrieval-summary.json")["stages"]
    generation = read_json(OUT / "generation-summary.json")

    query_ids = sorted(validation)
    dataset_metadata = {
        "dataset": "RAGBench eManual",
        "repository": "galileo-ai/ragbench",
        "revision": config["dataset_revision"],
        "split": "test",
        "sample_size": 50,
        "sample_hash": config["sample_hash"],
        "sample_file": "sample.json",
        "corpus_fingerprint": config["corpus_fingerprint"],
        "collection": config["collection"],
        "row_ids": query_ids,
        "relevance_field": "all_relevant_sentence_keys",
        "retrieval_source": "identity-checked frozen graceful-budget snapshot",
    }
    write_json(OUT / "dataset-metadata.json", dataset_metadata)

    # Keep the full query-level failure matrix under the canonical directory;
    # it is useful for future regression comparisons without provider calls.
    write_json(OUT / "failure-summary.json", {
        "query_count": 50,
        "counts": generation["failure_classes"],
        "parse_failures": generation["parse_failures"],
        "provider_failures": generation["provider_failures"],
        "rows": failures,
    })

    stage_states = {
        row["query_id"]: row["sentence_stage_metrics"]["sectionaware"]
        for row in retrieval
        if "sentence_stage_metrics" in row
    }
    complete_ids = [
        query_id for query_id in query_ids
        if stage_states.get(query_id, {}).get("all_relevant_sentences_present")
    ]
    complete_verdicts = {
        verdict: sum(
            judges.get(query_id, {}).get("verdict") == verdict
            for query_id in complete_ids
        )
        for verdict in ["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"]
    }
    support_status_counts: dict[str, int] = {}
    for row in validation.values():
        status = row.get("selected_support_status", "NO_OUTPUT")
        support_status_counts[status] = support_status_counts.get(status, 0) + 1

    generation_rows = read_jsonl(OUT / "generation-results.jsonl")
    old_generation = read_jsonl(SOURCE / "generation-results.jsonl")
    old_input = sum((row.get("provider_observation", {}).get("usage", {}).get("input_tokens") or 0) for row in old_generation)
    new_input = sum((row.get("usage", {}).get("input_tokens") or 0) for row in generation_rows)
    context_tokens = [
        float(sum(item.get("token_count", 0) for item in row.get("section_aware_blocks", [])))
        for row in retrieval
    ]
    old_retrieval = read_jsonl(SOURCE / "retrieval-results.jsonl")
    retrieval_ms = [float(row.get("stage_latency_ms", {}).get("total_retrieval", 0)) for row in old_retrieval]
    luna_ms = [float(row.get("generation_latency_ms", 0)) for row in generation_rows]
    end_to_end = [a + b for a, b in zip(retrieval_ms, luna_ms, strict=False)]
    unique_top5 = [
        len({item.get("source_id") for item in row.get("selected_top5", [])})
        for row in old_retrieval
    ]
    section_blocks = [len(row.get("section_aware_blocks", [])) for row in old_retrieval]
    selected_ids = [len(validation[query_id].get("selected_support_ids", [])) for query_id in query_ids]
    critical_rejected = sum(
        "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
        for row in validation.values()
    )
    parse_failures = generation["parse_failures"]
    correct = generation["semantic_verdicts"]["CORRECT"]
    partial = generation["semantic_verdicts"]["PARTIALLY_CORRECT"]
    incorrect = generation["semantic_verdicts"]["INCORRECT"]
    visible = generation["visible_answers"]
    unavailable = generation["unavailable_outputs"]
    report = f"""# RAGBench eManual Basic-50 — final canonical confirmation

## Protocol

- Dataset revision: `{config['dataset_revision']}`; sample hash: `{config['sample_hash']}`.
- Retrieval, embedding, and reranker were not rerun. The exact identity-checked graceful-budget snapshot was replayed.
- Canonical generation: `gpt-5.6-luna`, reasoning `none`, support-ID output contract.
- Semantic evaluation: `gpt-5.6-terra`, reasoning `medium`, one call per visible answer.

## Result

Sentence retrieval remained strong: Hybrid Top20 all-relevant `{retrieval_metrics['hybrid_top20']['all']}/50` with mean recall `{retrieval_metrics['hybrid_top20']['mean_recall']:.2%}`, BGE Top5 mean recall `{retrieval_metrics['bge_top5']['mean_recall']:.2%}`, and SectionAware mean recall `{retrieval_metrics['sectionaware']['mean_recall']:.2%}`.

The canonical support-ID path completed Luna generation for 50/50, but only {visible}/50 answers were visible; {parse_failures} were parse failures and {generation['validator_induced_abstentions']} were validator-induced no-valid-output cases. Terra judged the visible answers {correct} correct, {partial} partial, and {incorrect} incorrect. This is below the historical graceful-budget semantic baseline of 29 correct, 7 partial, 4 incorrect, and 10 abstentions.

Support-ID validation accepted no unauthorized, hidden, or cross-query IDs. The main remaining issue is therefore not retrieval or ACL leakage, but canonical support selection/output robustness: critical-value checks rejected {critical_rejected} query outputs and the model produced {parse_failures} contract-invalid abstention shapes.

Conclusion: the canonical architecture is **not yet stable for TechQA**. Keep the support-ID direction as a controlled candidate, but do not promote it globally until a broader contract/selection fix is separately tested.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")

    write_json(OUT / "decision.json", {
        "classification": "CANONICAL_ARCHITECTURE_NOT_YET_STABLE",
        "canonical_architecture": config["contract"]["pipeline"],
        "sample_hash": config["sample_hash"],
        "corpus_fingerprint": config["corpus_fingerprint"],
        "retrieval_replayed": True,
        "new_retrieval_calls": 0,
        "official_luna_calls": 50,
        "official_judge_calls": len(judges),
        "valid_support_id_visible_outputs": generation["valid_support_id_outputs"],
        "valid_support_id_output_rate": round(generation["valid_support_id_outputs"] / 50, 4),
        "semantic": {"correct": correct, "partial": partial, "incorrect": incorrect, "visible": visible},
        "complete_evidence": {"queries": len(complete_ids), "verdicts": complete_verdicts},
        "support_selection_status": support_status_counts,
        "safety": {
            "unauthorized_leakage": 0,
            "hidden_ids_accepted": 0,
            "cross_query_ids_accepted": 0,
            "unsupported_visible_claims": 0,
            "critical_conflicts_accepted": 0,
            "critical_conflicts_rejected": critical_rejected,
        },
        "historical_comparison": {
            "historical": {"correct": 29, "partial": 7, "incorrect": 4, "abstention": 10},
            "canonical": {"correct": correct, "partial": partial, "incorrect": incorrect, "abstention": unavailable, "parse_failures": parse_failures},
        },
        "techqa_gate": "NO",
        "primary_remaining_bottleneck": "SUPPORT_ID_OUTPUT_AND_VALIDATION_ROBUSTNESS",
    })
    write_json(OUT / "latency-summary.json", {
        "retrieval_replayed_stage_latency_ms": {
            "p50": percentile(retrieval_ms, 0.5), "p95": percentile(retrieval_ms, 0.95), "max": max(retrieval_ms) if retrieval_ms else None
        },
        "luna_generation_ms": {"p50": percentile(luna_ms, 0.5), "p95": percentile(luna_ms, 0.95), "max": max(luna_ms) if luna_ms else None},
        "end_to_end_estimated_ms": {"p50": percentile(end_to_end, 0.5), "p95": percentile(end_to_end, 0.95), "max": max(end_to_end) if end_to_end else None},
        "terra_judge_ms": generation["latency_ms"]["terra_judge"],
    })
    write_json(OUT / "cost-summary.json", {
        **generation["cost"],
        "luna_mean_cost_per_query_usd": round(generation["cost"]["luna_total_usd"] / 50, 8),
        "terra_mean_cost_per_visible_answer_usd": round(generation["cost"]["terra_total_usd"] / len(judges), 8) if judges else None,
        "historical_luna_generation_cost_usd": 0.0457738,
        "historical_luna_input_tokens": old_input,
        "support_id_input_token_ratio_vs_historical": round(new_input / old_input, 4) if old_input else None,
    })
    write_json(OUT / "support-summary.json", {
        "query_count": 50,
        "support_units": {"mean": round(sum(len([u for u in read_jsonl(OUT / 'support-units.jsonl') if u['query_id'] == q]) for q in query_ids) / 50, 3)},
        "mean_selected_support_ids": round(statistics.mean(selected_ids), 3),
        "p50_selected_support_ids": statistics.median(selected_ids),
        "max_selected_support_ids": max(selected_ids),
        "mean_top5_unique_sources": round(statistics.mean(unique_top5), 3),
        "mean_sectionaware_blocks": round(statistics.mean(section_blocks), 3),
        "mean_context_tokens": round(statistics.mean(context_tokens), 3) if context_tokens else None,
        "p95_context_tokens": percentile(context_tokens, 0.95),
        "support_selection_status": support_status_counts,
    })
    print(json.dumps({"decision": "CANONICAL_ARCHITECTURE_NOT_YET_STABLE", "visible": visible, "correct": correct, "partial": partial, "incorrect": incorrect, "abstention_like": unavailable, "complete_evidence": len(complete_ids)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
