import json

import pytest

from app.evidence.support_units import (
    build_support_units,
    resolve_support_ids,
    serialize_support_units,
)
from app.llm.openai_client import (
    responses_strict_schema,
    validate_responses_strict_schema_shape,
)
from app.llm.structured_output import (
    parse_support_unit_answer,
    parse_support_unit_state_machine_answer,
    support_unit_output_schema,
    support_unit_output_schema_state_machine,
    validate_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult


def evidence(text: str) -> SearchResult:
    return SearchResult(
        score=1.0,
        id="chunk-1",
        payload={
            "evidence_id": "E1",
            "evidence_block_id": "block-1",
            "source_id": "manual",
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "heading_path": ["Policy"],
            "contributing_chunk_ids": ["chunk-1"],
            "text": text,
        },
    )


def test_support_units_are_stable_and_retain_exact_text() -> None:
    units = build_support_units([evidence("Rule one.\n\nRule two.")])
    assert [unit.support_unit_id for unit in units] == ["E1.S1", "E1.S2"]
    assert units[0].text == "Rule one."
    assert "[SUPPORT UNIT E1.S1]" in serialize_support_units(units)


def test_schema_enumerates_only_request_support_ids() -> None:
    units = build_support_units([evidence("14 calendar days")])
    schema = support_unit_output_schema(units)
    support_ids = schema["properties"]["answer_parts"]["items"]["properties"]["support_ids"]
    assert support_ids["items"]["enum"] == ["E1.S1"]


def test_state_machine_schema_has_exclusive_answer_and_abstain_branches() -> None:
    units = build_support_units([evidence("14 calendar days")])
    schema = support_unit_output_schema_state_machine(units)
    branches = schema["properties"]["result"]["anyOf"]
    assert "anyOf" not in schema
    assert branches[0]["properties"]["abstain"]["enum"] == [False]
    assert branches[0]["properties"]["answer_parts"]["type"] == "array"
    assert branches[0]["properties"]["answer_parts"]["minItems"] == 1
    assert branches[1]["properties"]["abstain"]["enum"] == [True]
    assert branches[1]["properties"]["answer_parts"]["type"] == "array"
    assert branches[1]["properties"]["answer_parts"]["maxItems"] == 0


def test_state_machine_schema_does_not_change_support_id_cardinality() -> None:
    units = build_support_units([evidence("14 calendar days")])
    old = support_unit_output_schema(units)
    new = support_unit_output_schema_state_machine(units)
    for branch in new["properties"]["result"]["anyOf"]:
        assert (
            branch["properties"]["answer_parts"]["items"]
            == old["properties"]["answer_parts"]["items"]
        )


def test_state_machine_schema_passes_local_responses_strict_shape_validation() -> None:
    units = build_support_units([evidence("14 calendar days")])
    schema = responses_strict_schema(support_unit_output_schema_state_machine(units))
    validate_responses_strict_schema_shape(schema)


def test_state_machine_provider_wrapper_maps_to_canonical_answer() -> None:
    parsed = parse_support_unit_state_machine_answer(
        json.dumps(
            {
                "result": {
                    "answer_parts": [
                        {"text": "14 days", "support_ids": ["E1.S1"]}
                    ],
                    "abstain": False,
                }
            }
        )
    )
    assert parsed.abstain is False
    assert parsed.answer_parts[0].support_ids == ["E1.S1"]


def test_state_machine_provider_wrapper_rejects_abstain_with_parts() -> None:
    with pytest.raises(ValueError, match="abstain=true"):
        parse_support_unit_state_machine_answer(
            json.dumps(
                {
                    "result": {
                        "answer_parts": [
                            {"text": "14 days", "support_ids": ["E1.S1"]}
                        ],
                        "abstain": True,
                    }
                }
            )
        )


def test_unknown_support_id_is_rejected_without_fallback() -> None:
    units = build_support_units([evidence("14 calendar days")])
    answer = parse_support_unit_answer(
        json.dumps(
            {"answer_parts": [{"text": "14 days", "support_ids": ["E9.S1"]}], "abstain": False}
        )
    )
    validation = validate_support_unit_answer(answer, units)
    assert validation.valid_parts == []
    assert validation.application_abstain is True
    assert "UNKNOWN_SUPPORT_ID" in validation.failure_codes


def test_non_visible_support_unit_is_rejected() -> None:
    block = evidence("private text")
    block.payload["model_visible"] = False
    units = build_support_units([block])
    answer = parse_support_unit_answer(
        json.dumps(
            {"answer_parts": [{"text": "private", "support_ids": ["E1.S1"]}], "abstain": False}
        )
    )
    validation = validate_support_unit_answer(answer, units)
    assert validation.application_abstain is True
    assert "HIDDEN_SUPPORT_ID" in validation.failure_codes


def test_application_resolves_only_current_request_ids() -> None:
    units = build_support_units([evidence("exact citation")])
    assert resolve_support_ids(units, ["E1.S1"])[0].text == "exact citation"
    with pytest.raises(ValueError, match="current request"):
        resolve_support_ids(units, ["E2.S1"])
