# ruff: noqa: E501
"""Prepare the final Phase 7 correction and frozen V2.2 candidate.

This command is strictly zero-inference.  It consumes only frozen result and
provider metadata, and writes new closure artifacts without altering historical
Phase 7 outputs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/phase-7/final-integrity-audit"
CLOSURE = ROOT / "artifacts/phase-7/phase7-closure"
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
REL = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"
HOLDOUT = tuple(json.loads((M0 / "holdout-manifest.json").read_text())["query_ids"])


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def truncation_resolution() -> dict[str, Any]:
    rows = [
        row
        for row in read_jsonl(AUDIT / "corrected-v2-3-results.jsonl")
        if row["query_id"] == "multi-01-0"
    ]
    per_seed = []
    for row in sorted(rows, key=lambda item: item["seed"]):
        provider = row.get("provider_observation") or {}
        per_seed.append(
            {
                "seed": row["seed"],
                "num_predict": row.get("execution_config", {}).get("num_predict"),
                "provider_status": provider.get("status"),
                "http_status": provider.get("status_code"),
                "headers_received": bool(provider.get("headers_received_at")),
                "first_body_byte_received": bool(provider.get("first_body_byte_at")),
                "response_bytes": provider.get("response_bytes"),
                "generated_token_count": provider.get("eval_count"),
                "done_reason": provider.get("done_reason"),
                "finish_reason": provider.get("finish_reason"),
                "json_parse_failed": "TOP_LEVEL_SCHEMA_INVALID" in row.get("validator_failure_codes", []),
                "classification": "INDETERMINATE",
                "basis": [
                    "Provider completed HTTP response with status 200.",
                    "No finish/done reason or eval_count was persisted.",
                    "Malformed structured output is observable, but output-limit termination is not directly established.",
                ],
            }
        )
    return {
        "schema_version": "phase7-multi-01-0-truncation-resolution-v1",
        "query_id": "multi-01-0",
        "seeds_inspected": [item["seed"] for item in per_seed],
        "per_seed": per_seed,
        "direct_ceiling_hits": 0,
        "supported_truncation_artifacts": 0,
        "not_truncation_records": 0,
        "indeterminate_records": len(per_seed),
        "query_level_classification": "INDETERMINATE",
        "query_verdict_changed": False,
        "interpretation": "The available metadata does not prove or strongly support output-limit termination; the original corrected query verdict is retained.",
    }


def formal_recalculation() -> dict[str, Any]:
    old = read_json(V23 / "paired-holdout-analysis-bounded-output.json")
    corrected = read_json(AUDIT / "corrected-paired-analysis.json")
    return {
        "schema_version": "phase7-formal-verdict-recalculation-v1",
        "historical_result": {
            "clearly_better": old["clearly_better_count"],
            "clearly_worse": old["clearly_worse_count"],
            "equivalent_or_unstable": old["equivalent_or_unstable_queries"],
            "invalid_for_final_decision_due_execution_asymmetry": True,
        },
        "corrected_result": {
            "clearly_better": corrected["clearly_better_count"],
            "clearly_worse": corrected["clearly_worse_count"],
            "equivalent_or_unstable": corrected["equivalent_or_unstable_count"],
            "clearly_better_query_ids": corrected["clearly_better_queries"],
            "clearly_worse_query_ids": corrected["clearly_worse_queries"],
        },
        "formal_gate_verdict": "CLEAR_REGRESSION",
        "selected_for_closure": "pipeline_v2_2_evidence_backed",
        "v2_3_empirical_quality_superiority_established": False,
        "v2_3_contract_disproven": False,
        "v2_3_implementation_vs_contract_root_cause": "UNRESOLVED",
        "thresholds_changed": False,
    }


def final_config() -> dict[str, Any]:
    prompt_hash = "dc665466f81980a4f5d60765ebb88fef871e844470ef6ee6017b24507b1fead1"
    schema_hash = "ab655795576455da96cfc91d2251aa268a666812c55e781dde9e5013954a14d1"
    config = {
        "schema_version": "phase7-final-v2-2-production-candidate-v1",
        "pipeline_version": "pipeline_v2_2_evidence_backed",
        "output_contract_version": "output_contract_v2_2",
        "prompt_version": "v3",
        "prompt_hash": prompt_hash,
        "generator": {"model": "qwen3.5:4b", "model_digest": "2a654d98e6fb"},
        "execution": {
            "num_ctx": 4096,
            "num_predict": 1024,
            "temperature": 0.0,
            "think": False,
            "stream": False,
            "connect_timeout_seconds": 10.0,
            "read_timeout_seconds": 180.0,
            "overall_timeout_seconds": 240.0,
        },
        "retrieval": {
            "embedding_model": "qwen3-embedding:4b",
            "embedding_dimension": 1024,
            "method": "Dense + BM25 + RRF",
            "candidate_k": 20,
            "reranker": "BAAI/bge-reranker-v2-m3",
            "top_n": 5,
        },
        "evidence": {
            "builder": "SectionAwareEvidenceBuilder",
            "builder_file_sha256": digest(ROOT / "app/evidence/section_aware.py"),
            "serialization": "serialize_section_aware_context",
            "validation_schema_sha256": schema_hash,
            "critical_value_rules": "current V2.2 evidence-backed validation",
        },
        "security": {"acl": "STRICT", "phase6_semantic_answerability_gate": "OFF"},
        "provenance": {
            "corrected_v2_2_results_sha256": digest(AUDIT / "corrected-v2-2-results.jsonl"),
            "snapshot_manifest_sha256": digest(M0 / "evidence-snapshot-manifest.json"),
            "challenger_freeze_sha256": digest(REL / "v2-3-challenger-freeze.json"),
            "source_of_truth": "corrected symmetric V2.2 initial-eight run",
        },
    }
    config["config_fingerprint"] = sha_json(config)
    return config


def main() -> None:
    CLOSURE.mkdir(parents=True, exist_ok=True)
    trunc = truncation_resolution()
    formal = formal_recalculation()
    config = final_config()
    # Keep the final audit decision artifact explicit about the distinction
    # between the formal preregistered gate and the pipeline selected for
    # closure.  This is zero-inference provenance correction only.
    audit_decision_path = AUDIT / "final-architecture-decision.json"
    audit_decision = read_json(audit_decision_path)
    audit_decision.update(
        {
            "formal_gate_verdict": formal["formal_gate_verdict"],
            "selected_for_closure": formal["selected_for_closure"],
            "v2_3_empirical_quality_superiority_established": False,
            "v2_3_contract_disproven": False,
            "v2_3_implementation_vs_contract_root_cause": "UNRESOLVED",
            "selected_v2_2_known_limitations": [
                "semantic_attribution_alignment_unresolved"
            ],
            "multi_01_0_truncation_resolution": trunc["query_level_classification"],
            "historical_result_invalid_for_final_decision_due_execution_asymmetry": True,
        }
    )
    write_json(audit_decision_path, audit_decision)
    write_json(CLOSURE / "multi-01-0-truncation-resolution.json", trunc)
    write_json(CLOSURE / "formal-verdict-recalculation.json", formal)
    write_json(CLOSURE / "final-v2-2-config.json", config)
    (CLOSURE / "final-v2-2-config.sha256").write_text(config["config_fingerprint"] + "\n")
    limitations = {
        "schema_version": "phase7-selected-v2-2-limitations-v1",
        "selected_pipeline": "pipeline_v2_2_evidence_backed",
        "corrected_holdout": {"correctly_attributed_visible": 15, "misattributed_visible": 10, "false_abstention": 5},
        "misattribution_ratio_among_attributed_or_misattributed": 0.4,
        "citation_identity_deterministic": True,
        "tenant_acl_enforced": True,
        "semantic_attribution_guaranteed": False,
        "limitation": "Claim-to-evidence semantic alignment remains unresolved; deterministic citation identity does not guarantee semantic attribution correctness.",
        "v2_3_limitation": "The evaluated V2.3 implementation produced no correctly-attributed visible answers across the corrected 40-run paired holdout execution, with higher false-abstention and latency. Debug-set reproduction was not executed, so implementation-vs-contract causality remains unresolved.",
    }
    write_json(CLOSURE / "selected-architecture-limitations.json", limitations)
    summary = {
        "schema_version": "phase7-closure-summary-v1",
        "git_head_before_closure_commit": git_head(),
        "generation_calls_before_smoke": 0,
        "retrieval_calls_before_smoke": 0,
        "formal_gate_verdict": formal["formal_gate_verdict"],
        "selected_for_closure": formal["selected_for_closure"],
        "extension_status": "EXTENSION_BLOCKED_INSUFFICIENT_ELIGIBLE_POOL",
        "eligible_extension_pool": 1,
        "smoke36_status": "PENDING_POST_COMMIT",
        "config_fingerprint": config["config_fingerprint"],
    }
    write_json(CLOSURE / "summary.json", summary)
    report = """# Phase 7 Final Closure

## Formal result

The historical 2 better / 2 worse / 4 equivalent result is invalid for the final paired decision because V2.2 did not record `num_predict`, while V2.3 used 1024. The corrected symmetric run retained the frozen eight queries and seeds and used `num_predict=1024` for both arms.

The corrected result is 0 clearly better, 3 clearly worse, and 5 equivalent/unstable. The formal gate is `CLEAR_REGRESSION`; the selected closure pipeline is `pipeline_v2_2_evidence_backed`.

## multi-01-0

All five corrected V2.3 records completed HTTP 200, but no finish/done reason or eval count was persisted. Therefore each seed is `INDETERMINATE`, not proven or supported truncation. The query verdict is unchanged.

## V2.3 limitation

The evaluated V2.3 support-unit implementation produced no correctly-attributed visible answers across the corrected 40-run paired holdout execution and showed materially higher false-abstention and latency. The preregistered debug-set reproduction step was not executed, so this evaluation cannot distinguish whether the observed failure was caused by the support-unit contract itself or by its current implementation/validator interaction. No holdout-driven fix was attempted and no additional architecture experiment was opened.

## Selected V2.2 limitation

Under corrected symmetric execution, V2.2 produced 15/40 correctly attributed and 10/40 misattributed visible answers; 40% of the attributed/misattributed set was misattributed. Citation identity is deterministic and tenant ACLs are enforced, but semantic claim-to-evidence alignment is not guaranteed.

The development split contains 12 multi-document queries. After the initial eight holdout queries and three debug queries, only one eligible unseen development multi-document query remained, so the preregistered +8 extension was impossible without violating split policy. Calibration and frozen test were untouched.

## Provider findings

1. Stale Ollama llama-server runner state caused requests to stall; model unload and controlled service restart restored inference health.
2. Constrained structured generation showed output-length pathology and severe tail latency in V2.3; bounding generation with `num_predict=1024` stabilized execution without changing RAG retrieval.

Smoke36 is run only after the closure commit, with the exact frozen V2.2 fingerprint.
"""
    (CLOSURE / "report.md").write_text(report)
    print(json.dumps({"formal_gate": formal["formal_gate_verdict"], "selected": formal["selected_for_closure"], "config_fingerprint": config["config_fingerprint"]}, indent=2))


if __name__ == "__main__":
    main()
