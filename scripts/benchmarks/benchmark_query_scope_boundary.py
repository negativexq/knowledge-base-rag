"""Compare query-scope evaluator boundaries on the Phase 6C.2 cache."""

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
    QUERY_SCOPE_COMPACT_PROMPT_VERSION,
    QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION,
    OllamaQueryScopeEvaluator,
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
BASELINE_DIR = ROOT / "artifacts/phase-6/ambiguity-v2"
BASELINE_RESULTS = BASELINE_DIR / "v2-results.jsonl"
BASELINE_COMPARISON = BASELINE_DIR / "v1-v2-comparison.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
OUTPUT_DIR = ROOT / "artifacts/phase-6/query-scope-boundary"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def compact_scope_metadata(record: dict[str, Any]) -> list[dict[str, str]]:
    """Extract only real, safe applicability metadata from cached chunks.

    The current verified cache contains no authority/title/scope fields, so the
    compact arm normally receives an empty list and intentionally behaves like
    query-only. Content, source IDs, chunk IDs, scores, and benchmark labels
    are never included.
    """
    allowed = ("title", "authority_role", "authority_scope")
    values: set[tuple[tuple[str, str], ...]] = set()
    for chunk in record.get("authorized_top5", []):
        item = tuple((key, str(chunk[key])) for key in allowed if chunk.get(key))
        if item:
            values.add(item)
    return [dict(item) for item in sorted(values)]


def _scope_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row.get("query_scope") is not None and not row.get("deterministic_reason")
    ]
    expected = [
        "REQUIRES_USER_INPUT" if row["ground_truth_label"] == "ambiguous" else "SUFFICIENTLY_SCOPED"
        for row in eligible
    ]
    actual = [row["query_scope"]["decision"] for row in eligible]
    tp = sum(
        exp == "REQUIRES_USER_INPUT" and act == "REQUIRES_USER_INPUT"
        for exp, act in zip(expected, actual, strict=True)
    )
    fp = sum(
        exp != "REQUIRES_USER_INPUT" and act == "REQUIRES_USER_INPUT"
        for exp, act in zip(expected, actual, strict=True)
    )
    fn = sum(
        exp == "REQUIRES_USER_INPUT" and act != "REQUIRES_USER_INPUT"
        for exp, act in zip(expected, actual, strict=True)
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(eligible),
        "true_clarify": tp,
        "false_clarify": fp,
        "missed_ambiguity": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _sufficiency_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("sufficiency") is not None]
    expected = [
        "SUFFICIENT" if row["behavioral_target"] == "SHOULD_ANSWER" else "INSUFFICIENT"
        for row in eligible
    ]
    actual = [row["sufficiency"]["decision"] for row in eligible]
    tp = sum(
        exp == "SUFFICIENT" and act == "SUFFICIENT"
        for exp, act in zip(expected, actual, strict=True)
    )
    fp = sum(
        exp != "SUFFICIENT" and act == "SUFFICIENT"
        for exp, act in zip(expected, actual, strict=True)
    )
    fn = sum(
        exp == "SUFFICIENT" and act != "SUFFICIENT"
        for exp, act in zip(expected, actual, strict=True)
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(eligible),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def _latency(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": median(ordered),
        "p95": ordered[round(0.95 * (len(ordered) - 1))],
        "max": max(ordered),
    }


def _latency_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scope": _latency(
            [row["scope_latency_ms"] for row in rows if row.get("scope_latency_ms") is not None]
        ),
        "sufficiency": _latency(
            [
                row["sufficiency_latency_ms"]
                for row in rows
                if row.get("sufficiency_latency_ms") is not None
            ]
        ),
        "total": _latency([row["latency_ms"] for row in rows]),
        "average_evaluator_calls_per_query": sum(row["evaluator_call_count"] for row in rows)
        / len(rows),
        "scope_calls": sum(row.get("scope_call_count", 0) for row in rows),
        "sufficiency_calls": sum(row.get("sufficiency_call_count", 0) for row in rows),
    }


def _action_slices(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    keys = sorted({row["category"] for row in rows} | {row["language_pair"] for row in rows})
    result = {}
    for key in keys:
        subset = [row for row in rows if row["category"] == key or row["language_pair"] == key]
        answerable = [row for row in subset if row["behavioral_target"] == "SHOULD_ANSWER"]
        result[key] = {
            "n": len(subset),
            "answer": sum(row["shadow_action"] == "ANSWER" for row in subset),
            "clarify": sum(row["shadow_action"] == "CLARIFY" for row in subset),
            "abstain": sum(row["shadow_action"] == "ABSTAIN" for row in subset),
            "false_clarify": sum(
                row["behavioral_target"] != "SHOULD_CLARIFY" and row["shadow_action"] == "CLARIFY"
                for row in subset
            ),
            "false_answer": sum(
                row["behavioral_target"] != "SHOULD_ANSWER" and row["shadow_action"] == "ANSWER"
                for row in subset
            ),
            "coverage": (
                sum(row["shadow_action"] == "ANSWER" for row in answerable) / len(answerable)
                if answerable
                else None
            ),
        }
    return result


def _multi_document(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        row for row in rows if row["category"] == "multi_document" and row["all_required_present"]
    ]
    return {
        "complete_n": len(complete),
        "scope_sufficiently_scoped": sum(
            (row.get("query_scope") or {}).get("decision") == "SUFFICIENTLY_SCOPED"
            for row in complete
        ),
        "sufficiency_sufficient": sum(
            (row.get("sufficiency") or {}).get("decision") == "SUFFICIENT" for row in complete
        ),
        "answer": sum(row["shadow_action"] == "ANSWER" for row in complete),
    }


def _scope_result_row(
    record: dict[str, Any],
    scope: Any,
    scope_stats: dict[str, Any],
    sufficiency: Any = None,
    sufficiency_stats: dict[str, Any] | None = None,
    variant: str = "query_only",
) -> dict[str, Any]:
    scope_dict = scope.model_dump(mode="json") if scope is not None else None
    suff_dict = sufficiency.sufficiency.model_dump(mode="json") if sufficiency else None
    scope_decision = scope_dict["decision"] if scope_dict else None
    if scope_decision == "REQUIRES_USER_INPUT":
        action = "CLARIFY"
    elif scope_decision == "SUFFICIENTLY_SCOPED" and suff_dict:
        action = "ANSWER" if suff_dict["decision"] == "SUFFICIENT" else "ABSTAIN"
    else:
        action = "ABSTAIN"
    scope_latency = scope_stats.get("latency_ms") if scope_stats else None
    suff_latency = sufficiency_stats.get("latency_ms") if sufficiency_stats else None
    return {
        "query_id": record["query_id"],
        "case_family": record["case_family"],
        "category": record["category"],
        "behavioral_target": record["behavioral_target"],
        "ground_truth_label": record["ground_truth_label"],
        "query_language": record["query_language"],
        "evidence_language": record["evidence_language"],
        "language_pair": record["language_pair"],
        "gold_present": record["gold_present"],
        "all_required_present": record["all_required_present"],
        "deterministic_reason": record.get("deterministic_reason"),
        "scope_input_variant": variant,
        "scope_metadata_count": len(record.get("_compact_scope", [])),
        "query_scope": scope_dict,
        "sufficiency": suff_dict,
        "shadow_action": action,
        "parse_error": bool(
            (scope_stats or {}).get("parse_error") or (sufficiency_stats or {}).get("parse_error")
        ),
        "scope_latency_ms": scope_latency,
        "sufficiency_latency_ms": suff_latency,
        "latency_ms": (scope_latency or 0.0) + (suff_latency or 0.0),
        "scope_call_count": 1 if scope_stats else 0,
        "sufficiency_call_count": 1 if sufficiency_stats else 0,
        "evaluator_call_count": (1 if scope_stats else 0) + (1 if sufficiency_stats else 0),
        "first_pass_schema_success": (scope_stats or {}).get("first_pass_schema_success", 0)
        + (sufficiency_stats or {}).get("first_pass_schema_success", 0),
        "retry_count": (scope_stats or {}).get("retry_count", 0)
        + (sufficiency_stats or {}).get("retry_count", 0),
        "timeout_count": (scope_stats or {}).get("timeout_count", 0)
        + (sufficiency_stats or {}).get("timeout_count", 0),
        "invalid_enum_count": (scope_stats or {}).get("invalid_enum_count", 0)
        + (sufficiency_stats or {}).get("invalid_enum_count", 0),
        "hallucinated_supporting_chunk_id_count": (
            sufficiency.hallucinated_supporting_chunk_id_count if sufficiency is not None else 0
        ),
    }


async def evaluate_arm(
    records: list[dict[str, Any]],
    client: OllamaClient,
    prompt_version: str,
    timeout_seconds: float,
    retries: int,
) -> list[dict[str, Any]]:
    scope_evaluator = OllamaQueryScopeEvaluator(
        client, MODEL, prompt_version, timeout_seconds, retries
    )
    sufficiency_evaluator = OllamaSemanticEvaluator(client, MODEL, timeout_seconds, retries)
    results = []
    for original in records:
        record = dict(original)
        record["_compact_scope"] = compact_scope_metadata(record)
        if record["category"] == "acl_negative":
            results.append(
                {
                    "query_id": record["query_id"],
                    "case_family": record["case_family"],
                    "category": record["category"],
                    "behavioral_target": record["behavioral_target"],
                    "ground_truth_label": record["ground_truth_label"],
                    "query_language": record["query_language"],
                    "evidence_language": record["evidence_language"],
                    "language_pair": record["language_pair"],
                    "gold_present": record["gold_present"],
                    "all_required_present": record["all_required_present"],
                    "deterministic_reason": "ACL_NEGATIVE_OFFLINE_SAFETY_SLICE",
                    "scope_input_variant": prompt_version,
                    "scope_metadata_count": len(record["_compact_scope"]),
                    "query_scope": None,
                    "sufficiency": None,
                    "shadow_action": "ABSTAIN",
                    "parse_error": False,
                    "scope_latency_ms": None,
                    "sufficiency_latency_ms": None,
                    "latency_ms": 0.0,
                    "scope_call_count": 0,
                    "sufficiency_call_count": 0,
                    "evaluator_call_count": 0,
                    "first_pass_schema_success": 0,
                    "retry_count": 0,
                    "timeout_count": 0,
                    "invalid_enum_count": 0,
                    "hallucinated_supporting_chunk_id_count": 0,
                }
            )
            continue
        compact = (
            record["_compact_scope"]
            if prompt_version == QUERY_SCOPE_COMPACT_PROMPT_VERSION
            else None
        )
        scope, scope_stats = await scope_evaluator.evaluate(record["query"], compact)
        sufficiency = None
        sufficiency_stats = None
        if scope is not None and scope.decision == "SUFFICIENTLY_SCOPED":
            sufficiency = await sufficiency_evaluator.evaluate_sufficiency(
                record["query"], _cached_chunks(record)
            )
            sufficiency_stats = {
                "latency_ms": sufficiency.sufficiency_latency_ms or 0.0,
                "parse_error": sufficiency.parse_error,
                "first_pass_schema_success": sufficiency.first_pass_schema_success,
                "retry_count": sufficiency.retry_count,
                "timeout_count": sufficiency.timeout_count,
                "invalid_enum_count": sufficiency.invalid_enum_count,
            }
        results.append(
            _scope_result_row(
                record,
                scope,
                scope_stats,
                sufficiency,
                sufficiency_stats,
                prompt_version,
            )
        )
    return results


def _comparison_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "scope": _scope_metric(rows),
        "sufficiency": _sufficiency_metric(rows),
        "combined": _action_metrics(rows),
        "latency": _latency_summary(rows),
        "reliability": {
            "first_pass_schema_success": sum(row["first_pass_schema_success"] for row in rows),
            "evaluator_calls": sum(row["evaluator_call_count"] for row in rows),
            "parse_failures": sum(row["parse_error"] for row in rows),
            "retry_count": sum(row["retry_count"] for row in rows),
            "timeout_count": sum(row["timeout_count"] for row in rows),
            "invalid_enum_count": sum(row["invalid_enum_count"] for row in rows),
            "hallucinated_supporting_chunk_id_count": sum(
                row["hallucinated_supporting_chunk_id_count"] for row in rows
            ),
        },
        "slices": _action_slices(rows),
        "multi_document": _multi_document(rows),
    }


def _transitions(
    baseline: list[dict], arm_a: list[dict], arm_b: list[dict]
) -> list[dict[str, Any]]:
    baseline_by_id = {row["query_id"]: row for row in baseline}
    a_by_id = {row["query_id"]: row for row in arm_a}
    b_by_id = {row["query_id"]: row for row in arm_b}
    result = []
    for query_id in sorted(baseline_by_id):
        old = baseline_by_id[query_id]
        if old["behavioral_target"] != "SHOULD_ANSWER" or old["shadow_action"] != "CLARIFY":
            continue
        row = {
            "query_id": query_id,
            "case_family": old["case_family"],
            "category": old["category"],
            "language_pair": old["language_pair"],
            "baseline_action": old["shadow_action"],
        }
        for name, source in (
            ("query_only", a_by_id[query_id]),
            ("compact_scope", b_by_id[query_id]),
        ):
            row[name] = {
                "scope_decision": (source.get("query_scope") or {}).get("decision"),
                "missing_constraints": (source.get("query_scope") or {}).get(
                    "missing_constraints", []
                ),
                "downstream_sufficiency": (source.get("sufficiency") or {}).get("decision"),
                "final_action": source["shadow_action"],
            }
        result.append(row)
    return result


def _input_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    compact_fields = sorted(
        {key for record in records for item in compact_scope_metadata(record) for key in item}
    )
    forbidden = {
        "content",
        "chunk_id",
        "source_id",
        "score",
        "expected_source_ids",
        "required_source_ids",
        "ground_truth_label",
        "category",
        "case_family",
        "gold_present",
        "behavioral_target",
    }
    return {
        "query_only": {
            "retrieved_content_sent": False,
            "retrieval_ids_sent": False,
            "scores_sent": False,
            "ground_truth_fields_sent": False,
        },
        "compact_scope": {
            "retrieved_content_sent": False,
            "retrieval_ids_sent": False,
            "scores_sent": False,
            "ground_truth_fields_sent": False,
            "fields": compact_fields,
            "allowed_fields": ["title", "authority_role", "authority_scope"],
        },
        "forbidden_fields_observed": sorted(forbidden & set(compact_fields)),
        "cache_records": len(records),
        "compact_metadata_available_records": sum(
            bool(compact_scope_metadata(record)) for record in records
        ),
    }


def _write_csv(path: Path, comparison: dict[str, Any]) -> None:
    rows = []
    for metric in ("precision", "recall", "f1"):
        rows.append(
            [
                f"scope_{metric}",
                comparison["baseline"]["ambiguity"][metric],
                comparison["query_only"]["scope"][metric],
                comparison["compact_scope"]["scope"][metric],
            ]
        )
    for name in ("false_clarify", "false_answer", "false_abstain"):
        rows.append(
            [
                name,
                comparison["baseline"]["combined"][name],
                comparison["query_only"]["combined"][name],
                comparison["compact_scope"]["combined"][name],
            ]
        )
    for name in ("gold_present_answered",):
        rows.append(
            [
                name,
                comparison["baseline"]["combined"][name],
                comparison["query_only"]["combined"]["gold_present_answered"],
                comparison["compact_scope"]["combined"]["gold_present_answered"],
            ]
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "baseline_v2", "query_only", "compact_scope"])
        writer.writerows(rows)


def _write_outputs(
    output: Path,
    records: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    arm_a: list[dict[str, Any]],
    arm_b: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    baseline_comparison = json.loads(BASELINE_COMPARISON.read_text(encoding="utf-8"))
    comparison = {
        "metadata": metadata,
        "baseline": {
            "ambiguity": baseline_comparison["v2"]["ambiguity"],
            "combined": baseline_comparison["v2"]["combined"],
            "sufficiency": baseline_comparison["v2"]["sufficiency"],
        },
        "query_only": _comparison_summary(arm_a),
        "compact_scope": _comparison_summary(arm_b),
        "transitions": _transitions(baseline, arm_a, arm_b),
        "input_boundary_audit": _input_audit(records),
    }
    baseline = comparison["baseline"]
    query_only = comparison["query_only"]
    compact_scope = comparison["compact_scope"]
    baseline_coverage = (
        f"{baseline['combined']['gold_present_answered']}/"
        f"{baseline['combined']['gold_present_count']}"
    )
    query_only_coverage = (
        f"{query_only['combined']['gold_present_answered']}/"
        f"{query_only['combined']['gold_present_count']}"
    )
    compact_coverage = (
        f"{compact_scope['combined']['gold_present_answered']}/"
        f"{compact_scope['combined']['gold_present_count']}"
    )
    scope_f1_line = (
        f"| Scope/ambiguity F1 | {baseline['ambiguity']['f1']:.3f} | "
        f"{query_only['scope']['f1']:.3f} | {compact_scope['scope']['f1']:.3f} |"
    )
    false_clarify_line = (
        f"| False clarifies | {baseline['combined']['false_clarify']} | "
        f"{query_only['combined']['false_clarify']} | "
        f"{compact_scope['combined']['false_clarify']} |"
    )
    false_answer_line = (
        f"| False answers | {baseline['combined']['false_answer']} | "
        f"{query_only['combined']['false_answer']} | "
        f"{compact_scope['combined']['false_answer']} |"
    )
    output.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("query-only-results.jsonl", arm_a),
        ("compact-scope-results.jsonl", arm_b),
    ):
        (output / filename).write_text(
            "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
    (output / "query-set.json").write_text(
        json.dumps([row["query_id"] for row in records], indent=2) + "\n", encoding="utf-8"
    )
    (output / "three-way-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output / "three-way-comparison.csv", comparison)
    (output / "transition-analysis.json").write_text(
        json.dumps(comparison["transitions"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "slice-results.json").write_text(
        json.dumps(
            {
                "query_only": comparison["query_only"]["slices"],
                "compact_scope": comparison["compact_scope"]["slices"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "input-boundary-audit.json").write_text(
        json.dumps(comparison["input_boundary_audit"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "latency.json").write_text(
        json.dumps(
            {
                "query_only": comparison["query_only"]["latency"],
                "compact_scope": comparison["compact_scope"]["latency"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = f"""# Phase 6C.4 query-scope boundary comparison

The exact 48-query authorized cache was reused. Baseline is the existing
`ambiguity_v2` run. Arm A sends only the query to
`{QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION}`. Arm B sends the query plus real
runtime-safe compact metadata to `{QUERY_SCOPE_COMPACT_PROMPT_VERSION}`.

No retrieval, embedding, reranker, generation, calibration, or frozen-test
run was performed by the arm evaluator path. Sufficiency remains `sufficiency_v1`.

| Metric | Baseline v2 | Query-only | Compact-scope |
|---|---:|---:|---:|
{scope_f1_line}
{false_clarify_line}
| SHOULD_ANSWER coverage | {baseline_coverage} | {query_only_coverage} | {compact_coverage} |
{false_answer_line}

Genuine ambiguity retention is reported in the JSON artifact. The current
cache contains `{comparison['input_boundary_audit']['compact_metadata_available_records']}`
records with compact authority/title/scope metadata, so Arm B falls back to an
empty compact metadata list when those fields are absent.

This is an offline boundary experiment only. Runtime prompt defaults and
runtime enforcement remain unchanged.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    return comparison


async def run(args: argparse.Namespace) -> dict[str, Any]:
    metadata, records = load_cache(Path(args.cache_dir), FINGERPRINTS, args.collection)
    baseline = _read_jsonl(BASELINE_RESULTS)
    expected_ids = [row["query_id"] for row in records]
    if [row["query_id"] for row in baseline] != expected_ids:
        raise ValueError("ambiguity_v2 baseline does not match balanced cache")
    client = OllamaClient(base_url=args.ollama_url)
    try:
        available = set(await client.list_models())
        if MODEL not in available:
            raise RuntimeError(f"evaluator model is not installed locally: {MODEL}")
        arm_a = await evaluate_arm(
            records,
            client,
            QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION,
            args.timeout_seconds,
            args.retries,
        )
        arm_b = await evaluate_arm(
            records,
            client,
            QUERY_SCOPE_COMPACT_PROMPT_VERSION,
            args.timeout_seconds,
            args.retries,
        )
    finally:
        await client.aclose()
    # Each arm is sequential to avoid concurrent inference on the same local
    # model. Retrieval is never called in this evaluator-only stage.
    if [row["query_id"] for row in arm_a] != expected_ids or [
        row["query_id"] for row in arm_b
    ] != expected_ids:
        raise ValueError("query-scope arm result order mismatch")
    fingerprints = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    run_metadata = {
        "schema_version": "phase-6c4-query-scope-boundary-v1",
        "git_sha": _git_sha(),
        "corpus_fingerprint": fingerprints["corpus_fingerprint"],
        "dataset_fingerprint": fingerprints["dataset_fingerprint"],
        "collection": metadata["collection"],
        "query_count": len(records),
        "query_ids": expected_ids,
        "model": MODEL,
        "baseline_prompt": "ambiguity_v2",
        "query_only_prompt": QUERY_SCOPE_QUERY_ONLY_PROMPT_VERSION,
        "compact_scope_prompt": QUERY_SCOPE_COMPACT_PROMPT_VERSION,
        "sufficiency_prompt": "sufficiency_v1",
        "retrieval_config": metadata["retrieval_config"],
        "retrieval_config_fingerprint": metadata["retrieval_config_fingerprint"],
        "retrieval_rerun": False,
        "retrieval_calls": 0,
        "embedding_calls": 0,
        "reranker_calls": 0,
        "generation_invoked": False,
        "runtime_enforcement": False,
        "calibration_run": False,
        "frozen_test_touched": False,
    }
    return _write_outputs(Path(args.output_dir), records, baseline, arm_a, arm_b, run_metadata)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
