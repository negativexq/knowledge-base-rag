"""Compare fixed-obligation support with sufficiency_v1 on the Phase 6 cache."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from app.evaluation.semantic_answerability import (
    FIXED_OBLIGATION_SUPPORT_PROMPT_VERSION,
    QUERY_OBLIGATION_EXTRACTION_PROMPT_VERSION,
    OllamaFixedObligationEvaluator,
)
from app.llm.ollama_client import OllamaClient
from scripts.benchmark_balanced_semantic import COLLECTION_DEFAULT, _cached_chunks, load_cache
from scripts.compare_ambiguity_versions import _action_metrics

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "artifacts/phase-6/semantic-balanced-smoke"
SCOPE_RESULTS = ROOT / "artifacts/phase-6/query-scope-boundary/query-only-results.jsonl"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
OUTPUT_DIR = ROOT / "artifacts/phase-6/fixed-obligation-support"
MODEL = "qwen3.5:4b"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round(fraction * (len(ordered) - 1))]


def _latency(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "p50": median(values) if values else None,
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _expected_action(target: str) -> str:
    return {
        "SHOULD_ANSWER": "ANSWER",
        "SHOULD_CLARIFY": "CLARIFY",
        "SHOULD_ABSTAIN": "ABSTAIN",
        "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL": "ABSTAIN",
    }[target]


def _sufficiency_metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    eligible = [row for row in rows if row.get(field) is not None]
    actual = [
        (
            row[field].get("decision")
            if field == "sufficiency"
            else row.get("support_decision")
        )
        == "SUFFICIENT"
        for row in eligible
    ]
    expected = [row["behavioral_target"] == "SHOULD_ANSWER" for row in eligible]
    true_sufficient = sum(exp and act for exp, act in zip(expected, actual, strict=True))
    false_sufficient = sum(not exp and act for exp, act in zip(expected, actual, strict=True))
    false_insufficient = sum(exp and not act for exp, act in zip(expected, actual, strict=True))
    precision = (
        true_sufficient / (true_sufficient + false_sufficient)
        if true_sufficient + false_sufficient
        else 0.0
    )
    recall = true_sufficient / sum(expected) if sum(expected) else 0.0
    gold_present = [
        row
        for row in eligible
        if row["behavioral_target"] == "SHOULD_ANSWER" and row["all_required_present"]
    ]
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
                    else row.get("support_decision")
                )
                == "SUFFICIENT"
                for row in gold_present
            ),
            "denominator": len(gold_present),
        },
    }


def _comparison_slices(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    keys = sorted({row["category"] for row in rows} | {row["language_pair"] for row in rows})
    result: dict[str, dict[str, Any]] = {}
    for key in keys:
        subset = [
            row for row in rows if row["category"] == key or row["language_pair"] == key
        ]
        eligible = [row for row in subset if row.get(field) is not None]
        actual = [
            (
                row[field].get("decision")
                if field == "sufficiency"
                else row.get("support_decision")
            )
            == "SUFFICIENT"
            for row in eligible
        ]
        expected = [row["behavioral_target"] == "SHOULD_ANSWER" for row in eligible]
        result[key] = {
            "n": len(eligible),
            "true_sufficient": sum(e and a for e, a in zip(expected, actual, strict=True)),
            "false_sufficient": sum(not e and a for e, a in zip(expected, actual, strict=True)),
            "false_insufficient": sum(e and not a for e, a in zip(expected, actual, strict=True)),
            "all_gold_present": sum(
                e and row["all_required_present"]
                for e, row in zip(expected, eligible, strict=True)
            ),
            "all_gold_present_sufficient": sum(
                e and row["all_required_present"] and a
                for e, row, a in zip(expected, eligible, actual, strict=True)
            ),
        }
    return result


def _copy_baseline(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the prior query-scope+sufficiency result as an immutable baseline."""
    result = dict(row)
    result["sufficiency_version"] = "sufficiency_v1"
    result["scope_reused"] = True
    result["candidate_architecture"] = "query_scope_query_only_v1 + sufficiency_v1"
    return result


def _safe_extraction(observation) -> dict[str, Any] | None:
    if observation.extraction is None:
        return None
    return observation.extraction.model_dump(mode="json")


def _safe_support(observation) -> dict[str, Any] | None:
    if observation.evaluation is None:
        return None
    return observation.evaluation.model_dump(mode="json")


async def _evaluate_candidate(
    records: list[dict[str, Any]],
    scope_rows: list[dict[str, Any]],
    client: OllamaClient,
    timeout_seconds: float,
    retries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluator = OllamaFixedObligationEvaluator(client, MODEL, timeout_seconds, retries)
    scope_by_id = {row["query_id"]: row for row in scope_rows}
    result: list[dict[str, Any]] = []
    for record in records:
        scope_row = scope_by_id[record["query_id"]]
        row = {
            key: scope_row[key]
            for key in (
                "query_id",
                "case_family",
                "category",
                "behavioral_target",
                "ground_truth_label",
                "query_language",
                "evidence_language",
                "language_pair",
                "gold_present",
                "all_required_present",
                "deterministic_reason",
            )
        }
        row.update(
            {
                "split": "development",
                "scope_reused": True,
                "query_scope_decision": (scope_row.get("query_scope") or {}).get("decision"),
                "sufficiency_version": FIXED_OBLIGATION_SUPPORT_PROMPT_VERSION,
                "extraction_version": QUERY_OBLIGATION_EXTRACTION_PROMPT_VERSION,
                "extraction": None,
                "support_evaluation": None,
                "support_decision": None,
                "shadow_action": None,
                "failure_attribution": "NONE",
                "extraction_error": None,
                "support_error": None,
                "extraction_latency_ms": None,
                "support_latency_ms": None,
                "candidate_latency_ms": 0.0,
                "extraction_stats": {},
                "support_stats": {},
            }
        )

        if record["category"] == "acl_negative":
            row["shadow_action"] = "ABSTAIN"
            row["failure_attribution"] = "DETERMINISTIC_SAFETY"
            result.append(row)
            print(f"[fixed-obligation] {len(result)}/{len(records)}", flush=True)
            continue
        if row["query_scope_decision"] != "SUFFICIENTLY_SCOPED":
            row["shadow_action"] = "CLARIFY"
            row["failure_attribution"] = "QUERY_SCOPE_FAILURE"
            result.append(row)
            print(f"[fixed-obligation] {len(result)}/{len(records)}", flush=True)
            continue

        extraction = await evaluator.extract(record["query"])
        row["extraction"] = _safe_extraction(extraction)
        row["extraction_error"] = extraction.error_code
        row["extraction_latency_ms"] = extraction.latency_ms
        row["extraction_stats"] = {
            "evaluator_call_count": extraction.evaluator_call_count,
            "first_pass_schema_success": extraction.first_pass_schema_success,
            "retry_count": extraction.retry_count,
            "timeout_count": extraction.timeout_count,
            "parse_error": extraction.parse_error,
            "zero_obligation_count": extraction.zero_obligation_count,
            "over_limit_count": extraction.over_limit_count,
            "duplicate_obligation_count": extraction.duplicate_obligation_count,
        }
        row["candidate_latency_ms"] += extraction.latency_ms
        if extraction.extraction is None:
            row["shadow_action"] = "ABSTAIN"
            row["failure_attribution"] = "OBLIGATION_EXTRACTION_FAILURE"
            result.append(row)
            print(f"[fixed-obligation] {len(result)}/{len(records)}", flush=True)
            continue

        support = await evaluator.verify(
            record["query"], extraction.extraction.obligations, _cached_chunks(record)
        )
        row["support_evaluation"] = _safe_support(support)
        row["support_decision"] = support.decision
        row["shadow_action"] = support.shadow_action
        row["support_error"] = support.error_code
        row["support_latency_ms"] = support.latency_ms
        row["candidate_latency_ms"] += support.latency_ms
        row["support_stats"] = {
            "evaluator_call_count": support.evaluator_call_count,
            "first_pass_schema_success": support.first_pass_schema_success,
            "retry_count": support.retry_count,
            "timeout_count": support.timeout_count,
            "parse_error": support.parse_error,
            "missing_obligation_id_count": support.missing_obligation_id_count,
            "extra_obligation_id_count": support.extra_obligation_id_count,
            "invalid_chunk_id_count": support.invalid_chunk_id_count,
            "invalid_support_status_count": support.invalid_support_status_count,
        }
        if support.parse_error:
            row["failure_attribution"] = "SUPPORT_EVALUATION_FAILURE"
        elif row["behavioral_target"] == "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL":
            row["failure_attribution"] = "RETRIEVAL_FAILURE"
        result.append(row)
        print(f"[fixed-obligation] {len(result)}/{len(records)}", flush=True)

    reliability = {
        "extraction_calls": sum(
            r["extraction_stats"].get("evaluator_call_count", 0) for r in result
        ),
        "extraction_first_pass_schema_success": sum(
            r["extraction_stats"].get("first_pass_schema_success", 0) for r in result
        ),
        "extraction_retries": sum(r["extraction_stats"].get("retry_count", 0) for r in result),
        "extraction_parse_failures": sum(
            r["extraction_stats"].get("parse_error", False) for r in result
        ),
        "extraction_timeouts": sum(
            r["extraction_stats"].get("timeout_count", 0) for r in result
        ),
        "zero_obligation": sum(
            r["extraction_stats"].get("zero_obligation_count", 0) for r in result
        ),
        "over_limit": sum(r["extraction_stats"].get("over_limit_count", 0) for r in result),
        "duplicate_obligations": sum(
            r["extraction_stats"].get("duplicate_obligation_count", 0) for r in result
        ),
        "support_calls": sum(r["support_stats"].get("evaluator_call_count", 0) for r in result),
        "support_first_pass_schema_success": sum(
            r["support_stats"].get("first_pass_schema_success", 0) for r in result
        ),
        "support_retries": sum(r["support_stats"].get("retry_count", 0) for r in result),
        "support_parse_failures": sum(
            r["support_stats"].get("parse_error", False) for r in result
        ),
        "support_timeouts": sum(r["support_stats"].get("timeout_count", 0) for r in result),
        "missing_obligation_ids": sum(
            r["support_stats"].get("missing_obligation_id_count", 0) for r in result
        ),
        "extra_obligation_ids": sum(
            r["support_stats"].get("extra_obligation_id_count", 0) for r in result
        ),
        "invalid_chunk_ids": sum(
            r["support_stats"].get("invalid_chunk_id_count", 0) for r in result
        ),
        "invalid_support_status_combinations": sum(
            r["support_stats"].get("invalid_support_status_count", 0) for r in result
        ),
    }
    return result, reliability


def _transition_rows(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> list[dict]:
    right = {row["query_id"]: row for row in candidate}
    output = []
    for old in baseline:
        new = right[old["query_id"]]
        if (old.get("sufficiency") or {}).get("decision") != "INSUFFICIENT":
            continue
        output.append(
            {
                "query_id": old["query_id"],
                "case_family": old["case_family"],
                "category": old["category"],
                "language_pair": old["language_pair"],
                "baseline_decision": old["sufficiency"]["decision"],
                "extracted_obligations": (new.get("extraction") or {}).get("obligations", []),
                "extraction_error": new.get("extraction_error"),
                "support_results": (new.get("support_evaluation") or {}).get("results", []),
                "candidate_decision": new.get("support_decision"),
                "final_action": new.get("shadow_action"),
            }
        )
    return output


def _multidoc_analysis(
    records: list[dict[str, Any]], baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    record_by_id = {r["query_id"]: r for r in records}
    base_by_id = {r["query_id"]: r for r in baseline}
    candidate_by_id = {r["query_id"]: r for r in candidate}
    output = []
    for query_id in sorted(base_by_id):
        base = base_by_id[query_id]
        record = record_by_id[query_id]
        if base["category"] != "multi_document" or not base["all_required_present"]:
            continue
        new = candidate_by_id[query_id]
        output.append(
            {
                "query_id": query_id,
                "case_family": base["case_family"],
                "scope_decision": base.get("query_scope", {}).get("decision"),
                "expected_required_source_count": len(
                    record.get("required_source_ids") or record.get("expected_source_ids") or []
                ),
                "evidence_chunk_count": len(record.get("authorized_top5") or []),
                "baseline_sufficiency": (base.get("sufficiency") or {}).get("decision"),
                "extraction_status": "ok" if new.get("extraction") else "error",
                "extracted_obligations": (new.get("extraction") or {}).get("obligations", []),
                "support_map": (new.get("support_evaluation") or {}).get("results", []),
                "candidate_sufficiency": new.get("support_decision"),
                "candidate_action": new.get("shadow_action"),
                "failure_attribution": new.get("failure_attribution"),
            }
        )
    return output


def _failure_attribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(row["failure_attribution"] for row in rows))


def _latency_report(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "baseline_sufficiency": _latency(
            [r["sufficiency_latency_ms"] for r in baseline if r.get("sufficiency_latency_ms")]
        ),
        "candidate_extraction": _latency(
            [r["extraction_latency_ms"] for r in candidate if r.get("extraction_latency_ms")]
        ),
        "candidate_support": _latency(
            [r["support_latency_ms"] for r in candidate if r.get("support_latency_ms")]
        ),
        "candidate_combined": _latency(
            [r["candidate_latency_ms"] for r in candidate if r["candidate_latency_ms"]]
        ),
        "baseline_end_to_end": _latency([r["latency_ms"] for r in baseline]),
        "candidate_end_to_end": _latency([r["candidate_latency_ms"] for r in candidate]),
        "baseline_calls": sum(r.get("sufficiency_call_count", 0) for r in baseline),
        "candidate_calls": sum(
            r["extraction_stats"].get("evaluator_call_count", 0)
            + r["support_stats"].get("evaluator_call_count", 0)
            for r in candidate
        ),
    }


def _write_csv(path: Path, comparison: dict[str, Any]) -> None:
    columns = ["metric", "baseline", "candidate", "delta_candidate_minus_baseline"]
    rows = []
    for metric in ("precision", "recall", "f1", "false_sufficient", "false_insufficient"):
        old = comparison["baseline"]["sufficiency"][metric]
        new = comparison["candidate"]["sufficiency"][metric]
        rows.append([metric, old, new, new - old])
    for metric in ("gold_present_answered", "gold_present_count"):
        old = comparison["baseline"]["combined"][metric]
        new = comparison["candidate"]["combined"][metric]
        rows.append([metric, old, new, new - old])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_report(path: Path, comparison: dict[str, Any]) -> None:
    base, cand = comparison["baseline"], comparison["candidate"]
    report = f"""# Phase 6C.6 fixed-obligation support

This experiment reuses the exact 48-record authorized cache and the exact
`query_scope_query_only_v1` decisions. `sufficiency_v1` is the baseline. The
candidate separates query-only obligation extraction from support-only checking
and deterministically aggregates the fixed support statuses. No retrieval,
embedding, reranking, generation, calibration, or frozen-test call was made.

## Metric comparison

| Metric | sufficiency_v1 | fixed-obligation support |
|---|---:|---:|
| Precision | {base['sufficiency']['precision']:.3f} | {cand['sufficiency']['precision']:.3f} |
| Recall | {base['sufficiency']['recall']:.3f} | {cand['sufficiency']['recall']:.3f} |
| F1 | {base['sufficiency']['f1']:.3f} | {cand['sufficiency']['f1']:.3f} |
| False sufficient | {base['sufficiency']['false_sufficient']} | \
{cand['sufficiency']['false_sufficient']} |
| False insufficient | {base['sufficiency']['false_insufficient']} | \
{cand['sufficiency']['false_insufficient']} |
| End-to-end ANSWER | {base['combined']['answer']} | {cand['combined']['answer']} |
| End-to-end false answers | {base['combined']['false_answer']} | \
{cand['combined']['false_answer']} |
| Gold-present coverage | {base['combined']['gold_present_answered']}/\
{base['combined']['gold_present_count']} | {cand['combined']['gold_present_answered']}/\
{cand['combined']['gold_present_count']} |

## Reliability and attribution

The candidate separates `QUERY_SCOPE_FAILURE`, `OBLIGATION_EXTRACTION_FAILURE`,
`SUPPORT_EVALUATION_FAILURE`, `RETRIEVAL_FAILURE`, and deterministic safety.
Detailed counts are in `failure-attribution.json` and
`structured-reliability.json`. Candidate call-level details are split between
`extraction-results.jsonl` and `support-results.jsonl`.

## Multi-document

The complete multi-document cases and their obligation-to-chunk support maps
are in `multidoc-analysis.json`. A support decision is `SUFFICIENT` only when
every fixed obligation is `SUPPORTED`; no model-provided global decision is
trusted.

## Scope and safety

All support inputs are built from the authorized top-five context only. The
extractor receives the query only. ACL-negative records do not reach either
semantic stage. Runtime defaults, user-facing behavior, and `sufficiency_v1`
remain unchanged. This is an experimental Phase 6C.6 artifact.
"""
    path.write_text(report, encoding="utf-8")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    metadata, records = load_cache(Path(args.cache_dir), FINGERPRINTS, args.collection)
    scope_rows = _read_jsonl(Path(args.scope_results))
    expected_ids = [record["query_id"] for record in records]
    if [row["query_id"] for row in scope_rows] != expected_ids:
        raise ValueError("query-scope results do not match the immutable 48-query cache")
    if metadata.get("query_count") != 48:
        raise ValueError("fixed-obligation support requires exactly 48 cached records")
    if any(row.get("scope_input_variant") != "query_scope_query_only_v1" for row in scope_rows):
        raise ValueError("fixed-obligation support requires query-only scope decisions")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    baseline = [_copy_baseline(row) for row in scope_rows]

    client = OllamaClient(base_url=args.ollama_url, timeout=args.timeout_seconds)
    try:
        available = set(await client.list_models())
        if MODEL not in available:
            raise RuntimeError(f"evaluator model is not installed locally: {MODEL}")
        candidate, reliability = await _evaluate_candidate(
            records, scope_rows, client, args.timeout_seconds, args.retries
        )
    finally:
        await client.aclose()

    base_actions = _action_metrics(baseline)
    candidate_actions = _action_metrics(candidate)
    comparison = {
        "metadata": {
            "schema_version": "phase-6c6-fixed-obligation-support-v1",
            "git_sha": _git_sha(),
            "model": MODEL,
            "query_scope_version": "query_scope_query_only_v1",
            "baseline_sufficiency_version": "sufficiency_v1",
            "extraction_version": QUERY_OBLIGATION_EXTRACTION_PROMPT_VERSION,
            "support_version": FIXED_OBLIGATION_SUPPORT_PROMPT_VERSION,
            "corpus_fingerprint": metadata["corpus_fingerprint"],
            "dataset_fingerprint": metadata["dataset_fingerprint"],
            "collection": metadata["collection"],
            "retrieval_config": metadata["retrieval_config"],
            "retrieval_config_fingerprint": metadata["retrieval_config_fingerprint"],
            "query_count": len(records),
            "query_ids": expected_ids,
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "reranker_calls": 0,
            "generation_invoked": False,
            "calibration_run": False,
            "frozen_test_touched": False,
        },
        "baseline": {
            "sufficiency": _sufficiency_metric(baseline, "sufficiency"),
            "combined": base_actions,
            "slices": _comparison_slices(baseline, "sufficiency"),
        },
        "candidate": {
            "sufficiency": _sufficiency_metric(candidate, "support_evaluation"),
            "combined": candidate_actions,
            "slices": _comparison_slices(candidate, "support_evaluation"),
        },
        "transitions": _transition_rows(baseline, candidate),
        "multidoc_analysis": _multidoc_analysis(records, baseline, candidate),
        "failure_attribution": _failure_attribution(candidate),
        "structured_reliability": reliability,
        "latency": _latency_report(baseline, candidate),
    }
    (output / "v1-results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in baseline) + "\n",
        encoding="utf-8",
    )
    (output / "extraction-results.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "query_id": row["query_id"],
                    "case_family": row["case_family"],
                    "category": row["category"],
                    "extraction": row["extraction"],
                    "error": row["extraction_error"],
                    **row["extraction_stats"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for row in candidate
            if row["extraction_stats"]
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "support-results.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "query_id": row["query_id"],
                    "case_family": row["case_family"],
                    "category": row["category"],
                    "support_evaluation": row["support_evaluation"],
                    "decision": row["support_decision"],
                    "action": row["shadow_action"],
                    "error": row["support_error"],
                    **row["support_stats"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for row in candidate
            if row["support_stats"]
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "candidate-results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in candidate) + "\n",
        encoding="utf-8",
    )
    (output / "baseline-candidate-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output / "baseline-candidate-comparison.csv", comparison)
    (output / "obligation-transitions.json").write_text(
        json.dumps(comparison["transitions"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "multidoc-analysis.json").write_text(
        json.dumps(comparison["multidoc_analysis"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "extraction-analysis.json").write_text(
        json.dumps(
            {
                "annotation_available": False,
                "note": (
                    "The canonical dataset has source-level evidence labels, "
                    "not authored obligation-component labels."
                ),
                "extraction_count_distribution": dict(
                    Counter(
                        len((row.get("extraction") or {}).get("obligations", []))
                        for row in candidate
                        if row.get("extraction")
                    )
                ),
                "under_decomposition": None,
                "over_decomposition": None,
                "invented_component": None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "support-analysis.json").write_text(
        json.dumps(
            {
                "deterministic_aggregation": True,
                "supported_requires_valid_chunk_id": True,
                "unsupported_requires_empty_support_ids": True,
                "exact_obligation_id_set_required": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "failure-attribution.json").write_text(
        json.dumps(comparison["failure_attribution"], indent=2) + "\n", encoding="utf-8"
    )
    (output / "slice-results.json").write_text(
        json.dumps(
            {
                "baseline": comparison["baseline"]["slices"],
                "candidate": comparison["candidate"]["slices"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "structured-reliability.json").write_text(
        json.dumps(comparison["structured_reliability"], indent=2) + "\n", encoding="utf-8"
    )
    (output / "latency.json").write_text(
        json.dumps(comparison["latency"], indent=2) + "\n", encoding="utf-8"
    )
    _write_report(output / "report.md", comparison)
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--scope-results", type=Path, default=SCOPE_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
