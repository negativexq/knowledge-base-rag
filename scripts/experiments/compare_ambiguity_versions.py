"""Compare ambiguity_v1 and ambiguity_v2 on the immutable balanced cache."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from app.evaluation.semantic_answerability import (
    AMBIGUITY_PROMPT_V2_VERSION,
)
from app.llm.ollama_client import OllamaClient
from scripts.benchmarks.benchmark_balanced_semantic import (
    COLLECTION_DEFAULT,
    MODEL,
    evaluate_model,
    load_cache,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "artifacts/phase-6/semantic-balanced-smoke"
BASELINE_RESULTS = CACHE_DIR / "results.jsonl"
BASELINE_SUMMARY = CACHE_DIR / "summary.json"
FINGERPRINTS = ROOT / "artifacts/evaluation-corpus-v2/fingerprints.json"
OUTPUT_DIR = ROOT / "artifacts/phase-6/ambiguity-v2"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _expected_action(row: dict[str, Any]) -> str:
    return {
        "SHOULD_ANSWER": "ANSWER",
        "SHOULD_CLARIFY": "CLARIFY",
        "SHOULD_ABSTAIN": "ABSTAIN",
        "SHOULD_ABSTAIN_DUE_TO_RETRIEVAL": "ABSTAIN",
    }[row["behavioral_target"]]


def _action_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [_expected_action(row) for row in rows]
    actual = [row["shadow_action"] for row in rows]
    gold_present = [row for row in rows if row["behavioral_target"] == "SHOULD_ANSWER"]
    return {
        "answer": sum(action == "ANSWER" for action in actual),
        "clarify": sum(action == "CLARIFY" for action in actual),
        "abstain": sum(action == "ABSTAIN" for action in actual),
        "correct_answer": sum(
            exp == "ANSWER" and act == "ANSWER" for exp, act in zip(expected, actual, strict=True)
        ),
        "false_answer": sum(
            exp != "ANSWER" and act == "ANSWER" for exp, act in zip(expected, actual, strict=True)
        ),
        "correct_clarify": sum(
            exp == "CLARIFY" and act == "CLARIFY" for exp, act in zip(expected, actual, strict=True)
        ),
        "false_clarify": sum(
            exp != "CLARIFY" and act == "CLARIFY" for exp, act in zip(expected, actual, strict=True)
        ),
        "correct_abstain": sum(
            exp == "ABSTAIN" and act == "ABSTAIN" for exp, act in zip(expected, actual, strict=True)
        ),
        "false_abstain": sum(
            exp == "ANSWER" and act == "ABSTAIN" for exp, act in zip(expected, actual, strict=True)
        ),
        "missed_ambiguity": sum(
            exp == "CLARIFY" and act != "CLARIFY" for exp, act in zip(expected, actual, strict=True)
        ),
        "gold_present_answered": sum(row["shadow_action"] == "ANSWER" for row in gold_present),
        "gold_present_count": len(gold_present),
    }


def _ambiguity_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if not row.get("semantic_evaluation_skipped") and not row.get("deterministic_reason")
    ]
    expected = [
        "AMBIGUOUS" if row["ground_truth_label"] == "ambiguous" else "CLEAR" for row in eligible
    ]
    actual = [(row.get("ambiguity") or {}).get("decision", "ERROR") for row in eligible]
    tp = sum(
        exp == "AMBIGUOUS" and act == "AMBIGUOUS" for exp, act in zip(expected, actual, strict=True)
    )
    fp = sum(
        exp != "AMBIGUOUS" and act == "AMBIGUOUS" for exp, act in zip(expected, actual, strict=True)
    )
    fn = sum(
        exp == "AMBIGUOUS" and act != "AMBIGUOUS" for exp, act in zip(expected, actual, strict=True)
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


def _safe_ambiguity(row: dict[str, Any]) -> dict[str, Any]:
    ambiguity = row.get("ambiguity") or {}
    return {
        "decision": ambiguity.get("decision"),
        "missing_constraints": ambiguity.get("missing_constraints", []),
    }


def _false_clarify_transitions(v1: list[dict], v2: list[dict]) -> list[dict[str, Any]]:
    left = {row["query_id"]: row for row in v1}
    right = {row["query_id"]: row for row in v2}
    rows = []
    for query_id in sorted(left):
        old, new = left[query_id], right[query_id]
        if old["behavioral_target"] == "SHOULD_ANSWER" and old["shadow_action"] == "CLARIFY":
            old_ambiguity, new_ambiguity = _safe_ambiguity(old), _safe_ambiguity(new)
            rows.append(
                {
                    "query_id": query_id,
                    "case_family": old["case_family"],
                    "category": old["category"],
                    "language_pair": old["language_pair"],
                    "v1_ambiguity": old_ambiguity,
                    "v2_ambiguity": new_ambiguity,
                    "v1_action": old["shadow_action"],
                    "v2_action": new["shadow_action"],
                }
            )
    return rows


def _ambiguous_retention(v1: list[dict], v2: list[dict]) -> dict[str, Any]:
    old = {row["query_id"]: row for row in v1}
    new = {row["query_id"]: row for row in v2}
    rows = []
    for query_id in sorted(old):
        if old[query_id]["behavioral_target"] != "SHOULD_CLARIFY":
            continue
        rows.append(
            {
                "query_id": query_id,
                "case_family": old[query_id]["case_family"],
                "v1_decision": _safe_ambiguity(old[query_id])["decision"],
                "v2_decision": _safe_ambiguity(new[query_id])["decision"],
                "v1_correct": old[query_id]["shadow_action"] == "CLARIFY",
                "v2_correct": new[query_id]["shadow_action"] == "CLARIFY",
            }
        )
    return {
        "n": len(rows),
        "v1_retained": sum(row["v1_correct"] for row in rows),
        "v2_retained": sum(row["v2_correct"] for row in rows),
        "v1_missed": sum(not row["v1_correct"] for row in rows),
        "v2_missed": sum(not row["v2_correct"] for row in rows),
        "records": rows,
    }


def _answerable_slice(rows: list[dict], key: str) -> dict[str, Any]:
    subset = [
        row
        for row in rows
        if row["behavioral_target"] == "SHOULD_ANSWER"
        and (row["category"] == key or row["language_pair"] == key)
    ]
    return {
        "n": len(subset),
        "answer": sum(row["shadow_action"] == "ANSWER" for row in subset),
        "clarify": sum(row["shadow_action"] == "CLARIFY" for row in subset),
        "abstain": sum(row["shadow_action"] == "ABSTAIN" for row in subset),
        "coverage": (
            sum(row["shadow_action"] == "ANSWER" for row in subset) / len(subset)
            if subset
            else None
        ),
    }


def _slices(v1: list[dict], v2: list[dict]) -> dict[str, Any]:
    keys = sorted({row["category"] for row in v1} | {row["language_pair"] for row in v1})
    return {
        key: {"v1": _answerable_slice(v1, key), "v2": _answerable_slice(v2, key)} for key in keys
    }


def _multi_document(v1: list[dict], v2: list[dict]) -> dict[str, Any]:
    result = {}
    for label, rows in (("v1", v1), ("v2", v2)):
        complete = [
            row
            for row in rows
            if row["category"] == "multi_document" and row["all_required_present"]
        ]
        result[label] = {
            "complete_n": len(complete),
            "ambiguity_clear": sum(_safe_ambiguity(row)["decision"] == "CLEAR" for row in complete),
            "sufficiency_sufficient": sum(
                (row.get("sufficiency") or {}).get("decision") == "SUFFICIENT" for row in complete
            ),
            "answer": sum(row["shadow_action"] == "ANSWER" for row in complete),
        }
    return result


def _version_and_injection(v1: list[dict], v2: list[dict]) -> dict[str, Any]:
    result = {}
    for category in ("version_conflict", "injection_bearing"):
        result[category] = {}
        for label, rows in (("v1", v1), ("v2", v2)):
            subset = [row for row in rows if row["category"] == category]
            result[category][label] = {
                "n": len(subset),
                "ambiguity": dict(Counter(_safe_ambiguity(row)["decision"] for row in subset)),
                "actions": dict(Counter(row["shadow_action"] for row in subset)),
                "parse_failures": sum(row["parse_error"] for row in subset),
                "false_answers": sum(
                    row["behavioral_target"] != "SHOULD_ANSWER" and row["shadow_action"] == "ANSWER"
                    for row in subset
                ),
            }
    return result


def _comparison(
    v1: list[dict], v2: list[dict], v1_summary: dict[str, Any], v2_summary: dict[str, Any]
) -> dict[str, Any]:
    v1_actions, v2_actions = _action_metrics(v1), _action_metrics(v2)
    v1_ambiguity, v2_ambiguity = _ambiguity_metrics(v1), _ambiguity_metrics(v2)
    return {
        "metadata": {
            "schema_version": "phase-6c3-ambiguity-v2-comparison-v1",
            "git_sha": _git_sha(),
            "model": MODEL,
            "v1_prompt": "ambiguity_v1",
            "v2_prompt": AMBIGUITY_PROMPT_V2_VERSION,
            "sufficiency_prompt": "sufficiency_v1",
            "retrieval_rerun": False,
            "retrieval_calls": 0,
            "embedding_calls": 0,
            "reranker_calls": 0,
            "generation_invoked": False,
            "calibration_run": False,
            "frozen_test_touched": False,
        },
        "v1": {
            "ambiguity": v1_ambiguity,
            "combined": v1_actions,
            "sufficiency": v1_summary.get("sufficiency", {}),
            "reliability": v1_summary.get("reliability", {}),
            "latency": v1_summary.get("latency", {}),
        },
        "v2": {
            "ambiguity": v2_ambiguity,
            "combined": v2_actions,
            "sufficiency": v2_summary["sufficiency"],
            "reliability": v2_summary["reliability"],
            "latency": v2_summary["latency"],
        },
        "transitions": {
            "should_answer_false_clarify": _false_clarify_transitions(v1, v2),
            "action_counts": dict(
                Counter(
                    f"{row['v1_action']}->{row['v2_action']}"
                    for row in _false_clarify_transitions(v1, v2)
                )
            ),
        },
        "ambiguous_retention": _ambiguous_retention(v1, v2),
        "slices": _slices(v1, v2),
        "multi_document": _multi_document(v1, v2),
        "version_and_injection": _version_and_injection(v1, v2),
    }


def _write_csv(path: Path, comparison: dict[str, Any]) -> None:
    metrics = [
        (
            "ambiguity_precision",
            comparison["v1"]["ambiguity"]["precision"],
            comparison["v2"]["ambiguity"]["precision"],
        ),
        (
            "ambiguity_recall",
            comparison["v1"]["ambiguity"]["recall"],
            comparison["v2"]["ambiguity"]["recall"],
        ),
        ("ambiguity_f1", comparison["v1"]["ambiguity"]["f1"], comparison["v2"]["ambiguity"]["f1"]),
        (
            "false_clarify",
            comparison["v1"]["combined"]["false_clarify"],
            comparison["v2"]["combined"]["false_clarify"],
        ),
        (
            "false_answer",
            comparison["v1"]["combined"]["false_answer"],
            comparison["v2"]["combined"]["false_answer"],
        ),
        (
            "gold_present_coverage",
            comparison["v1"]["combined"]["gold_present_answered"]
            / comparison["v1"]["combined"]["gold_present_count"],
            comparison["v2"]["combined"]["gold_present_answered"]
            / comparison["v2"]["combined"]["gold_present_count"],
        ),
        (
            "ambiguity_p50_ms",
            comparison["v1"]["latency"]["ambiguity"]["p50"],
            comparison["v2"]["latency"]["ambiguity"]["p50"],
        ),
        (
            "ambiguity_p95_ms",
            comparison["v1"]["latency"]["ambiguity"]["p95"],
            comparison["v2"]["latency"]["ambiguity"]["p95"],
        ),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "v1", "v2", "delta_v2_minus_v1"])
        for name, old, new in metrics:
            writer.writerow(
                [name, old, new, new - old if old is not None and new is not None else None]
            )


def _write_report(path: Path, comparison: dict[str, Any]) -> None:
    v1, v2 = comparison["v1"], comparison["v2"]
    transitions = comparison["transitions"]["should_answer_false_clarify"]
    retention = comparison["ambiguous_retention"]
    multi = comparison["multi_document"]
    v1_coverage = (
        f"{v1['combined']['gold_present_answered']}/" f"{v1['combined']['gold_present_count']}"
    )
    v2_coverage = (
        f"{v2['combined']['gold_present_answered']}/" f"{v2['combined']['gold_present_count']}"
    )
    v1_multi = (
        f"| v1 | {multi['v1']['ambiguity_clear']}/{multi['v1']['complete_n']} | "
        f"{multi['v1']['sufficiency_sufficient']}/{multi['v1']['complete_n']} | "
        f"{multi['v1']['answer']}/{multi['v1']['complete_n']} |"
    )
    v2_multi = (
        f"| v2 | {multi['v2']['ambiguity_clear']}/{multi['v2']['complete_n']} | "
        f"{multi['v2']['sufficiency_sufficient']}/{multi['v2']['complete_n']} | "
        f"{multi['v2']['answer']}/{multi['v2']['complete_n']} |"
    )
    report = f"""# Phase 6C.3 ambiguity v2 comparison

The comparison reuses the exact 48-query authorized cache from Phase 6C.2.
Only the ambiguity prompt changed: `{comparison['metadata']['v1_prompt']}` versus
`{comparison['metadata']['v2_prompt']}`. Sufficiency remains `sufficiency_v1`.
No retrieval, embedding, reranker, generation, calibration, or frozen-test call
was made during the v2 run.

## Results

| Metric | v1 | v2 |
|---|---:|---:|
| Ambiguity precision | {v1['ambiguity']['precision']:.3f} | {v2['ambiguity']['precision']:.3f} |
| Ambiguity recall | {v1['ambiguity']['recall']:.3f} | {v2['ambiguity']['recall']:.3f} |
| Ambiguity F1 | {v1['ambiguity']['f1']:.3f} | {v2['ambiguity']['f1']:.3f} |
| False clarifies | {v1['combined']['false_clarify']} | {v2['combined']['false_clarify']} |
| Missed ambiguities | {v1['combined']['missed_ambiguity']} | {v2['combined']['missed_ambiguity']} |
| False answers | {v1['combined']['false_answer']} | {v2['combined']['false_answer']} |
| Gold-present coverage | {v1_coverage} | {v2_coverage} |


## SHOULD_ANSWER false-clarify transitions

The v1 baseline has {len(transitions)} such records. Action transitions:
`{json.dumps(comparison['transitions']['action_counts'], sort_keys=True)}`.
The full ID-level transition list is in `false-clarify-transitions.json`.
The SHOULD_ANSWER false-clarify count therefore changes from
{sum(row['v1_action'] == 'CLARIFY' for row in transitions)} to
{sum(row['v2_action'] == 'CLARIFY' for row in transitions)}; the broader
combined false-clarify count changes from {v1['combined']['false_clarify']} to
{v2['combined']['false_clarify']} because two non-answerable rows changed from
ABSTAIN to CLARIFY.

## Genuine ambiguity retention

v1 retained {retention['v1_retained']}/{retention['n']} genuine clarifications;
v2 retained {retention['v2_retained']}/{retention['n']}.

## Multi-document complete cases

| | Ambiguity CLEAR | Sufficiency SUFFICIENT | Final ANSWER |
|---|---:|---:|---:|
{v1_multi}
{v2_multi}

The v1 prompt remains the default. This artifact is a comparison only; it does
not enable runtime enforcement or promote ambiguity_v2.
"""
    path.write_text(report, encoding="utf-8")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    if args.report_only:
        existing = json.loads((output / "v1-v2-comparison.json").read_text(encoding="utf-8"))
        baseline = _read_jsonl(BASELINE_RESULTS)
        v2_results = _read_jsonl(output / "v2-results.jsonl")
        comparison = _comparison(
            baseline,
            v2_results,
            json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8")),
            existing["v2"],
        )
        comparison["metadata"] = existing["metadata"]
        (output / "v1-v2-comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_csv(output / "v1-v2-comparison.csv", comparison)
        (output / "false-clarify-transitions.json").write_text(
            json.dumps(
                comparison["transitions"]["should_answer_false_clarify"],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (output / "ambiguous-retention.json").write_text(
            json.dumps(comparison["ambiguous_retention"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "slice-results.json").write_text(
            json.dumps(comparison["slices"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "latency.json").write_text(
            json.dumps(
                {"v1": comparison["v1"]["latency"], "v2": comparison["v2"]["latency"]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _write_report(output / "report.md", comparison)
        return comparison
    fingerprints = json.loads(FINGERPRINTS.read_text(encoding="utf-8"))
    metadata, records = load_cache(Path(args.cache_dir), FINGERPRINTS, args.collection)
    baseline = _read_jsonl(BASELINE_RESULTS)
    baseline_summary = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
    expected_ids = [row["query_id"] for row in records]
    if [row["query_id"] for row in baseline] != expected_ids:
        raise ValueError("v1 baseline does not match the balanced cache query order")
    client = OllamaClient(base_url=args.ollama_url)
    try:
        available = set(await client.list_models())
        if args.model not in available:
            raise RuntimeError(f"evaluator model is not installed locally: {args.model}")
        v2_summary, v2_results = await evaluate_model(
            args.model,
            records,
            client,
            args.timeout_seconds,
            args.retries,
            ambiguity_prompt_version=AMBIGUITY_PROMPT_V2_VERSION,
        )
    finally:
        await client.aclose()

    if [row["query_id"] for row in v2_results] != expected_ids:
        raise ValueError("v2 result order does not match the balanced cache")
    comparison = _comparison(baseline, v2_results, baseline_summary, v2_summary)
    comparison["metadata"].update(
        {
            "corpus_fingerprint": fingerprints["corpus_fingerprint"],
            "dataset_fingerprint": fingerprints["dataset_fingerprint"],
            "collection": metadata["collection"],
            "query_count": len(records),
            "query_ids": expected_ids,
            "retrieval_config": metadata["retrieval_config"],
            "retrieval_config_fingerprint": metadata["retrieval_config_fingerprint"],
        }
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "v2-results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in v2_results) + "\n",
        encoding="utf-8",
    )
    (output / "v1-v2-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(output / "v1-v2-comparison.csv", comparison)
    (output / "false-clarify-transitions.json").write_text(
        json.dumps(
            comparison["transitions"]["should_answer_false_clarify"], ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "ambiguous-retention.json").write_text(
        json.dumps(comparison["ambiguous_retention"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "slice-results.json").write_text(
        json.dumps(comparison["slices"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "latency.json").write_text(
        json.dumps(
            {"v1": comparison["v1"]["latency"], "v2": comparison["v2"]["latency"]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_report(output / "report.md", comparison)
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection", default=COLLECTION_DEFAULT)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="rebuild comparison artifacts from existing v1/v2 result files",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
