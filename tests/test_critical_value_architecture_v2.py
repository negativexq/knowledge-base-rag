"""Reusable contracts for the experimental Architecture V2 boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.evaluation.critical_occurrence_validation import (
    validate_occurrences_v3,
)
from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_roles import classify_occurrence_roles
from app.evaluation.critical_validator_architecture_v2 import audit_claim_architecture_v2
from app.evaluation.critical_values import claim_local_critical_value_audit


def roles(answer: str) -> list[str]:
    occurrences = extract_critical_occurrences(answer)
    return [item.role for item in classify_occurrence_roles(answer, occurrences)]


def test_occurrence_identity_is_span_local_for_equal_values() -> None:
    occurrences = extract_critical_occurrences("30 is wrong; retention is 30 days.")
    assert len(occurrences) == 2
    assert occurrences[0].normalized_value == occurrences[1].normalized_value == "30"
    assert (occurrences[0].span_start, occurrences[0].span_end) != (
        occurrences[1].span_start,
        occurrences[1].span_end,
    )
    assert occurrences[0].occurrence_id != occurrences[1].occurrence_id


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("The signed result is -204, not 204.", ["VALIDATE", "SKIP_REJECTED_PREMISE"]),
        (
            "30 is not correct; the retention window is 30 days.",
            ["SKIP_REJECTED_PREMISE", "VALIDATE"],
        ),
        (
            "The legacy limit is 100. The 100 in your question is not current; it is 120.",
            ["VALIDATE", "SKIP_REJECTED_PREMISE", "VALIDATE"],
        ),
        ("The old limit was 100 and the current limit is 100.", ["VALIDATE", "VALIDATE"]),
    ],
)
def test_roles_are_occurrence_local(answer: str, expected: list[str]) -> None:
    assert roles(answer) == expected


def test_typed_sibling_roles_do_not_depend_on_type_equality() -> None:
    answer = "30 is not correct; a separate retention window is 30 days."
    occurrences = extract_critical_occurrences(answer)
    decisions = classify_occurrence_roles(answer, occurrences)
    assert [item.lexical_type for item in occurrences] == ["NUMBER", "DURATION"]
    assert [item.role for item in decisions] == ["SKIP_REJECTED_PREMISE", "VALIDATE"]


def test_signed_and_nested_boundaries_are_owned() -> None:
    occurrences = extract_critical_occurrences("The signed result is -204, not 204.")
    assert [(item.raw_literal, item.span_start, item.span_end) for item in occurrences] == [
        ("-204", 21, 25),
        ("204", 31, 34),
    ]


def test_ambiguous_role_remains_validation() -> None:
    assert roles("30 or 90 may be relevant.") == ["VALIDATE", "VALIDATE"]


def test_role_decision_does_not_mutate_occurrence() -> None:
    occurrences = extract_critical_occurrences("30 is wrong; retention is 30 days.")
    before = occurrences[0]
    classify_occurrence_roles("30 is wrong; retention is 30 days.", occurrences)
    assert occurrences[0] == before
    with pytest.raises(FrozenInstanceError):
        occurrences[0].normalized_value = "31"  # type: ignore[misc]


def test_architecture_v2_has_no_mask_or_post_role_reextraction_flags() -> None:
    result = audit_claim_architecture_v2(
        "The signed result is -204, not 204.",
        ["The signed result is -204."],
    )
    assert result["raw_text_masked"] is False
    assert result["post_role_reextraction"] is False
    assert result["role_layer_rediscovery"] is False
    assert result["validate_occurrence_ids"] == ("claim.O1",)


@pytest.mark.parametrize(
    ("claim", "support"),
    [
        ("The limit is 120 requests per minute.", "The limit is 120 requests per minute."),
        ("The supported version is 8.1.2.", "The supported version is 8.1.2."),
        ("The SQLCODE is -204.", "The SQLCODE is -204."),
    ],
)
def test_v3_equivalence_for_unfiltered_occurrences(claim: str, support: str) -> None:
    old = claim_local_critical_value_audit(claim, [support], validator_version="v3")
    occurrences = extract_critical_occurrences(claim)
    new = validate_occurrences_v3(claim, [support], occurrences)
    assert new["validator_outcome"] == old["validator_outcome"]
    assert new["validator_reason_class"] == old["validator_reason_class"]
