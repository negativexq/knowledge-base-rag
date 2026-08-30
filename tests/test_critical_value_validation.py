"""Focused tests for the canonical claim-local critical-value guard."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.critical_values import claim_local_critical_value_audit
from app.evidence.support_units import SupportUnit
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer


def unit(
    support_id: str,
    text: str,
    *,
    authorized: bool = True,
    visible: bool = True,
) -> SupportUnit:
    evidence_id, _ = support_id.split(".", 1)
    return SupportUnit(
        support_unit_id=support_id,
        parent_evidence_block_id=f"block-{evidence_id}",
        evidence_id=evidence_id,
        source_id="source",
        document_version="version",
        section_id="section",
        contributing_chunk_ids=("chunk",),
        tenant_id="tenant",
        authorized=authorized,
        model_visible=visible,
        text=text,
    )


def validate(text: str, units: list[SupportUnit]) -> object:
    answer = parse_support_unit_answer(
        json.dumps(
            {
                "answer_parts": [
                    {"text": text, "support_ids": [unit.support_unit_id for unit in units]}
                ],
                "abstain": False,
            }
        )
    )
    return validate_support_unit_answer(answer, units)


def test_unrelated_value_is_ignored() -> None:
    audit = claim_local_critical_value_audit(
        "Hold the button for 5 seconds.",
        ["Press and hold the button for 5 seconds.", "The timeout is 30 minutes."],
    )
    assert audit["pass"] is True


def test_numeric_duration_version_and_percentage_conflicts_are_rejected() -> None:
    cases = [
        ("Hold for 50 seconds.", "Hold for 5 seconds."),
        ("Wait 30 minutes.", "Wait 30 seconds."),
        ("Use version 2.2.", "Use version 2.1."),
        ("Maximum is 100%.", "Maximum is 10%."),
    ]
    for claim, support in cases:
        result = claim_local_critical_value_audit(claim, [support])
        assert result["pass"] is False
        assert result["status"] in {
            "CRITICAL_VALUE_DIRECT_CONFLICT",
            "CRITICAL_VALUE_INDETERMINATE",
        }


def test_multiple_critical_values_are_checked_independently() -> None:
    result = claim_local_critical_value_audit(
        "Use version 2.1 and wait 5 seconds.",
        ["Use version 2.1.", "Wait 5 seconds."],
    )
    assert result["pass"] is True
    assert all(trace["status"] == "DIRECT_SUPPORT" for trace in result["token_traces"])


def test_indeterminate_boolean_conflict_remains_conservative() -> None:
    result = claim_local_critical_value_audit(
        "Yes, this setting is available.",
        ["The setting may not be available in this model."],
    )
    assert result["pass"] is False
    assert result["status"] == "CRITICAL_VALUE_INDETERMINATE"


def test_support_id_security_is_unchanged() -> None:
    hidden = validate("Use the setting.", [unit("E1.S1", "Use the setting.", visible=False)])
    assert "HIDDEN_SUPPORT_ID" in hidden.failure_codes
    unauthorized = validate(
        "Use the setting.", [unit("E1.S1", "Use the setting.", authorized=False)]
    )
    assert "UNAUTHORIZED_SUPPORT_ID" in unauthorized.failure_codes


def test_citation_metadata_does_not_become_material_evidence() -> None:
    result = claim_local_critical_value_audit(
        "Use the setting. [s.filesystem:handbook/1/0]",
        ["Use the setting."],
    )
    assert result["answer_critical_tokens"] == []
    assert result["pass"] is False
    assert result["status"] == "CRITICAL_VALUE_UNSUPPORTED"


def test_unknown_support_id_is_not_repaired() -> None:
    answer = parse_support_unit_answer(
        json.dumps(
            {
                "answer_parts": [{"text": "Use it.", "support_ids": ["E9.S1"]}],
                "abstain": False,
            }
        )
    )
    result = validate_support_unit_answer(answer, [unit("E1.S1", "Use it.")])
    assert "UNKNOWN_SUPPORT_ID" in result.failure_codes


def test_frozen_replay_target_and_runner_are_artifact_only() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "artifacts/ragbench/canonical/basic50-final"
    rows = [
        json.loads(line)
        for line in (source / "validation-results.jsonl").read_text().splitlines()
        if line
    ]
    target = [
        row for row in rows if "CRITICAL_VALUE_CONFLICT" in row.get("validator_failure_codes", [])
    ]
    assert len(target) == 10
    runner = (root / "scripts/replay_canonical_validator_fix.py").read_text().lower()
    for forbidden in ("import openai", "import ollama", "import qdrant"):
        assert forbidden not in runner
