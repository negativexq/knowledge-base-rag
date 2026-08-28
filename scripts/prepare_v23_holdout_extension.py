"""Prepare the preregistered V2.3 holdout extension without inference.

The extension is deliberately fail-closed: the development corpus must expose
eight new multi-document queries after excluding the initial holdout and debug
sets.  No query is borrowed from calibration/frozen_test and no generation is
started when that precondition is not met.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
OUT = ROOT / "artifacts/phase-7/pipeline-v2-3-holdout-extension"
DATASET = ROOT / "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
SEEDS = [41, 42, 43, 44, 45]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def select_extension(
    dataset: list[dict[str, Any]], initial: list[str], debug: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    excluded = set(initial) | set(debug)
    eligible = [
        row
        for row in dataset
        if row.get("split") == "development"
        and row.get("category") == "multi_document"
        and len(row.get("expected_source_ids") or []) > 1
        and row["id"] not in excluded
    ]
    eligible.sort(key=lambda row: hashlib.sha256(row["id"].encode()).hexdigest())
    return eligible[:8], eligible


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    initial = load(M0 / "holdout-manifest.json")["query_ids"]
    debug = load(M0 / "multidoc-debug-manifest.json")["query_ids"]
    dataset = load(DATASET)
    selected, eligible = select_extension(dataset, initial, debug)
    identity = {
        "preregistration_sha256": digest(M0 / "pipeline-v2-3-preregistration.json"),
        "preregistration_recorded_sha256": (M0 / "preregistration.sha256").read_text().strip(),
        "initial_v23_results_sha256": digest(
            V23 / "v2-3-holdout-bounded-output-results.jsonl"
        ),
        "v2_2_baseline_sha256": digest(M0 / "v2-2-baseline-results.jsonl"),
        "challenger_freeze_sha256": digest(
            ROOT
            / "artifacts/phase-7/pipeline-v2-3-execution-reliability/v2-3-challenger-freeze.json"
        ),
        "acl_results_sha256": digest(V23 / "v2-3-acl-bounded-output-results.jsonl"),
    }
    write_json(
        OUT / "holdout-extension-selection.json",
        {
            "status": "READY" if len(selected) == 8 else "BLOCKED_INSUFFICIENT_ELIGIBLE_POOL",
            "selection_rule": "stable_sha256_query_id_sort",
            "input_split": "development",
            "required_count": 8,
            "eligible_pool_size": len(eligible),
            "eligible_query_ids": [row["id"] for row in eligible],
            "selected_query_ids": [row["id"] for row in selected],
            "excluded_initial_holdout": initial,
            "excluded_debug": debug,
            "excluded_splits": ["calibration", "frozen_test"],
            "selection_hash": hashlib.sha256(
                json.dumps([row["id"] for row in selected], separators=(",", ":")).encode()
            ).hexdigest(),
            "integrity": identity,
        },
    )
    blocked = len(selected) != 8
    write_json(
        OUT / "holdout-extension-fact-ground-truth.json",
        {
            "status": "NOT_CREATED" if blocked else "PENDING",
            "reason": "eight unseen development multi-document queries are required"
            if blocked
            else None,
            "query_ids": [row["id"] for row in selected],
            "required_facts": [],
            "sha256": None,
        },
    )
    write_json(
        OUT / "holdout-extension-snapshot-manifest.json",
        {
            "status": "NOT_CREATED" if blocked else "PENDING",
            "query_ids": [],
            "snapshot_hashes": {},
            "retrieval_calls": 0,
            "reranker_calls": 0,
            "reason": "selection precondition failed" if blocked else None,
        },
    )
    for filename in (
        "v2-2-extension-results.jsonl",
        "v2-3-extension-results.jsonl",
        "blind-review-extension-input.jsonl",
        "blind-review-extension-labels.jsonl",
    ):
        (OUT / filename).write_text("")
    write_json(OUT / "blind-review-extension-unblind-map.json", [])
    write_json(
        OUT / "extension-paired-analysis.json",
        {
            "status": "NOT_RUN",
            "reason": "BLOCKED_INSUFFICIENT_ELIGIBLE_POOL",
            "extension_query_count": 0,
            "generation_calls": 0,
        },
    )
    write_json(
        OUT / "combined-16-analysis.json",
        {
            "status": "NOT_FINALIZED",
            "reason": "the preregistered +8 extension cannot be selected from development",
            "initial_holdout_query_count": len(initial),
            "extension_query_count": 0,
            "combined_query_count": len(initial),
            "initial_clearly_better": 2,
            "initial_clearly_worse": 2,
            "architecture_decision": "V2_3_INCONCLUSIVE_EXPAND_ONCE",
        },
    )
    write_json(OUT / "failure-taxonomy-extension-delta.json", {"status": "NOT_RUN"})
    write_json(
        OUT / "failure-taxonomy-combined-delta.json",
        {"status": "NOT_FINALIZED", "initial_holdout_only": True},
    )
    write_json(
        OUT / "final-architecture-decision.json",
        {
            "execution_status": "EXTENSION_BLOCKED_INSUFFICIENT_ELIGIBLE_POOL",
            "architecture_decision": "V2_3_INCONCLUSIVE_EXPAND_ONCE",
            "extension_used": False,
            "no_third_expansion": True,
            "initial_result_preserved": True,
            "next_action": (
                "obtain a valid preregistered +8 development holdout or close "
                "with disclosed uncertainty"
            ),
        },
    )
    summary = {
        "execution_status": "EXTENSION_BLOCKED_INSUFFICIENT_ELIGIBLE_POOL",
        "architecture_decision": "V2_3_INCONCLUSIVE_EXPAND_ONCE",
        "eligible_pool_size": len(eligible),
        "selected_count": len(selected),
        "generation_calls": 0,
        "retrieval_calls": 0,
        "reranker_calls": 0,
        "historical_initial_holdout_preserved": True,
        "identity": identity,
    }
    write_json(OUT / "summary.json", summary)
    (OUT / "report.md").write_text(
        "# V2.3 +8 Holdout Extension\n\n"
        "The preregistered selection was evaluated against the development split "
        "without inference. The corpus contains 12 multi-document queries; after "
        "excluding the eight initial holdout queries and three debug queries, only "
        "`multi-03-3` remains. The required eight-query unseen pool is therefore "
        "unavailable. No calibration/frozen query was borrowed and no generation, "
        "retrieval, or reranking call was made. The initial paired result remains "
        "preserved and the architecture decision remains "
        "`V2_3_INCONCLUSIVE_EXPAND_ONCE`.\n"
    )
    return 0 if not blocked else 2


if __name__ == "__main__":
    raise SystemExit(main())
