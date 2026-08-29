import json

import pytest

from app.evidence.support_units import (
    build_support_units,
    resolve_support_ids,
    serialize_support_units,
)
from app.llm.structured_output import (
    parse_support_unit_answer,
    support_unit_output_schema,
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
