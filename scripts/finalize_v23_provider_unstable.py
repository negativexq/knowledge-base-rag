"""Close the V2.3 attempt as an execution issue, not a quality decision."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V23 = ROOT / "artifacts/phase-7/pipeline-v2-3-support-units"


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
    holdout = read_jsonl(V23 / "v2-3-holdout-results.jsonl")
    acl_path = V23 / "v2-3-acl-results.jsonl"
    acl = read_jsonl(acl_path) if acl_path.exists() else []
    rows = holdout + acl
    failures = [row for row in rows if row.get("result") != "PASS"]
    status = {
        "execution_status": "PROVIDER_UNSTABLE",
        "architecture_decision": "NOT_EVALUATED",
        "required_paired_calls": 55,
        "completed_rows": len(rows),
        "successful_rows": len(rows) - len(failures),
        "provider_failures": len(failures),
        "holdout_rows": len(holdout),
        "acl_rows": len(acl),
        "quality_comparison_valid": False,
        "reason": (
            "V2.3 support-unit calls timed out/failed before a complete paired "
            "holdout was available"
        ),
        "failures": [
            {
                "query_id": row.get("query_id"),
                "seed": row.get("seed"),
                "result": row.get("result"),
                "error": row.get("error"),
            }
            for row in failures
        ],
    }
    write_json(V23 / "paired-execution-status.json", status)
    existing = read_json(V23 / "decision.json") if (V23 / "decision.json").exists() else {}
    write_json(
        V23 / "decision.json",
        {
            **existing,
            "decision": "NOT_EVALUATED",
            "execution_status": "PROVIDER_UNSTABLE",
            "adopted": False,
            "operational_block": "V2_3_PROVIDER_UNSTABLE",
            "quality_comparison_valid": False,
        },
    )
    write_json(V23 / "summary.json", {
        "pipeline": "pipeline_v2_3_support_units",
        "status": status,
        "retrieval_calls": 0,
        "reranker_calls": 0,
        "generation_calls": len(rows),
        "historical_v2_2_baseline_reused": True,
        "decision": "NOT_EVALUATED",
    })
    report = (
        "# V2.3 paired execution status\n\n"
        "The provider preflight and V2.2 baseline completed. The V2.3 support-unit "
        "paired run was stopped after bounded provider failures, so no architecture "
        "quality decision is valid.\n\n"
        + json.dumps(status, ensure_ascii=False, indent=2)
        + "\n"
    )
    (V23 / "provider-unstable-report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
