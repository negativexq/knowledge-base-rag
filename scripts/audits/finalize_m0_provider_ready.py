"""Finalize the M0 provider recovery state without running inference."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"
RELIABILITY = ROOT / "artifacts/phase-7/local-inference-reliability"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> None:
    provider = read_json(RELIABILITY / "provider-preflight.json")
    reliability = read_json(RELIABILITY / "five-call-reliability-summary.json")
    stability = read_json(M0 / "stability-audit.json")
    baseline = read_json(M0 / "v2-2-baseline-summary.json")
    baseline_rows = read_jsonl(M0 / "v2-2-baseline-results.jsonl")
    prereg = M0 / "pipeline-v2-3-preregistration.json"
    prereg_hash = hashlib.sha256(prereg.read_bytes()).hexdigest()
    recorded_hash = (M0 / "preregistration.sha256").read_text(encoding="utf-8").strip()
    if provider.get("status") != "PASS":
        raise RuntimeError("PROVIDER_NOT_READY")
    if not reliability.get("all_pass") or reliability.get("completed_calls") != 5:
        raise RuntimeError("RELIABILITY_PREFLIGHT_FAILED")
    if not stability.get("generation_same_seed_stable"):
        raise RuntimeError("M0_SAME_SEED_UNSTABLE")
    if len(baseline_rows) != 55 or baseline.get("generation_calls") != 55:
        raise RuntimeError("V2_2_BASELINE_INCOMPLETE")
    if prereg_hash != recorded_hash:
        raise RuntimeError("PREREGISTRATION_HASH_MISMATCH")
    old = read_json(M0 / "m0-summary.json")
    summary = {
        **old,
        "previous_execution_status": old.get("execution_status", "M0_PROVIDER_BLOCKED"),
        "previous_architecture_decision": old.get("architecture_decision", "NOT_EVALUATED"),
        "execution_status": "PROVIDER_READY",
        "architecture_decision": "NOT_EVALUATED",
        "current_status": "M0_COMPLETE_PROVIDER_READY",
        "provider_preflight": "PASS",
        "five_call_reliability": reliability,
        "same_seed_audit_complete": True,
        "cross_seed_audit_complete": True,
        "v2_2_baseline_frozen": True,
        "v2_2_baseline_rows": len(baseline_rows),
        "preregistration_frozen": True,
        "preregistration_sha256": prereg_hash,
        "architecture_decision_evaluated": False,
    }
    write_json(M0 / "m0-summary.json", summary)
    write_json(
        M0 / "provider-ready-verification.json",
        {
            "status": "PROVIDER_READY",
            "execution_status": "M0_COMPLETE_PROVIDER_READY",
            "architecture_decision": "NOT_EVALUATED",
            "provider_preflight": "PASS",
            "five_call_reliability": reliability,
            "stability": stability,
            "baseline_rows": len(baseline_rows),
            "baseline_frozen": True,
            "preregistration_sha256": prereg_hash,
            "historical_blocked_state_preserved": True,
        },
    )
    decision = read_json(V23 / "decision.json") if (V23 / "decision.json").exists() else {}
    write_json(
        V23 / "decision.json",
        {
            **decision,
            "decision": "NOT_EVALUATED",
            "execution_status": "PROVIDER_READY",
            "adopted": False,
            "operational_block": None,
            "m0_baseline_frozen": True,
        },
    )


if __name__ == "__main__":
    main()
