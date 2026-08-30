"""Focused, provider-free tests for canonical validator forensics."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_canonical_support_validator_failures import (
    classify_critical_part,
    safe_subset_exists,
)


def test_numeric_conflict_is_false_positive_when_other_unit_is_unrelated() -> None:
    units = {
        "E1.S1": "The device supports HDMI 1 and HDMI 2.",
        # The current extractor short-circuits on a boolean token, so this
        # unrelated support unit makes the union appear to conflict with the
        # numerically supported claim.
        "E2.S1": "No unrelated setting is enabled.",
    }
    part = {"text": "Choose HDMI 1 or HDMI 2.", "support_ids": ["E1.S1", "E2.S1"]}
    result = classify_critical_part(part, units)
    assert result["verdict"] == "FALSE_POSITIVE"
    assert result["minimal_support_subset"] == "MINIMAL_SUBSET_EXISTS"
    assert result["minimal_support_ids"] == ["E1.S1"]


def test_citation_only_numbers_are_not_material_critical_values() -> None:
    units = {"E1.S1": "Run the test from Settings > Support."}
    part = {
        "text": "Run the test. [s.filesystem:handbook/1/0]",
        "support_ids": ["E1.S1"],
    }
    result = classify_critical_part(part, units)
    assert result["verdict"] == "FALSE_POSITIVE"
    assert result["material_answer_values"] == []


def test_boolean_conflict_without_claim_local_support_is_indeterminate() -> None:
    units = {"E1.S1": "The speakers are making an odd sound. No sound is heard."}
    part = {"text": "Yes, this setting is available.", "support_ids": ["E1.S1"]}
    result = classify_critical_part(part, units)
    assert result["verdict"] == "INDETERMINATE"


def test_production_like_numeric_mismatch_does_not_get_subset_rescue() -> None:
    units = {"E1.S1": "Hold the button for 5 seconds."}
    part = {"text": "Hold the button for 50 seconds.", "support_ids": ["E1.S1"]}
    assert safe_subset_exists(part, units) == ("INDETERMINATE", [])


def test_canonical_artifact_target_and_critical_counts() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "artifacts/ragbench/canonical/basic50-final"
    rows = [
        json.loads(line) for line in (source / "validation-results.jsonl").read_text().splitlines()
    ]
    failures = [row for row in rows if not (row.get("valid") and row.get("visible"))]
    critical = [
        row
        for row in failures
        if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
    ]
    assert len(failures) == 19
    assert len(critical) == 10


def test_forensic_runner_has_no_provider_or_retrieval_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/audit_canonical_support_validator_failures.py").read_text()
    for forbidden in ("openai", "ollama", "qdrant", "reranker", "embedding"):
        assert f"import {forbidden}" not in source.lower()
