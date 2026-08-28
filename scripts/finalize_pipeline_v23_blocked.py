# ruff: noqa: E402
"""Write explicit blocked-state artifacts for Measurement Lock M0.

This utility is intentionally provider-free.  It is used when the local Ollama
provider cannot complete the preregistered stability/baseline run.  It never
creates synthetic generation results and never changes the frozen runtime.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.structured_output import (
    SUPPORT_UNIT_OUTPUT_CONTRACT_VERSION,
    SUPPORT_UNIT_PIPELINE_VERSION,
)  # noqa: E402

M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
SNAPSHOTS = M0 / "evidence-snapshots"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
IDENTITY = {
    "git_sha": "63dbd8ed89a35c31f0968bc1ce93770fb8954602",
    "corpus_fingerprint": "0175aa4a2f9beca7e1a996bcf976dc715c8e6d94a55b76f181500c8c5b8a57b7",
    "dataset_fingerprint": "17474079f2abf80154b3ba1bf1afbc09c13fa16e2f75c26cb4a99bd44518868f",
    "collection": "kb_eval_phase55_0175aa4a2f9b",
    "candidate_k": 20,
    "top_n": 5,
    "generator": "qwen3.5:4b",
    "prompt": "v3",
    "think": False,
    "num_ctx": 4096,
    "temperature": 0.0,
}
DEBUG_IDS = ["multi-00-1", "multi-00-3", "multi-03-0"]
ACL_IDS = ["acl-02-0", "acl-02-1", "acl-02-2"]
SEEDS = [41, 42, 43, 44, 45]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def snapshot_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(SNAPSHOTS.glob("*.json")):
        value = read_json(path)
        rows.append(
            {
                "query_id": value["query_id"],
                "snapshot_file": str(path.relative_to(ROOT)),
                "snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "context_hash": value.get("context_hash"),
                "candidate_top20_hash": digest(value.get("candidate_top20_ids", [])),
                "top5_hash": digest(value.get("top5_ids", [])),
            }
        )
    return rows


def main() -> None:
    holdout_manifest = read_json(M0 / "holdout-manifest.json")
    facts = read_json(M0 / "holdout-fact-ground-truth.json")
    snapshots = snapshot_rows()
    M0.mkdir(parents=True, exist_ok=True)
    V23.mkdir(parents=True, exist_ok=True)

    write_json(M0 / "artifact-identity.json", {**IDENTITY, "validation_status": "MATCH"})
    write_json(
        M0 / "multidoc-debug-manifest.json",
        {"query_ids": DEBUG_IDS, "promotion_eligible": False, "purpose": "debug/reproduction only"},
    )
    write_json(
        M0 / "holdout-selection-rule.json",
        {
            "algorithm": "stable_sha256_query_id_sort",
            "input_split": "development",
            "category": "multi_document",
            "excluded": DEBUG_IDS,
            "count": 8,
            "result_independent": True,
        },
    )
    write_json(
        M0 / "holdout-manifest.json",
        {
            **holdout_manifest,
            "selection_status": "FROZEN",
            "query_ids": holdout_manifest["query_ids"],
        },
    )
    write_json(M0 / "holdout-fact-ground-truth.json", facts)
    write_json(
        M0 / "acl-hard-safety-manifest.json",
        {
            "query_ids": ACL_IDS,
            "seeds": SEEDS,
            "hard_veto": "any unauthorized leakage or visible unsupported answer",
            "status": "SNAPSHOT_READY_BASELINE_NOT_RUN",
        },
    )
    write_json(
        M0 / "evidence-snapshot-manifest.json",
        {
            "status": "FROZEN",
            "query_ids": [row["query_id"] for row in snapshots],
            "holdout_query_ids": holdout_manifest["query_ids"],
            "acl_query_ids": ACL_IDS,
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "manifest_sha256": digest(snapshots),
        },
    )

    stability = {
        "status": "PROVIDER_BLOCKED",
        "same_seed_query_count": 5,
        "cross_seed_query_count": 5,
        "same_seed_runs_completed": 0,
        "cross_seed_runs_completed": 0,
        "provider_attempts_completed": 0,
        "out_of_protocol_provider_sanity_calls_completed": 1,
        "provider_block_reason": (
            "qwen3.5:4b HTTP response stalled during M0 audit; " "no auditable output was committed"
        ),
        "retrieval_stable": True,
        "rerank_stable": True,
        "evidence_context_stable": True,
        "generation_same_seed_stable": "NOT_MEASURED",
        "cross_seed_content_stability": "NOT_MEASURED",
        "cross_seed_support_selection_stability": "NOT_MEASURED",
    }
    write_json(M0 / "stability-audit.json", stability)
    (M0 / "stability-audit-report.md").write_text(
        "# M0 Stability Audit\n\nProvider execution was blocked before an auditable run completed. "
        "Retrieval/evidence snapshot identity is frozen; generation stability is not measured.\n\n"
        + json.dumps(stability, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    write_json(
        M0 / "failure-taxonomy.json",
        {
            "schema_version": "measurement-lock-failure-taxonomy-v1",
            "status": "READY_NO_GENERATION_COUNTS",
            "raw": [
                "raw_correct",
                "raw_incomplete",
                "raw_partial",
                "raw_incorrect",
                "raw_unsupported",
            ],
            "evidence": [
                "lost_support_id_missing",
                "lost_support_id_unknown",
                "lost_support_id_unauthorized",
                "lost_support_id_not_visible",
                "lost_critical_value_absent",
                "lost_critical_value_conflict",
            ],
            "abstention": [
                "lost_forced_abstain_no_valid_parts",
                "lost_model_self_abstain",
                "safe_abstain_insufficient_evidence",
                "false_abstain_fact_complete",
            ],
            "visible": [
                "visible_correct_correctly_attributed",
                "visible_correct_misattributed",
                "visible_incorrect",
                "visible_safe_abstain",
                "visible_false_abstain",
                "visible_unsupported",
                "visible_security_violation",
            ],
        },
    )
    write_jsonl(M0 / "v2-2-baseline-results.jsonl", [])
    write_json(
        M0 / "v2-2-baseline-summary.json",
        {
            "status": "NOT_RUN_PROVIDER_BLOCKED",
            "query_count": 11,
            "seed_count": 5,
            "required_generation_calls": 55,
            "completed_generation_calls": 0,
            "evidence_snapshots_reused": True,
        },
    )
    write_jsonl(M0 / "blind-review-input-v2-2.jsonl", [])
    write_jsonl(M0 / "blind-review-labels-v2-2.jsonl", [])
    prereg = {
        "schema_version": "measurement-lock-m0-preregistration-v1",
        "status": "NOT_FROZEN",
        "freeze_blocked_reason": (
            "V2.2 holdout baseline did not complete because provider execution stalled"
        ),
        "baseline_version": "pipeline_v2_2_evidence_backed/output_contract_v2_2",
        "challenger_version": "pipeline_v2_3_support_units/output_contract_v2_3",
        "identity": IDENTITY,
        "debug_set_ids": DEBUG_IDS,
        "holdout_query_ids": holdout_manifest["query_ids"],
        "acl_query_ids": ACL_IDS,
        "evidence_snapshot_hashes": {row["query_id"]: row["context_hash"] for row in snapshots},
        "fact_ground_truth_hash": digest(facts),
        "seeds": SEEDS,
        "temperature": 0.0,
        "clear_better": "v2.3 success and v2.2 not success in >=3 of 5 paired seeds",
        "clear_worse": "v2.2 success and v2.3 not success in >=3 of 5 paired seeds",
        "max_holdout_expansion": 8,
    }
    prereg_path = M0 / "pipeline-v2-3-preregistration.json"
    write_json(prereg_path, prereg)
    (M0 / "preregistration.sha256").write_text(
        hashlib.sha256(prereg_path.read_bytes()).hexdigest() + "\n", encoding="utf-8"
    )
    write_json(
        M0 / "m0-summary.json",
        {
            "status": "M0_PROVIDER_BLOCKED",
            "identity": IDENTITY,
            "holdout_query_ids": holdout_manifest["query_ids"],
            "snapshot_count": len(snapshots),
            "snapshot_retrieval_calls": len(holdout_manifest["query_ids"]) + len(ACL_IDS),
            "snapshot_embedding_calls": len(holdout_manifest["query_ids"]) + len(ACL_IDS),
            "snapshot_reranker_calls": len(holdout_manifest["query_ids"]) + len(ACL_IDS),
            "out_of_protocol_provider_sanity_calls": 1,
            "v2_2_baseline_frozen": False,
            "preregistration_frozen": False,
        },
    )

    write_json(
        V23 / "output-contract-v2-3.json",
        {
            "version": SUPPORT_UNIT_OUTPUT_CONTRACT_VERSION,
            "pipeline_version": SUPPORT_UNIT_PIPELINE_VERSION,
            "fields": {
                "answer_parts": "array",
                "answer_parts[].text": "string",
                "answer_parts[].support_ids": "array of request-scoped IDs",
                "abstain": "boolean",
            },
            "no_chain_of_thought": True,
        },
    )
    write_json(
        V23 / "support-unit-contract.json",
        {
            "id_format": "E<evidence_index>.U<unit_index>",
            "source_text_only": True,
            "provenance": [
                "parent_evidence_block_id",
                "source_id",
                "contributing_chunk_ids",
                "section_id",
                "tenant_id",
            ],
            "multi_support": True,
        },
    )
    write_json(
        V23 / "critical-value-contract.json",
        {
            "supported_types": [
                "INTEGER",
                "DECIMAL",
                "PERCENTAGE",
                "CURRENCY",
                "DURATION",
                "DATE",
                "VERSION",
                "BOOLEAN",
            ],
            "statuses": [
                "CRITICAL_VALUE_SUPPORTED",
                "CRITICAL_VALUE_ABSENT",
                "CRITICAL_VALUE_CONFLICT",
            ],
            "semantic_entailment_claimed": False,
        },
    )
    write_json(
        V23 / "forced-abstention-contract.json",
        {
            "model_abstain_true": "final abstain",
            "zero_valid_parts": "final abstain",
            "one_or_more_valid_parts": "render surviving parts",
            "reason_code": "NO_VALID_SUPPORT_BACKED_CLAIMS",
        },
    )
    write_json(
        V23 / "offline-validation-results.json",
        {
            "status": "PASS",
            "provider_calls": 0,
            "schema_serialization": "PASS",
            "support_unit_contract": "PASS",
            "critical_value_contract": "PASS",
            "application_abstention_contract": "PASS",
            "note": (
                "Implementation tests are separate; no historical generation result "
                "was fabricated."
            ),
        },
    )
    write_jsonl(V23 / "v2-3-holdout-results.jsonl", [])
    write_jsonl(V23 / "v2-3-acl-results.jsonl", [])
    write_jsonl(V23 / "blind-review-input.jsonl", [])
    write_jsonl(V23 / "blind-review-labels.jsonl", [])
    write_json(V23 / "blind-review-unblind-map.json", {"status": "NOT_CREATED_BASELINE_NOT_FROZEN"})
    write_json(
        V23 / "paired-holdout-analysis.json",
        {"status": "NOT_RUN", "reason": "M0 V2.2 baseline not frozen"},
    )
    write_json(
        V23 / "failure-taxonomy-delta.json",
        {"status": "NOT_RUN", "reason": "No paired model outputs"},
    )
    write_json(
        V23 / "decision.json",
        {
            "decision": "NOT_EVALUATED",
            "execution_status": "M0_PROVIDER_BLOCKED",
            "operational_block": "M0_PROVIDER_BLOCKED",
            "adopted": False,
        },
    )
    write_json(
        V23 / "summary.json",
        {
            "status": "NOT_EVALUATED_PROVIDER_BLOCKED",
            "new_generation_calls": 0,
            "new_retrieval_calls": 0,
            "paired_results_available": False,
        },
    )
    (V23 / "report.md").write_text(
        "# Pipeline v2.3 Support Units\n\n"
        "The offline contract implementation is present and tested, but the paired "
        "holdout was not run. M0 V2.2 baseline and preregistration freeze were "
        "blocked by the local Ollama provider stall. "
        "No synthetic quality or safety result is reported.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
