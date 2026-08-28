"""Zero-inference regression tests for the Phase 7 closure artifacts."""

from __future__ import annotations

import hashlib
import json

from scripts.prepare_phase7_closure import (
    final_config,
    formal_recalculation,
    truncation_resolution,
)


def test_multi_01_0_is_not_overclassified_as_truncation() -> None:
    result = truncation_resolution()
    assert result["seeds_inspected"] == [41, 42, 43, 44, 45]
    assert result["direct_ceiling_hits"] == 0
    assert result["supported_truncation_artifacts"] == 0
    assert result["indeterminate_records"] == 5
    assert result["query_verdict_changed"] is False


def test_formal_gate_and_closure_selection_are_separate() -> None:
    result = formal_recalculation()
    assert result["formal_gate_verdict"] == "CLEAR_REGRESSION"
    assert result["selected_for_closure"] == "pipeline_v2_2_evidence_backed"
    assert result["v2_3_empirical_quality_superiority_established"] is False
    assert result["v2_3_contract_disproven"] is False
    assert result["v2_3_implementation_vs_contract_root_cause"] == "UNRESOLVED"


def test_final_v22_config_has_complete_frozen_execution_fingerprint() -> None:
    config = final_config()
    assert config["pipeline_version"] == "pipeline_v2_2_evidence_backed"
    assert config["execution"] == {
        "num_ctx": 4096,
        "num_predict": 1024,
        "temperature": 0.0,
        "think": False,
        "stream": False,
        "connect_timeout_seconds": 10.0,
        "read_timeout_seconds": 180.0,
        "overall_timeout_seconds": 240.0,
    }
    fingerprint_input = {key: value for key, value in config.items() if key != "config_fingerprint"}
    encoded = json.dumps(
        fingerprint_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert config["config_fingerprint"] == hashlib.sha256(encoded.encode()).hexdigest()


def test_phase7_closure_does_not_touch_later_splits() -> None:
    closure = json.loads(
        open("artifacts/phase-7/phase7-closure/summary.json", encoding="utf-8").read()
    )
    decision = json.loads(
        open(
            "artifacts/phase-7/final-integrity-audit/final-architecture-decision.json",
            encoding="utf-8",
        ).read()
    )
    assert closure["extension_status"] == "EXTENSION_BLOCKED_INSUFFICIENT_ELIGIBLE_POOL"
    assert decision["calibration_touched"] is False
    assert decision["frozen_touched"] is False
