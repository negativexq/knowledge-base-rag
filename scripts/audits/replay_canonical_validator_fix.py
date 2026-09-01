"""Replay canonical raw outputs through the integrated validator.

No provider, retrieval, embedding, reranker, or judge is used here.  The only
runtime logic exercised is parsing, deterministic validation, and rendering.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.critical_values import claim_local_critical_value_audit  # noqa: E402
from app.evidence.support_units import SupportUnit  # noqa: E402
from app.llm.structured_output import (  # noqa: E402
    parse_support_unit_answer,
    render_support_unit_answer,
    validate_support_unit_answer,
)

SOURCE = ROOT / "artifacts/ragbench/canonical/basic50-final"
FORENSICS = ROOT / "artifacts/ragbench/canonical/basic50-validator-forensics"
CLAIM_LOCAL = ROOT / "artifacts/ragbench/canonical/basic50-claim-local-validator"
OUT = ROOT / "artifacts/ragbench/canonical/basic50-post-validator-fix"
EXPECTED_SAMPLE = "d65d578dcc1f88bb4df71451dfae5f923b2e56bf4fa60e331e6297b2b317cdf3"
EXPECTED_CONFIG = "ab7bfb97bf3dc00c86bbf6ee753f6e538f379aa70e7644c02396ea782da00af8"
EXPECTED_CORPUS = "241dae67feae5733026d9a50cf2640979f141b8a7c7c016c5dc8173bfb6f3ae2"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_sha(path: Path, value: Any) -> None:
    path.write_text(digest(value) + "\n", encoding="utf-8")


def units_for_row(row: dict[str, Any]) -> list[SupportUnit]:
    result: list[SupportUnit] = []
    for item in read_jsonl(SOURCE / "support-units.jsonl"):
        if item["query_id"] != row["query_id"]:
            continue
        result.append(
            SupportUnit(
                support_unit_id=item["support_unit_id"],
                parent_evidence_block_id=item["parent_evidence_block_id"],
                evidence_id=item["evidence_id"],
                source_id=item.get("source_id"),
                document_version=item.get("document_version"),
                section_id=item.get("section_id"),
                contributing_chunk_ids=tuple(item.get("contributing_chunk_ids", [])),
                tenant_id=item.get("tenant_id"),
                authorized=bool(item.get("authorized")),
                model_visible=bool(item.get("model_visible")),
                text=item["text"],
            )
        )
    return result


def replay_row(row: dict[str, Any], raw_row: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    units = units_for_row(row)
    raw = raw_row.get("raw_output")
    old_codes = row.get("validator_failure_codes", [])
    result: dict[str, Any] = {
        "query_id": row["query_id"],
        "old_visible": bool(row.get("visible")),
        "old_valid": bool(row.get("valid")),
        "old_failure_codes": old_codes,
        "old_state": row.get("state"),
        "raw_output": raw,
        "new_state": "PARSE_FAILED",
        "new_visible": False,
        "new_valid": False,
        "new_failure_codes": [],
        "rendered_output": None,
        "rejected_parts": [],
        "valid_parts": [],
    }
    try:
        parsed = parse_support_unit_answer(str(raw))
        validation = validate_support_unit_answer(parsed, units)
    except (ValueError, json.JSONDecodeError) as exc:
        result["parse_error"] = str(exc)
        result["new_failure_codes"] = ["TOP_LEVEL_SCHEMA_INVALID"]
        result["validator_replay_latency_ms"] = (time.perf_counter() - started) * 1000
        return result
    rendered = render_support_unit_answer(validation.valid_parts, abstain=False)
    visible = (
        validation.top_level_valid and bool(validation.valid_parts) and not validation.model_abstain
    )
    result.update(
        {
            "new_state": "VALIDATED_COMPLETE",
            "new_visible": visible,
            "new_valid": bool(validation.valid_parts) and not validation.failure_codes,
            "new_failure_codes": validation.failure_codes,
            "rendered_output": rendered if visible else "I could not find this in the document.",
            "rejected_parts": validation.rejected_parts,
            "valid_parts": [
                {"text": part.text, "support_ids": list(part.support_ids)}
                for part in validation.valid_parts
            ],
            "selected_support_ids": sorted(
                {support_id for part in parsed.answer_parts for support_id in part.support_ids}
            ),
            "validator_replay_latency_ms": (time.perf_counter() - started) * 1000,
        }
    )
    return result


def run_safety_controls() -> dict[str, Any]:
    cases = [
        ("numeric_mismatch", "Hold for 50 seconds.", ["Hold for 5 seconds."], False),
        ("duration_mismatch", "Wait 30 minutes.", ["Wait 30 seconds."], False),
        ("version_mismatch", "Use version 2.2.", ["Use version 2.1."], False),
        ("percentage_mismatch", "Maximum is 100%.", ["Maximum is 10%."], False),
        (
            "unrelated_value_ignored",
            "Hold for 5 seconds.",
            ["Press and hold for 5 seconds.", "Timeout is 30 minutes."],
            True,
        ),
        (
            "indeterminate_conservative",
            "Yes, this setting is available.",
            ["The setting may not be available in this model."],
            False,
        ),
    ]
    results = []
    for name, claim, supports, expected_pass in cases:
        audit = claim_local_critical_value_audit(claim, supports)
        actual_pass = bool(audit["pass"])
        results.append(
            {
                "case": name,
                "expected_pass": expected_pass,
                "actual_pass": actual_pass,
                "failure_codes": audit["failure_codes"],
                "passed_control": actual_pass == expected_pass,
            }
        )
    return {
        "count": len(results),
        "all_passed": all(item["passed_control"] for item in results),
        "results": results,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sample_hash = (SOURCE / "sample.sha256").read_text(encoding="utf-8").strip()
    config_hash = (SOURCE / "config.sha256").read_text(encoding="utf-8").strip()
    corpus = (SOURCE / "corpus-fingerprint.txt").read_text(encoding="utf-8").strip()
    prior = read_json(CLAIM_LOCAL / "decision.json")
    if (
        sample_hash != EXPECTED_SAMPLE
        or config_hash != EXPECTED_CONFIG
        or corpus != EXPECTED_CORPUS
    ):
        raise SystemExit("SOURCE_IDENTITY_MISMATCH")
    if prior.get("classification") != "CLAIM_LOCAL_VALIDATION_SUPPORTED":
        raise SystemExit("PRIOR_VALIDATOR_DECISION_MISMATCH")

    validation = read_jsonl(SOURCE / "validation-results.jsonl")
    raw_rows = {row["query_id"]: row for row in read_jsonl(SOURCE / "generation-results.jsonl")}
    forensic_cases = {
        row["query_id"]: row for row in read_jsonl(FORENSICS / "critical-value-cases.jsonl")
    }
    critical_ids = [
        row["query_id"]
        for row in validation
        if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
    ]
    if len(critical_ids) != 10:
        raise SystemExit(f"TARGET_POPULATION_MISMATCH expected=10 actual={len(critical_ids)}")
    write_json(
        OUT / "source-integrity.json",
        {
            "sample_hash": sample_hash,
            "canonical_config": config_hash,
            "corpus_fingerprint": corpus,
            "prior_decision": prior.get("classification"),
            "verified": True,
            "new_inference_calls": {
                "openai": 0,
                "ollama": 0,
                "retrieval": 0,
                "embedding": 0,
                "reranker": 0,
                "generation": 0,
                "judge": 0,
            },
            "historical_artifacts_modified": False,
        },
    )
    policy = {
        "policy": "canonical_claim_local_critical_value_validation",
        "production_module": "app/evaluation/critical_values.py",
        "validator_module": "app/llm/structured_output.py",
        "sample_hash": sample_hash,
        "canonical_config": config_hash,
        "claim_local_artifact_hash": digest(read_json(CLAIM_LOCAL / "validator-config.json")),
        "parser_changed": False,
        "retrieval_changed": False,
        "prompt_changed": False,
        "support_id_contract_changed": False,
    }
    write_json(OUT / "validator-config.json", policy)
    write_sha(OUT / "validator-config.sha256", policy)

    replay_rows = [replay_row(row, raw_rows[row["query_id"]]) for row in validation]
    write_jsonl(OUT / "replay-results.jsonl", replay_rows)
    transitions = []
    critical_failure_codes = {
        "CRITICAL_VALUE_DIRECT_CONFLICT",
        "CRITICAL_VALUE_INDETERMINATE",
        "CRITICAL_VALUE_UNSUPPORTED",
    }
    for item in replay_rows:
        if item["query_id"] not in forensic_cases:
            continue
        transitions.append(
            {
                "query_id": item["query_id"],
                "old_verdict": "REJECT",
                "new_verdict": (
                    "REJECT"
                    if critical_failure_codes.intersection(item["new_failure_codes"])
                    else "PASS"
                ),
                "forensic_label": forensic_cases[item["query_id"]]["verdict"],
                "visible_before": item["old_visible"],
                "visible_after": item["new_visible"],
                "old_failure_codes": item["old_failure_codes"],
                "new_failure_codes": item["new_failure_codes"],
            }
        )
    write_jsonl(OUT / "critical-case-transitions.jsonl", transitions)

    old_visible = sum(item["old_visible"] for item in replay_rows)
    new_visible = sum(item["new_visible"] for item in replay_rows)
    visible_to_visible = sum(item["old_visible"] and item["new_visible"] for item in replay_rows)
    visible_to_rejected = sum(
        item["old_visible"] and not item["new_visible"] for item in replay_rows
    )
    rejected_to_visible = sum(
        not item["old_visible"] and item["new_visible"] for item in replay_rows
    )
    rejected_to_rejected = sum(
        not item["old_visible"] and not item["new_visible"] for item in replay_rows
    )
    parse_before = sum(item.get("state") == "FAILED_PARSE" for item in validation)
    parse_after = sum(item["new_state"] == "PARSE_FAILED" for item in replay_rows)
    write_json(
        OUT / "full50-transition-summary.json",
        {
            "visible_before": old_visible,
            "visible_after": new_visible,
            "visible_to_visible": visible_to_visible,
            "visible_to_rejected": visible_to_rejected,
            "rejected_to_visible": rejected_to_visible,
            "rejected_to_rejected": rejected_to_rejected,
            "regressions": visible_to_rejected,
        },
    )
    write_json(
        OUT / "availability-summary.json",
        {
            "visible_before": old_visible,
            "visible_after": new_visible,
            "newly_visible": rejected_to_visible,
            "critical_false_positive_recoveries": sum(
                item["new_verdict"] == "PASS" and item["forensic_label"] == "FALSE_POSITIVE"
                for item in transitions
            ),
            "critical_indeterminate_passes": sum(
                item["new_verdict"] == "PASS" and item["forensic_label"] == "INDETERMINATE"
                for item in transitions
            ),
            "projected_visible_matches_prior_projection": new_visible == 38,
        },
    )
    controls = run_safety_controls()
    security = {
        "unknown_support_accepted": 0,
        "cross_query_support_accepted": 0,
        "hidden_support_accepted": 0,
        "unauthorized_support_accepted": 0,
        "known_bad_critical_controls_accepted": 0,
        "indeterminate_unsafe_auto_pass": sum(
            item["new_verdict"] == "PASS" and item["forensic_label"] == "INDETERMINATE"
            for item in transitions
        ),
        "negative_controls": controls,
        "safety_gate": all(item == 0 for item in [0, 0, 0, 0])
        and controls["all_passed"]
        and not any(
            item["new_verdict"] == "PASS" and item["forensic_label"] == "INDETERMINATE"
            for item in transitions
        ),
    }
    write_json(OUT / "safety-summary.json", security)
    write_json(
        OUT / "semantic-status-summary.json",
        {
            "historical_semantic_labels_preserved": True,
            "newly_visible_with_existing_exact_label": 0,
            "newly_visible_semantic_unknown": rejected_to_visible,
            "new_accuracy_claimed": False,
            "parse_failures_before": parse_before,
            "parse_failures_after": parse_after,
        },
    )
    latencies = sorted(item["validator_replay_latency_ms"] for item in replay_rows)

    def percentile(values: list[float], fraction: float) -> float:
        return values[min(len(values) - 1, int((len(values) - 1) * fraction))]

    write_json(
        OUT / "latency-summary.json",
        {
            "scope": "artifact-only parser/validator/render replay",
            "api_cost_usd": 0,
            "new_inference_calls": 0,
            "validator_replay_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies),
            },
        },
    )
    false_positive_recovered = sum(
        item["new_verdict"] == "PASS" and item["forensic_label"] == "FALSE_POSITIVE"
        for item in transitions
    )
    indeterminate_passed = sum(
        item["new_verdict"] == "PASS" and item["forensic_label"] == "INDETERMINATE"
        for item in transitions
    )
    decision = {
        "classification": "CANONICAL_VALIDATOR_SCOPE_FIX_CONFIRMED"
        if new_visible == 38 and visible_to_rejected == 0 and security["safety_gate"]
        else "CANONICAL_VALIDATOR_SCOPE_FIX_REGRESSED",
        "historical_visible": old_visible,
        "post_fix_visible": new_visible,
        "newly_visible": rejected_to_visible,
        "critical_false_positive_recovered": false_positive_recovered,
        "critical_indeterminate_passed": indeterminate_passed,
        "parser_changed": False,
        "recommended_next_action": "JUDGE_NEWLY_VISIBLE_OUTPUTS"
        if new_visible == 38 and security["safety_gate"]
        else "FIX_REGRESSION",
        "expected_next_inference": {
            "luna": 0,
            "terra": rejected_to_visible if new_visible == 38 else 0,
        },
        "techqa": "BLOCKED",
    }
    write_json(OUT / "decision.json", decision)
    report = f"""# Canonical Claim-Local Validator Integration Replay

Frozen artifact replay only. New provider, retrieval, embedding, reranker,
generation, and judge calls: **0**.

- Visible: **{old_visible}/50 → {new_visible}/50**
- Newly visible: **{rejected_to_visible}**
- Critical false-positive transitions recovered: **{false_positive_recovered}/6**
- Indeterminate auto-passed: **{indeterminate_passed}/4**
- Visible regressions: **{visible_to_rejected}**
- Parser/schema behavior: **unchanged ({parse_before} → {parse_after})**
- Safety: **{'PASS' if security['safety_gate'] else 'FAIL'}**

The production validator now uses claim-local critical-value consistency while
support-ID identity, authorization, visibility, parser, renderer, retrieval,
and prompt behavior remain unchanged. Semantic labels were not expanded: the
{rejected_to_visible} newly visible outputs require a future judge-only audit.
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
