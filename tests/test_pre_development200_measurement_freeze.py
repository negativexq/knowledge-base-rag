# ruff: noqa: E501
"""Zero-inference checks for the pre-Development200 measurement freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.prepare_pre_development200 import EXPECTED_CONFIG_FINGERPRINT, json_sha

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/phase-7/pre-development200"


def read(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_scoring_audit_preserves_task_and_safe_behavior_semantics() -> None:
    ambiguous = read("ambiguous-scoring-audit.json")
    injection = read("injection-scoring-audit.json")
    assert ambiguous["expected_behavior_counts"] == {"CLARIFICATION_EXPECTED": 4}
    assert ambiguous["clarification_success_count"] == 0
    assert ambiguous["actual_safe_behavior_count"] == 1
    assert ambiguous["unsafe_answer_count"] == 3
    assert ambiguous["genuine_completeness_failures"] == 0
    assert injection["genuine_completeness_failures"] == 2
    assert injection["security_control_actual_success_count"] == 2
    assert injection["metric_mismatch"] is False


def test_scoring_amendment_and_rescore_are_zero_inference() -> None:
    amendment = read("scoring-amendment.json")
    summary = read("smoke36-rescored-summary.json")
    assert amendment["required"] is True
    assert amendment["no_generation_rerun"] is True
    assert amendment["no_output_changes"] is True
    assert amendment["no_threshold_tuning"] is True
    assert summary["no_generation_calls"] is True
    assert summary["no_retrieval_calls"] is True
    assert summary["general_complete_metric_preserved"] is True


def test_transport_attempt_bookkeeping_is_explicit() -> None:
    audit = read("smoke36-transport-attempt-audit.json")
    assert audit["official_benchmark_records"] == 36
    assert audit["transport_attempts"] == 37
    assert audit["provider_failures"] == 0
    assert audit["extra_attempt_query_id"] == "cross-07-0"
    assert audit["first_vs_official_raw_output"] == "FIRST_OUTPUT_NOT_RECOVERABLE"


def test_attribution_sample_is_deterministic_and_frozen() -> None:
    sample = read("development200-attribution-sample.json")
    assert sample["population"] == "development200"
    assert sample["sample_size"] == 30
    assert len(sample["selected_query_ids"]) == 30
    assert len(set(sample["selected_query_ids"])) == 30
    assert sample["selection_algorithm"] == "sha256(query_id) ascending"
    canonical = {key: value for key, value in sample.items() if key not in {"selection_timestamp", "selection_hash"}}
    assert sample["selection_hash"] == json_sha(canonical)
    assert hashlib.sha256((OUT / "development200-attribution-sample.json").read_bytes()).hexdigest() == (OUT / "development200-attribution-sample.sha256").read_text().strip()


def test_measurement_plan_and_final_config_are_immutable_markers() -> None:
    config = json.loads((ROOT / "artifacts/phase-7/phase7-closure/final-v2-2-config.json").read_text())
    plan = read("development200-measurement-plan.json")
    plan_hash = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert config["config_fingerprint"] == EXPECTED_CONFIG_FINGERPRINT
    assert plan["config_fingerprint"] == EXPECTED_CONFIG_FINGERPRINT
    assert plan["status"] == "FROZEN_BEFORE_INFERENCE"
    assert plan_hash == (OUT / "development200-measurement-plan.sha256").read_text().strip()
    assert read("pre-development200-summary.json")["development200_started"] is False


def test_no_later_split_was_touched_by_freeze() -> None:
    summary = read("pre-development200-summary.json")
    assert summary["calibration_touched"] is False
    assert summary["frozen_touched"] is False
