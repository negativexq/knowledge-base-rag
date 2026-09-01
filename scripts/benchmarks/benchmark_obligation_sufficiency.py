"""Compare obligation-based sufficiency with sufficiency_v1 on the Phase 6C.4 cache."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
from pathlib import Path
from statistics import median
from typing import Any

from app.evaluation.semantic_answerability import (
    OBLIGATION_SUFFICIENCY_PROMPT_VERSION,
    OllamaSemanticEvaluator,
)
from app.llm.ollama_client import OllamaClient
from scripts.benchmarks.benchmark_balanced_semantic import (
    COLLECTION_DEFAULT,
    MODEL,
    _cached_chunks,
    load_cache,
)
from scripts.experiments.compare_ambiguity_versions import _action_metrics

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "artifacts/phase-6/semantic-balanced-smoke"
QUERY_SCOPE_RESULTS = ROOT / "artifacts/phase-6/query-scope-boundary/query-only-results.jsonl"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
OUTPUT_DIR = ROOT / "artifacts/phase-6/obligation-sufficiency"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round(percentile * (len(ordered) - 1))]


def _latency(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "p50": median(values) if values else None,
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _sufficiency_metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    eligible = [row for row in rows if row.get(field) is not None]
    expected = [row["behavioral_target"] == "SHOULD_ANSWER" for row in eligible]
    actual = [
        (
            row[field].get("decision")
            if field == "sufficiency"
            else row.get("normalized_obligation_decision")
        )
        == "SUFFICIENT"
        for row in eligible
    ]
    true_sufficient = sum(exp and act for exp, act in zip(expected, actual, strict=True))
    false_sufficient = sum(not exp and act for exp, act in zip(expected, actual, strict=True))
    false_insufficient = sum(exp and not act for exp, act in zip(expected, actual, strict=True))
    precision = (
        true_sufficient / (true_sufficient + false_sufficient)
        if true_sufficient + false_sufficient
        else 0.0
    )
    recall = true_sufficient / sum(expected) if sum(expected) else 0.0
    return {
        "n": len(eligible),
        "true_sufficient": true_sufficient,
        "false_sufficient": false_sufficient,
        "false_insufficient": false_insufficient,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
        "all_gold_present_sufficiency_recall": {
            "numerator": sum(
                (
                    row[field].get("decision")
                    if field == "sufficiency"
                    else row.get("normalized_obligation_decision")
                )
                == "SUFFICIENT"
                for row in eligible
                if row["behavioral_target"] == "SHOULD_ANSWER" and row["all_required_present"]
            ),
            "denominator": sum(
                row["behavioral_target"] == "SHOULD_ANSWER" and row["all_required_present"]
                for row in eligible
            ),
        },
    }


def _sufficiency_slices(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    keys = sorted({row["category"] for row in rows} | {row["language_pair"] for row in rows})
    result: dict[str, dict[str, Any]] = {}
    for key in keys:
        subset = [row for row in rows if row["category"] == key or row["language_pair"] == key]
        eligible = [row for row in subset if row.get(field) is not None]
        expected = [row["behavioral_target"] == "SHOULD_ANSWER" for row in eligible]
        actual = [
            (
                row[field].get("decision")
                if field == "sufficiency"
                else row.get("normalized_obligation_decision")
            )
            == "SUFFICIENT"
            for row in eligible
        ]
        result[key] = {
            "n": len(eligible),
            "true_sufficient": sum(exp and act for exp, act in zip(expected, actual, strict=True)),
            "false_sufficient": sum(
                not exp and act for exp, act in zip(expected, actual, strict=True)
            ),
            "false_insufficient": sum(
                exp and not act for exp, act in zip(expected, actual, strict=True)
            ),
            "all_gold_present": sum(
                exp and row["all_required_present"]
                for exp, row in zip(expected, eligible, strict=True)
            ),
            "all_gold_present_sufficient": sum(
                exp and row["all_required_present"] and act
                for exp, row, act in zip(expected, eligible, actual, strict=True)
            ),
        }
    return result


def _copy_v1_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["sufficiency_version"] = "sufficiency_v1"
    result["scope_reused"] = True
    result["obligation_sufficiency"] = None
    return result


async def _evaluate_v2(
    records: list[dict[str, Any]],
    scope_rows: list[dict[str, Any]],
    client: OllamaClient,
    timeout_seconds: float,
    retries: int,
) -> list[dict[str, Any]]:
    evaluator = OllamaSemanticEvaluator(client, MODEL, timeout_seconds, retries)
    scope_by_id = {row["query_id"]: row for row in scope_rows}
    result: list[dict[str, Any]] = []
    for record in records:
        scope_row = scope_by_id[record["query_id"]]
        row = dict(scope_row)
        row["sufficiency_version"] = OBLIGATION_SUFFICIENCY_PROMPT_VERSION
        row["scope_reused"] = True
        row["obligation_sufficiency"] = None
        row["normalized_obligation_decision"] = None
        row["contradictory_decision_normalization_count"] = 0
        row["invalid_obligation_count"] = 0
        row["invalid_support_id_count"] = 0
        row["obligation_parse_error"] = False
        row["obligation_error_code"] = None
        row["obligation_latency_ms"] = None
        row["obligation_evaluator_call_count"] = 0
        row["obligation_first_pass_schema_success"] = 0
        row["obligation_retry_count"] = 0
        row["obligation_timeout_count"] = 0

        # ACL rows remain a deterministic offline safety slice and never reach
        # the semantic evaluator.
        if row["category"] == "acl_negative":
            row["shadow_action"] = "ABSTAIN"
            result.append(row)
            continue
        if row.get("query_scope", {}).get("decision") != "SUFFICIENTLY_SCOPED":
            row["shadow_action"] = "CLARIFY"
            result.append(row)
            continue

        observation = await evaluator.evaluate_obligation_sufficiency(
            record["query"], _cached_chunks(record)
        )
        row["obligation_sufficiency"] = (
            observation.evaluation.model_dump(mode="json")
            if observation.evaluation is not None
            else None
        )
        row["normalized_obligation_decision"] = observation.decision
        row["shadow_action"] = observation.shadow_action
        row["obligation_parse_error"] = observation.parse_error
        row["obligation_error_code"] = observation.error_code
        row["obligation_latency_ms"] = observation.latency_ms
        row["obligation_evaluator_call_count"] = observation.evaluator_call_count
        row["obligation_first_pass_schema_success"] = observation.first_pass_schema_success
        row["obligation_retry_count"] = observation.retry_count
        row["obligation_timeout_count"] = observation.timeout_count
        row["invalid_obligation_count"] = observation.invalid_obligation_count
        row["invalid_support_id_count"] = observation.invalid_support_id_count
        row["contradictory_decision_normalization_count"] = (
            observation.contradictory_decision_normalization_count
        )
        row["sufficiency"] = (
            {"decision": observation.decision}
            if observation.decision is not None
            else None
        )
        row["sufficiency_latency_ms"] = observation.latency_ms
        row["latency_ms"] = (row.get("scope_latency_ms") or 0.0) + observation.latency_ms
        row["evaluator_call_count"] = (
            (row.get("scope_call_count") or 0) + observation.evaluator_call_count
        )
        result.append(row)
    return result


def _transitions(v1: list[dict[str, Any]], v2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    right = {row["query_id"]: row for row in v2}
    transitions = []
    for old in v1:
        if (old.get("sufficiency") or {}).get("decision") != "INSUFFICIENT":
            continue
        new = right[old["query_id"]]
        evaluation = new.get("obligation_sufficiency") or {}
        transitions.append(
            {
                "query_id": old["query_id"],
                "case_family": old["case_family"],
                "category": old["category"],
                "language_pair": old["language_pair"],
                "v1_decision": old["sufficiency"]["decision"],
                "v2_obligations": evaluation.get("obligations", []),
                "v2_model_decision": evaluation.get("decision"),
                "v2_normalized_decision": new.get("normalized_obligation_decision"),
                "v2_support_map": [
                    {
                        "obligation_id": obligation.get("id"),
                        "status": obligation.get("status"),
                        "supporting_chunk_ids": obligation.get("supporting_chunk_ids", []),
                    }
                    for obligation in evaluation.get("obligations", [])
                ],
                "v2_final_action": new["shadow_action"],
            }
        )
    return transitions


def _multidoc_analysis(
    records: list[dict[str, Any]], v1: list[dict[str, Any]], v2: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records_by_id = {record["query_id"]: record for record in records}
    v1_by_id = {row["query_id"]: row for row in v1}
    v2_by_id = {row["query_id"]: row for row in v2}
    result = []
    for query_id in sorted(v1_by_id):
        old = v1_by_id[query_id]
        if old["category"] != "multi_document" or not old["all_required_present"]:
            continue
        new = v2_by_id[query_id]
        record = records_by_id[query_id]
        evaluation = new.get("obligation_sufficiency") or {}
        result.append(
            {
                "query_id": query_id,
                "case_family": old["case_family"],
                "expected_answer_components": len(
                    record.get("required_source_ids")
                    or record.get("expected_source_ids")
                    or []
                ),
                "evidence_chunks_available": len(record.get("authorized_top5") or []),
                "query_scope_decision": (old.get("query_scope") or {}).get("decision"),
                "v1_sufficiency": (old.get("sufficiency") or {}).get("decision"),
                "v2_obligations": evaluation.get("obligations", []),
                "v2_normalized_decision": new.get("normalized_obligation_decision"),
                "v2_final_action": new["shadow_action"],
            }
        )
    return result


def _reliability(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "first_pass_schema_success": sum(
            row["obligation_first_pass_schema_success"] for row in rows
        ),
        "evaluator_calls": sum(row["obligation_evaluator_call_count"] for row in rows),
        "retry_count": sum(row["obligation_retry_count"] for row in rows),
        "parse_failures": sum(row["obligation_parse_error"] for row in rows),
        "timeout_count": sum(row["obligation_timeout_count"] for row in rows),
        "invalid_obligation_count": sum(row["invalid_obligation_count"] for row in rows),
        "invalid_support_id_count": sum(row["invalid_support_id_count"] for row in rows),
        "contradictory_decision_normalizations": sum(
            row["contradictory_decision_normalization_count"] for row in rows
        ),
    }


def _latency_report(v1: list[dict[str, Any]], v2: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "v1_sufficiency": _latency(
            [row["sufficiency_latency_ms"] for row in v1 if row.get("sufficiency_latency_ms")]
        ),
        "v2_sufficiency": _latency(
            [row["obligation_latency_ms"] for row in v2 if row.get("obligation_latency_ms")]
        ),
        "v1_end_to_end": _latency([row["latency_ms"] for row in v1]),
        "v2_end_to_end": _latency([row["latency_ms"] for row in v2]),
        "v1_sufficiency_calls": sum(row.get("sufficiency_call_count", 0) for row in v1),
        "v2_sufficiency_calls": sum(row.get("obligation_evaluator_call_count", 0) for row in v2),
        "v1_average_calls_per_query": sum(row.get("evaluator_call_count", 0) for row in v1)
        / len(v1),
        "v2_average_calls_per_query": sum(row.get("evaluator_call_count", 0) for row in v2)
        / len(v2),
    }


def _write_csv(path: Path, comparison: dict[str, Any]) -> None:
    columns = ["metric", "v1", "v2", "delta_v2_minus_v1"]
    rows = []
    for metric in (
        "precision",
        "recall",
        "f1",
        "false_sufficient",
        "false_insufficient",
    ):
        v1 = comparison["v1"]["sufficiency"][metric]
        v2 = comparison["v2"]["sufficiency"][metric]
        rows.append([metric, v1, v2, v2 - v1])
    for metric in ("gold_present_answered", "gold_present_count"):
        v1 = comparison["v1"]["combined"][metric]
        v2 = comparison["v2"]["combined"][metric]
        rows.append([metric, v1, v2, v2 - v1])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_outputs(
    output: Path,
    metadata: dict[str, Any],
    records: list[dict[str, Any]],
    v1: list[dict[str, Any]],
    v2: list[dict[str, Any]],
) -> dict[str, Any]:
    comparison = {
        "metadata": metadata,
        "v1": {
            "sufficiency": _sufficiency_metric(v1, "sufficiency"),
            "combined": _action_metrics(v1),
            "sufficiency_slices": _sufficiency_slices(v1, "sufficiency"),
        },
        "v2": {
            "sufficiency": _sufficiency_metric(v2, "obligation_sufficiency"),
            "combined": _action_metrics(v2),
            "sufficiency_slices": _sufficiency_slices(v2, "obligation_sufficiency"),
        },
        "transitions": _transitions(v1, v2),
        "multidoc_analysis": _multidoc_analysis(records, v1, v2),
        "reliability": _reliability(v2),
        "latency": _latency_report(v1, v2),
        "retrieval_calls": 0,
        "embedding_calls": 0,
        "reranker_calls": 0,
        "generation_invoked": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "v1-results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in v1) + "\n",
        encoding="utf-8",
    )
    (output / "v2-results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in v2) + "\n",
        encoding="utf-8",
    )
    (output / "v1-v2-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output / "v1-v2-comparison.csv", comparison)
    (output / "obligation-transitions.json").write_text(
        json.dumps(comparison["transitions"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "multidoc-analysis.json").write_text(
        json.dumps(comparison["multidoc_analysis"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "slice-results.json").write_text(
        json.dumps(
            {
                "v1": comparison["v1"]["sufficiency_slices"],
                "v2": comparison["v2"]["sufficiency_slices"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "structured-reliability.json").write_text(
        json.dumps(comparison["reliability"], indent=2) + "\n", encoding="utf-8"
    )
    (output / "latency.json").write_text(
        json.dumps(comparison["latency"], indent=2) + "\n", encoding="utf-8"
    )
    v1_suff = comparison["v1"]["sufficiency"]
    v2_suff = comparison["v2"]["sufficiency"]
    v1_coverage = (
        f"{comparison['v1']['combined']['gold_present_answered']}/"
        f"{comparison['v1']['combined']['gold_present_count']}"
    )
    v2_coverage = (
        f"{comparison['v2']['combined']['gold_present_answered']}/"
        f"{comparison['v2']['combined']['gold_present_count']}"
    )
    report = f"""# Phase 6C.5 obligation-based evidence sufficiency

The exact 48-query Phase 6C.4 cache and the existing
`query_scope_query_only_v1` decisions were reused. Retrieval, embeddings,
reranking, and generation were not called. Only the sufficiency evaluator
changed: `sufficiency_v1` versus `{OBLIGATION_SUFFICIENCY_PROMPT_VERSION}`.

| Metric | sufficiency_v1 | obligation v2 |
|---|---:|---:|
| Precision | {v1_suff['precision']:.3f} | {v2_suff['precision']:.3f} |
| Recall | {v1_suff['recall']:.3f} | {v2_suff['recall']:.3f} |
| F1 | {v1_suff['f1']:.3f} | {v2_suff['f1']:.3f} |
| False sufficient | {v1_suff['false_sufficient']} | {v2_suff['false_sufficient']} |
| False insufficient | {v1_suff['false_insufficient']} | {v2_suff['false_insufficient']} |
| End-to-end gold-present coverage | {v1_coverage} | {v2_coverage} |

The final v2 decision is deterministically aggregated from obligation statuses:
all `SUPPORTED` means `SUFFICIENT`; any `UNSUPPORTED` means `INSUFFICIENT`.
The model is not allowed to turn partial evidence into a sufficient result.
Obligation descriptions are limited to the user request and no more than six
obligations. Supporting chunk IDs are validated against the authorized top-k.

Complete multi-document records and all v1 false-insufficient transitions are
listed in the accompanying JSON artifacts. Runtime defaults and enforcement
remain unchanged.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    return comparison


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cache_metadata, records = load_cache(Path(args.cache_dir), FINGERPRINTS, args.collection)
    scope_rows = _read_jsonl(QUERY_SCOPE_RESULTS)
    expected_ids = [row["query_id"] for row in records]
    if [row["query_id"] for row in scope_rows] != expected_ids:
        raise ValueError("query-scope results do not match the balanced cache")
    if args.reuse_v2_results:
        v2_rows = _read_jsonl(args.reuse_v2_results)
        if [row["query_id"] for row in v2_rows] != expected_ids:
            raise ValueError("reused obligation results do not match the balanced cache")
    else:
        client = OllamaClient(base_url=args.ollama_url)
        try:
            available = set(await client.list_models())
            if MODEL not in available:
                raise RuntimeError(f"evaluator model is not installed locally: {MODEL}")
            v2_rows = await _evaluate_v2(
                records, scope_rows, client, args.timeout_seconds, args.retries
            )
        finally:
            await client.aclose()

    fingerprints = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    metadata = {
        "schema_version": "phase-6c5-obligation-sufficiency-v1",
        "git_sha": _git_sha(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": cache_metadata["collection"],
        "query_count": len(records),
        "case_family_count": len({row["case_family"] for row in records}),
        "model": MODEL,
        "query_scope_prompt": "query_scope_query_only_v1",
        "baseline_sufficiency_prompt": "sufficiency_v1",
        "candidate_sufficiency_prompt": OBLIGATION_SUFFICIENCY_PROMPT_VERSION,
        "retrieval_config": cache_metadata["retrieval_config"],
        "retrieval_config_fingerprint": cache_metadata["retrieval_config_fingerprint"],
        "scope_decisions_reused": True,
        "retrieval_rerun": False,
        "calibration_run": False,
        "frozen_test_touched": False,
        "runtime_enforcement": False,
    }
    return _write_outputs(
        Path(args.output_dir),
        metadata,
        records,
        [_copy_v1_row(row) for row in scope_rows],
        v2_rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument(
        "--reuse-v2-results",
        type=Path,
        help="rebuild derived artifacts from a completed v2 JSONL run without LLM calls",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
