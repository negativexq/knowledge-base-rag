"""Focused tests for the canonical claim-local critical-value guard."""

from __future__ import annotations

import json

import pytest

from app.evaluation.critical_values import (
    _v6_mask_rejected_premises,
    _v6_tokenized,
    claim_local_critical_value_audit,
    claim_local_critical_value_audit_v4,
    claim_local_critical_value_audit_v5,
    claim_local_critical_value_audit_v6,
)
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


@pytest.mark.parametrize(
    ("claim", "support"),
    [
        (
            "The documented validity is 90 days, not 30 days.",
            "The documented validity is 90 days.",
        ),
        (
            "The correct limit is 120 requests per minute, not 100.",
            "The correct limit is 120 requests per minute.",
        ),
        ("v8.1.3 is wrong; the supported release is v8.1.2.", "The supported release is v8.1.2."),
    ],
)
def test_v4_guard_allows_deterministic_corrective_pairs(claim: str, support: str) -> None:
    v3 = claim_local_critical_value_audit(claim, [support], validator_version="v3")
    v4 = claim_local_critical_value_audit_v4(claim, [support])
    assert v3["pass"] is False
    assert v4["pass"] is True
    assert v4["polarity_guard_applied"] is True
    assert v4["polarity_guard_suppressed_count"] >= 1


@pytest.mark.parametrize(
    ("claim", "support"),
    [
        ("The token does not expire after 90 days.", "The token expires after 90 days."),
        ("120 is greater than 100.", "The documented limit is 120 requests per minute."),
        ("The docs say '30 days'.", "The docs say 30 days."),
        (
            "The limit might be 100 or 120 requests per minute.",
            "The documented limit is 120 requests per minute.",
        ),
    ],
)
def test_v4_does_not_globally_suppress_non_corrective_literals(
    claim: str, support: str
) -> None:
    v3 = claim_local_critical_value_audit(claim, [support], validator_version="v3")
    v4 = claim_local_critical_value_audit_v4(claim, [support])
    assert v4["polarity_guard_applied"] is False
    assert v4["validator_outcome"] == v3["validator_outcome"]


def test_v4_unsupported_positive_claim_remains_conservative() -> None:
    result = claim_local_critical_value_audit_v4(
        "The limit is 100 requests per minute.",
        ["The documented limit is 120 requests per minute."],
    )
    assert result["pass"] is False
    assert result["polarity_guard_applied"] is False


def _v5_polarities(claim: str) -> list[str]:
    result = claim_local_critical_value_audit_v5(claim, [claim])
    return [item["polarity"] for item in result["v5_polarity_occurrences"]]


def test_v5_same_literal_rejected_then_asserted_is_occurrence_local() -> None:
    result = claim_local_critical_value_audit_v5(
        "30 is not correct; the retention window is 30 days.",
        ["The retention window is 30 days."],
    )
    occurrences = result["v5_polarity_occurrences"]
    assert [item["polarity"] for item in occurrences] == [
        "REJECTED_PREMISE",
        "POSITIVE_ASSERTION",
    ]
    assert result["v5_occurrence_guard_suppressed_count"] == 1


def test_v5_same_literal_asserted_then_rejected_is_occurrence_local() -> None:
    assert _v5_polarities(
        "The legacy limit is 100. The 100 in your question is not the current rate; it is 120."
    ) == ["POSITIVE_ASSERTION", "REJECTED_PREMISE", "POSITIVE_ASSERTION"]


def test_v5_same_literal_twice_positive_remains_validated() -> None:
    assert _v5_polarities("The old limit was 100 and the current limit is 100.") == [
        "POSITIVE_ASSERTION",
        "POSITIVE_ASSERTION",
    ]


def test_v5_same_literal_twice_rejected_can_be_skipped_independently() -> None:
    assert _v5_polarities(
        "30 is not correct; the 30-day figure you cited is also unsupported."
    ) == ["REJECTED_PREMISE", "REJECTED_PREMISE"]


def test_v5_type_mismatch_does_not_collapse_same_surface_literal() -> None:
    result = claim_local_critical_value_audit_v5(
        "30 is not correct; a separate retention window is 30 days.",
        ["A separate retention window is 30 days."],
    )
    occurrences = result["v5_polarity_occurrences"]
    assert len(occurrences) == 2
    assert occurrences[0]["polarity"] == "REJECTED_PREMISE"
    assert occurrences[1]["polarity"] != "REJECTED_PREMISE"
    assert occurrences[0]["kind"] != occurrences[1]["kind"]


def test_v5_ambiguous_sibling_remains_validating() -> None:
    assert _v5_polarities(
        "30 is not correct; a separate policy may use 30 days."
    ) == ["REJECTED_PREMISE", "UNKNOWN"]


def test_v5_masks_only_exact_occurrence_span() -> None:
    result = claim_local_critical_value_audit_v5(
        "30 is not correct; the 30-day retention window is documented.",
        ["The 30-day retention window is documented."],
    )
    assert result["v5_occurrence_guard_suppressed_count"] == 1
    assert result["v5_occurrence_guard_applied"] is True


def test_v5_preserves_v4_single_occurrence_behavior() -> None:
    claim = "The documented validity is 90 days, not 30 days."
    support = ["The documented validity is 90 days."]
    v4 = claim_local_critical_value_audit_v4(claim, support)
    v5 = claim_local_critical_value_audit_v5(claim, support)
    assert v4["pass"] is True
    assert v5["pass"] is True
    assert v5["v5_occurrence_guard_suppressed_count"] == v4[
        "polarity_guard_suppressed_count"
    ]


def test_v6_signed_literal_owns_sign_and_standalone_sibling_is_separate() -> None:
    claim = "The signed result is -204, not 204."
    occurrences = _v6_mask_rejected_premises(claim)[1]
    assert [(item["raw_literal"], item["start"], item["end"]) for item in occurrences] == [
        ("-204", 21, 25),
        ("204", 31, 34),
    ]
    assert [item["polarity"] for item in occurrences] == [
        "POSITIVE_ASSERTION",
        "REJECTED_PREMISE",
    ]


def test_v6_plus_signed_literal_does_not_emit_inner_number() -> None:
    occurrences = _v6_tokenized("The signed result is +42, not 42.")
    assert [item["raw_literal"] for item in occurrences] == ["+42", "42"]


@pytest.mark.parametrize(
    "claim",
    [
        "The value is 12.0, not 12.",
        "The rate is 10%, not 10 requests.",
        "The duration is 30 days, not 30.",
        "8.1.2 is supported, not 8.1.",
        "The issue is CVE-2025-1234, not 1234.",
        "The date is 2026-08-31.",
    ],
)
def test_v6_typed_literals_do_not_emit_spurious_nested_subspans(claim: str) -> None:
    occurrences = _v6_tokenized(claim)
    spans = [(int(item["start"]), int(item["end"])) for item in occurrences]
    for index, (start, end) in enumerate(spans):
        assert not any(
            other_start <= start and end <= other_end and (other_start, other_end) != (start, end)
            for other_index, (other_start, other_end) in enumerate(spans)
            if other_index != index
        )


def test_v6_c57_shadow_does_not_skip_signed_assertion() -> None:
    result = claim_local_critical_value_audit_v6(
        "The signed result is -204, not 204.",
        ["The signed result is -204."],
    )
    assert [item["polarity"] for item in result["v6_polarity_occurrences"]] == [
        "POSITIVE_ASSERTION",
        "REJECTED_PREMISE",
    ]
    assert result["v6_occurrence_guard_suppressed_count"] == 1
