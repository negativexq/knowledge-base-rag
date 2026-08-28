import json

import pytest

from app.evaluation.critical_values import critical_value_status, extract_critical_values
from app.llm.structured_output import (
    parse_support_unit_answer,
    render_support_unit_answer,
    support_unit_output_schema,
    support_unit_pattern_output_schema,
    validate_support_unit_answer,
)
from app.llm.support_units import build_support_units, serialize_support_units
from app.retrieval.hybrid_search import SearchResult


def block(text: str, evidence_id: str = "E1", tenant: str = "tenant-a") -> SearchResult:
    return SearchResult(
        score=1.0,
        id=f"block-{evidence_id}",
        payload={
            "evidence_id": evidence_id,
            "evidence_block_id": f"block-{evidence_id}",
            "source_id": "policy",
            "tenant_id": tenant,
            "heading_path": ["Policy"],
            "contributing_chunk_ids": [f"chunk-{evidence_id}"],
            "text": text,
        },
    )


def test_support_units_are_deterministic_and_preserve_provenance():
    units = build_support_units([block("Rule one.\n\nRule two.")])
    assert [unit.support_unit_id for unit in units] == ["E1.U1", "E1.U2"]
    assert units[0].contributing_chunk_ids == ("chunk-E1",)
    assert "[SUPPORT UNIT E1.U1]" in serialize_support_units(units)


def test_schema_constrains_support_ids():
    units = build_support_units([block("14 calendar days")])
    schema = support_unit_output_schema(units)
    assert schema["properties"]["answer_parts"]["items"]["properties"]["support_ids"]["items"][
        "enum"
    ] == ["E1.U1"]


def test_pattern_schema_is_diagnostic_only_and_preserves_support_id_shape():
    schema = support_unit_pattern_output_schema()
    support_items = schema["properties"]["answer_parts"]["items"]["properties"]["support_ids"][
        "items"
    ]
    assert support_items["pattern"] == r"^E[1-9][0-9]*\.U[1-9][0-9]*$"
    assert "enum" not in support_items


def test_valid_support_unit_survives_and_renders():
    units = build_support_units([block("14 calendar days")])
    answer = parse_support_unit_answer(
        json.dumps(
            {"answer_parts": [{"text": "14 days", "support_ids": ["E1.U1"]}], "abstain": False}
        )
    )
    result = validate_support_unit_answer(answer, units)
    assert len(result.valid_parts) == 1
    assert render_support_unit_answer(result.valid_parts) == "14 days [E1.U1]"


@pytest.mark.parametrize(
    "payload",
    [
        {"answer_parts": [{"text": "30 days", "support_ids": ["E1.U1"]}], "abstain": False},
        {"answer_parts": [{"text": "14 days", "support_ids": ["E9.U1"]}], "abstain": False},
    ],
)
def test_conflict_or_unknown_support_is_rejected(payload):
    units = build_support_units([block("14 calendar days")])
    result = validate_support_unit_answer(parse_support_unit_answer(json.dumps(payload)), units)
    assert not result.valid_parts
    assert result.application_abstain


def test_application_forces_abstention_when_no_parts_are_supported():
    units = build_support_units([block("A policy paragraph")])
    answer = parse_support_unit_answer(json.dumps({"answer_parts": [], "abstain": False}))
    result = validate_support_unit_answer(answer, units)
    assert result.application_abstain
    assert "NO_VALID_SUPPORT_BACKED_CLAIMS" in result.failure_codes


def test_model_abstain_with_parts_fails_closed():
    with pytest.raises(ValueError):
        parse_support_unit_answer(
            json.dumps({"answer_parts": [{"text": "x", "support_ids": ["E1.U1"]}], "abstain": True})
        )


def test_critical_values_distinguish_supported_absent_and_conflict():
    assert (
        critical_value_status("14 calendar days", "within 14 calendar days")
        == "CRITICAL_VALUE_SUPPORTED"
    )
    assert (
        critical_value_status("14 calendar days", "within the policy window")
        == "CRITICAL_VALUE_ABSENT"
    )
    assert (
        critical_value_status("14 calendar days", "within 30 calendar days")
        == "CRITICAL_VALUE_CONFLICT"
    )


def test_critical_value_parser_supports_currency_and_boolean():
    values = extract_critical_values("The fee is 12.50 EUR and the flag is true.")
    assert any(value.kind == "CURRENCY" and value.unit == "EUR" for value in values)
    assert any(value.kind == "BOOLEAN" and value.value == "true" for value in values)
