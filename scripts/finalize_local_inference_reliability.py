"""Finalize provider-blocked reliability artifacts without provider calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELIABILITY = ROOT / "artifacts/phase-7/local-inference-reliability"
M0 = ROOT / "artifacts/phase-7/measurement-lock-m0"
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    preflight = read_json(RELIABILITY / "provider-preflight.json")
    status = preflight.get("status", "PROVIDER_BLOCKED")
    for probe, name in (("B", "structured"), ("C", "v2-2-real"), ("D", "v2-3-real")):
        path = RELIABILITY / f"probe-{probe.lower()}-{name}.json"
        if not path.exists():
            write_json(path, {"probe": probe, "result": "NOT_RUN", "reason": "Probe A failed"})
    (RELIABILITY / "five-call-reliability.jsonl").write_text("", encoding="utf-8")
    write_json(
        RELIABILITY / "five-call-reliability-summary.json",
        {
            "status": "NOT_RUN_PREFLIGHT_FAILED",
            "required_calls": 5,
            "completed_calls": 0,
            "reason": "Probe A did not complete before the bounded overall timeout",
        },
    )
    (RELIABILITY / "provider-preflight-report.md").write_text(
        "# Local Inference Reliability\n\n"
        f"Status: **{status}**\n\n"
        "Probe A (plain, tiny, no schema) timed out before response headers and "
        "before the first body byte. Therefore B/C/D were not run: the failure is "
        "already isolated to the basic Ollama response path.\n\n"
        "No official M0 call, V2.2 baseline, or V2.3 paired call was started.\n",
        encoding="utf-8",
    )

    m0_summary = read_json(M0 / "m0-summary.json")
    m0_summary["previous_status"] = m0_summary.get("status")
    m0_summary["current_status"] = "M0_PROVIDER_BLOCKED"
    m0_summary["execution_status"] = "PROVIDER_BLOCKED"
    m0_summary["architecture_decision"] = "NOT_EVALUATED"
    m0_summary["provider_preflight"] = "FAIL_PROBE_A_OVERALL_TIMEOUT"
    m0_summary["official_m0_started"] = False
    write_json(M0 / "m0-summary.json", m0_summary)

    stability = read_json(M0 / "stability-audit.json")
    stability["previous_status"] = stability.get("status")
    stability["current_status"] = "PROVIDER_BLOCKED"
    stability["architecture_decision"] = "NOT_EVALUATED"
    stability["preflight_probe_a"] = "TIMEOUT_OVERALL_BEFORE_HEADERS"
    stability["preflight_probes_b_to_d"] = "NOT_RUN_AFTER_A_FAILURE"
    stability["same_seed_runs_completed"] = 0
    stability["cross_seed_runs_completed"] = 0
    write_json(M0 / "stability-audit.json", stability)

    v23_decision = read_json(V23 / "decision.json")
    v23_decision.update(
        {
            "decision": "NOT_EVALUATED",
            "execution_status": "M0_PROVIDER_BLOCKED",
            "adopted": False,
        }
    )
    write_json(V23 / "decision.json", v23_decision)
    v23_summary = read_json(V23 / "summary.json")
    v23_summary.update(
        {
            "execution_status": "M0_PROVIDER_BLOCKED",
            "architecture_decision": "NOT_EVALUATED",
        }
    )
    write_json(V23 / "summary.json", v23_summary)


if __name__ == "__main__":
    main()
