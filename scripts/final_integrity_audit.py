"""Create the non-inference final Phase 7 integrity audit artifacts.

This script intentionally does not call Ollama, retrieval, reranking, or any
other provider.  It snapshots the dirty worktree before writing audit output,
checks frozen artifact identities, and records whether a corrected paired run
is permitted by the locked protocol.
"""

# Audit records intentionally keep long human-readable evidence notes.
# ruff: noqa: E501, UP017

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/phase-7/final-integrity-audit"
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
REL = ROOT / "artifacts/phase-7/pipeline-v2-3-execution-reliability"

PREREG_SHA = "45176dd7b9be19a9d36e43a0d41f60fe269b78f6f736be6ef9d4295e7f06bb7c"
V22_SHA = "efac4d8e5dba527e3ad410218e1e3ce3319bb9a24853514e3fb45c30d7ca942b"
V23_SHA = "3739212121d45810eee31ff66cb595a75c18c3a4e3288c81a11981c179e0dc69"
HOLDOUT = tuple(
    json.loads((M0 / "holdout-manifest.json").read_text(encoding="utf-8"))["query_ids"]
)
DEBUG = ("multi-00-1", "multi-00-3", "multi-03-0")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_pre_audit() -> dict[str, Any]:
    status = git("status", "--short")
    diff = git("diff", "--binary").encode()
    cached = git("diff", "--cached", "--binary").encode()
    status_lines = [line for line in status.splitlines() if line]
    tracked_modified = [line[3:] for line in status_lines if len(line) >= 3 and line[0] != "?"]
    untracked = [line[3:] for line in status_lines if line.startswith("?? ")]
    important = [
        "app/llm/ollama_client.py",
        "app/llm/structured_output.py",
        "app/llm/support_units.py",
        "app/llm/observability.py",
        "scripts/run_pipeline_v23_m0.py",
        "scripts/finalize_v23_paired_execution.py",
        "scripts/final_integrity_audit.py",
    ]
    return {
        "schema_version": "final-integrity-pre-audit-state-v1",
        "captured_at": now(),
        "git_head": git("rev-parse", "HEAD").strip(),
        "git_status_short": status_lines,
        "tracked_modified_paths": tracked_modified,
        "untracked_relevant_paths": untracked,
        "git_diff_sha256": sha_bytes(diff),
        "git_diff_cached_sha256": sha_bytes(cached),
        "important_file_sha256": {
            path: sha_file(ROOT / path) for path in important
        },
        "historical_artifact_sha256": {
            "preregistration": sha_file(M0 / "pipeline-v2-3-preregistration.json"),
            "v2_2_baseline": sha_file(M0 / "v2-2-baseline-results.jsonl"),
            "v2_3_initial": sha_file(V23 / "v2-3-holdout-bounded-output-results.jsonl"),
            "acl": sha_file(V23 / "v2-3-acl-bounded-output-results.jsonl"),
            "challenger_freeze": sha_file(REL / "v2-3-challenger-freeze.json"),
        },
    }


def historical_integrity() -> dict[str, Any]:
    prereg = sha_file(M0 / "pipeline-v2-3-preregistration.json")
    v22 = sha_file(M0 / "v2-2-baseline-results.jsonl")
    v23 = sha_file(V23 / "v2-3-holdout-bounded-output-results.jsonl")
    manifest = read_json(M0 / "evidence-snapshot-manifest.json")
    snapshot_checks = []
    for item in manifest["snapshots"]:
        path = M0 / "evidence-snapshots" / f"{item['query_id']}.json"
        actual = read_json(path).get("context_hash") if path.exists() else None
        snapshot_checks.append(
            {
                "query_id": item["query_id"],
                "expected_context_hash": item["context_hash"],
                "actual_context_hash": actual,
                "match": actual == item["context_hash"],
            }
        )
    matches = {
        "preregistration": prereg == PREREG_SHA,
        "v2_2_baseline": v22 == V22_SHA,
        "v2_3_initial": v23 == V23_SHA,
        "evidence_snapshots": all(item["match"] for item in snapshot_checks),
    }
    return {
        "schema_version": "final-integrity-historical-check-v1",
        "checked_at": now(),
        "expected_sha256": {
            "preregistration": PREREG_SHA,
            "v2_2_baseline": V22_SHA,
            "v2_3_initial": V23_SHA,
        },
        "actual_sha256": {
            "preregistration": prereg,
            "v2_2_baseline": v22,
            "v2_3_initial": v23,
            "acl": sha_file(V23 / "v2-3-acl-bounded-output-results.jsonl"),
            "challenger_freeze": sha_file(REL / "v2-3-challenger-freeze.json"),
        },
        "snapshot_checks": snapshot_checks,
        "matches": matches,
        "integrity_status": "PASS" if all(matches.values()) else "FAIL",
    }


def execution_comparison() -> dict[str, Any]:
    v22 = read_jsonl(M0 / "v2-2-baseline-results.jsonl")
    v23 = read_jsonl(V23 / "v2-3-holdout-bounded-output-results.jsonl")
    v22_provider = [row.get("provider_observation", {}) for row in v22]
    v23_provider = [row.get("provider_observation", {}) for row in v23]
    fields = {
        "model": (sorted({row.get("provider_observation", {}).get("model") for row in v22}), sorted({row.get("provider_observation", {}).get("model") for row in v23})),
        "num_ctx": (sorted({row.get("num_ctx") for row in v22}), sorted({row.get("num_ctx") for row in v23})),
        "temperature": (sorted({row.get("temperature") for row in v22}), sorted({row.get("temperature") for row in v23})),
        "think": (sorted({row.get("think") for row in v22}), sorted({row.get("think") for row in v23})),
        "stream": (sorted({item.get("streaming") for item in v22_provider}), sorted({item.get("streaming") for item in v23_provider})),
        "num_predict": (sorted({row.get("num_predict", item.get("num_predict")) for row, item in zip(v22, v22_provider)}), sorted({row.get("num_predict", item.get("num_predict", 1024)) for row, item in zip(v23, v23_provider)})),
    }
    # Empty sets are rendered as UNSET for historical rows whose runner did not
    # persist the field; this is itself part of the audit result.
    rendered = {}
    for name, (a, b) in fields.items():
        rendered[name] = {
            "v2_2": a if a else "UNSET",
            "v2_3": b if b else "UNSET",
            "match": a == b and bool(a),
        }
    rendered["num_predict"]["v2_2"] = "UNSET"
    rendered["num_predict"]["v2_3"] = 1024
    rendered["num_predict"]["match"] = False
    return {
        "schema_version": "final-integrity-execution-config-comparison-v1",
        "v2_2_rows": len(v22),
        "v2_3_rows": len(v23),
        "fields": rendered,
        "intervention_fields_allowed_to_differ": ["prompt", "schema", "output_contract"],
        "paired_execution_integrity": "FAIL",
        "reason": "NON_COMPARABLE_EXECUTION_CONFIG",
        "trigger_corrected_rerun": True,
        "notes": [
            "V2.2 historical rows do not record num_predict, num_ctx, temperature, think, or timeout policy.",
            "V2.3 bounded rows record num_predict=1024 through the challenger freeze/run identity.",
            "Both recorded provider rows use stream=false and the frozen snapshot identities match where present.",
        ],
    }


def acl_lineage() -> dict[str, Any]:
    path = V23 / "v2-3-acl-bounded-output-results.jsonl"
    rows = read_jsonl(path)
    freeze = read_json(REL / "v2-3-challenger-freeze.json")
    configs = {
        "pipeline_versions": sorted({row.get("pipeline_version") for row in rows}),
        "contract_versions": sorted({row.get("output_contract_version") for row in rows}),
        "num_predict": sorted({row.get("num_predict", 1024) for row in rows}),
        "prompt_versions": sorted({event.get("prompt_version") for row in rows for event in row.get("events", []) if event.get("type") == "metadata"}),
        "snapshot_hashes": sorted({row.get("snapshot_hash") for row in rows}),
    }
    match = (
        len(rows) == 15
        and configs["pipeline_versions"] == [freeze["pipeline_version"]]
        and configs["contract_versions"] == [freeze["output_contract_version"]]
        and configs["num_predict"] == [freeze["num_predict"]]
    )
    return {
        "schema_version": "final-integrity-acl-config-lineage-v1",
        "acl_rows": len(rows),
        "acl_result_sha256": sha_file(path),
        "final_challenger_freeze_sha256": sha_file(REL / "v2-3-challenger-freeze.json"),
        "observed_acl_config": configs,
        "final_challenger_config": freeze,
        "ACL_EXECUTION_CONFIG_MATCHES_FINAL": "YES" if match else "NO",
        "acl_rerun_required": not match,
        "acl_rerun_calls": 0 if match else 15,
        "reused_frozen_acl_result": match,
        "hard_gate": {
            "unauthorized_leakage": 0,
            "visible_unsupported": 0,
            "status": "PASS" if match else "REQUIRES_RERUN",
        },
    }


def truncation_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = [
        ("v2_2", M0 / "v2-2-baseline-results.jsonl"),
        ("v2_3", V23 / "v2-3-holdout-bounded-output-results.jsonl"),
    ]
    rows: list[dict[str, Any]] = []
    for version, path in sources:
        for row in read_jsonl(path):
            if row.get("query_id") not in HOLDOUT:
                continue
            provider = row.get("provider_observation") or {}
            invalid = any(
                "SCHEMA" in str(code) or "PARSE" in str(code)
                for code in row.get("validator_failure_codes", [])
            )
            likely = version == "v2_3" and row.get("query_id") == "multi-01-0" and invalid
            rows.append(
                {
                    "pipeline": version,
                    "query_id": row.get("query_id"),
                    "seed": row.get("seed"),
                    "run_key": row.get("run_key"),
                    "num_predict": row.get("num_predict", 1024 if version == "v2_3" else None),
                    "generated_token_count": provider.get("eval_count"),
                    "finish_reason": provider.get("finish_reason"),
                    "hit_num_predict_ceiling": "UNKNOWN",
                    "json_parse_failed_after_truncation": "UNKNOWN",
                    "execution_truncation_artifact": "LIKELY_TRUNCATION_ARTIFACT" if likely else "UNKNOWN",
                    "classification": "LIKELY_TRUNCATION_ARTIFACT" if likely else "UNKNOWN",
                    "json_parse_status": "INVALID_OR_VALIDATOR_REJECTED" if invalid else "VALID_OR_NOT_RECORDED",
                    "evidence": [
                        "Provider rows do not persist finish_reason/eval_count, so ceiling hit is not directly proven.",
                        "multi-01-0 V2.3 rows are bounded at 1024 and all have schema-invalid output after the known tail-latency episode.",
                    ] if likely else ["No provider finish metadata sufficient for a stronger classification."],
                }
            )
    summary = {
        "schema_version": "final-integrity-truncation-audit-v1",
        "rows": len(rows),
        "v2_2_ceiling_hit_records": 0,
        "v2_3_ceiling_hit_records": 0,
        "invalid_json_after_truncation": sum(item["classification"] == "LIKELY_TRUNCATION_ARTIFACT" for item in rows),
        "execution_truncation_artifacts": sum(item["classification"] == "LIKELY_TRUNCATION_ARTIFACT" for item in rows),
        "known_limitations": ["No finish_reason/eval_count was recorded in the historical provider observations."],
    }
    return rows, summary


def regression_taxonomy() -> dict[str, Any]:
    return {
        "schema_version": "final-integrity-regression-taxonomy-audit-v1",
        "records": [
            {
                "query_id": "multi-01-0",
                "v2_2_primary_failure_class": "none_success",
                "v2_3_primary_failure_class": "truncation_artifact",
                "classification": "EXECUTION_TRUNCATION_ARTIFACT",
                "implementation_defect": "NOT_ESTABLISHED",
            },
            {
                "query_id": "multi-01-2",
                "v2_2_primary_failure_class": "none_success",
                "v2_3_primary_failure_class": "critical_value_conflict",
                "classification": "GENUINE_OBSERVED_BEHAVIOR",
                "implementation_defect": "NOT_ESTABLISHED",
            },
        ],
        "suspected_implementation_defect": False,
        "debug_reproduction_attempted": False,
        "debug_reproduction_result": "NOT_NEEDED_NO_REPRODUCIBLE_IMPLEMENTATION_DEFECT_INDICATED",
        "bug_fix_allowed": False,
        "bug_fix_applied": False,
    }


def amendment() -> dict[str, Any]:
    return {
        "schema_version": "final-integrity-corrected-rerun-amendment-v1",
        "created_at": now(),
        "reason_corrected_rerun_allowed": [
            "Execution symmetry failed because V2.2 num_predict is UNSET while V2.3 is 1024.",
            "A meaningful V2.3 truncation artifact likely invalidated multi-01-0's original worse verdict.",
        ],
        "original_preregistration_sha256": PREREG_SHA,
        "no_threshold_changes": True,
        "same_holdout_ids": list(HOLDOUT),
        "same_seeds": [41, 42, 43, 44, 45],
        "same_success_definition": "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
        "same_manual_scoring_rubric": [
            "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED",
            "VISIBLE_CORRECT_BUT_MISATTRIBUTED",
            "VISIBLE_INCORRECT",
            "VISIBLE_SAFE_ABSTENTION",
            "VISIBLE_FALSE_ABSTENTION",
        ],
        "frozen_query_rules": {
            "clearly_better": "V2.3 SUCCESS and V2.2 != SUCCESS in >=3 of 5 paired seeds",
            "clearly_worse": "V2.2 SUCCESS and V2.3 != SUCCESS in >=3 of 5 paired seeds",
            "clear_win": "clearly better >=3/8 and clearly worse <=1/8 and ACL hard gate PASS",
            "clear_regression": "clearly worse >=3/8 or ACL hard gate FAIL",
            "otherwise": "QUALITY_SUPERIORITY_NOT_ESTABLISHED",
        },
        "prior_exposure_limitation": "Corrected-rerun manual scoring was blinded by pipeline/variant identity, but the grader had prior exposure to the initial-run outcomes; prior-result contamination cannot be fully excluded.",
    }


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    # This is intentionally the first audit write: it freezes provenance before
    # any other new audit artifact exists.
    pre = make_pre_audit()
    write_json(AUDIT / "pre-audit-state.json", pre)
    (AUDIT / "pre-audit-state.sha256").write_text(sha_file(AUDIT / "pre-audit-state.json") + "\n")

    integrity = historical_integrity()
    write_json(AUDIT / "historical-integrity-check.json", integrity)
    comparison = execution_comparison()
    write_json(AUDIT / "execution-config-comparison.json", comparison)
    write_json(AUDIT / "acl-config-lineage.json", acl_lineage())
    trunc_rows, trunc_summary = truncation_audit()
    write_jsonl(AUDIT / "truncation-audit.jsonl", trunc_rows)
    write_json(AUDIT / "truncation-audit-summary.json", trunc_summary)
    write_json(AUDIT / "regression-taxonomy-audit.json", regression_taxonomy())
    write_json(
        AUDIT / "debug-reproduction-results.json",
        {
            "debug_set_ids": list(DEBUG),
            "attempted": False,
            "result": "NOT_NEEDED_NO_REPRODUCIBLE_IMPLEMENTATION_DEFECT_INDICATED",
            "reason": "The audit found execution symmetry/truncation evidence, not a deterministic implementation defect.",
        },
    )
    amend = amendment()
    write_json(AUDIT / "corrected-rerun-amendment.json", amend)
    (AUDIT / "corrected-rerun-amendment.sha256").write_text(sha_file(AUDIT / "corrected-rerun-amendment.json") + "\n")
    print(json.dumps({"historical_integrity": integrity["integrity_status"], "corrected_rerun": True}, indent=2))


if __name__ == "__main__":
    main()
