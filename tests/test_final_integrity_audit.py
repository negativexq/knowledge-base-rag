"""Focused tests for the final Phase 7 integrity audit helpers."""

from __future__ import annotations

import hashlib
import json

from scripts.final_integrity_audit import amendment, execution_comparison, historical_integrity


def test_historical_artifact_integrity_is_frozen() -> None:
    result = historical_integrity()
    assert result["integrity_status"] == "PASS"
    assert result["matches"]["preregistration"] is True
    assert result["matches"]["v2_2_baseline"] is True
    assert result["matches"]["v2_3_initial"] is True
    assert result["matches"]["evidence_snapshots"] is True


def test_execution_audit_detects_missing_v22_num_predict() -> None:
    result = execution_comparison()
    assert result["paired_execution_integrity"] == "FAIL"
    assert result["reason"] == "NON_COMPARABLE_EXECUTION_CONFIG"
    assert result["fields"]["num_predict"] == {
        "v2_2": "UNSET",
        "v2_3": 1024,
        "match": False,
    }
    assert result["trigger_corrected_rerun"] is True


def test_amendment_freezes_original_rules_and_hashes_deterministically() -> None:
    value = amendment()
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    assert value["no_threshold_changes"] is True
    assert value["same_seeds"] == [41, 42, 43, 44, 45]
    assert value["same_success_definition"] == "VISIBLE_CORRECT_AND_CORRECTLY_ATTRIBUTED"
    assert len(digest) == 64
