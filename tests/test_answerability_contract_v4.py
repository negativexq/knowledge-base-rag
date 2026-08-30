import json

from app.evidence.support_relevance import audit_support_relevance
from app.evidence.support_units import SupportUnit
from app.llm.openai_client import responses_strict_schema, validate_responses_strict_schema_shape
from app.llm.structured_output import (
    ANSWERABILITY_OUTPUT_INSTRUCTIONS,
    parse_support_unit_answerability,
    support_unit_answerability_schema,
    validate_answerability_output,
)
from scripts.run_techqa_answerability_contract_v4 import preflight_allows_official


def unit(support_id: str, text: str) -> SupportUnit:
    return SupportUnit(
        support_unit_id=support_id,
        parent_evidence_block_id="block-1",
        evidence_id=support_id.split(".")[0],
        source_id="source-1",
        document_version="v1",
        section_id="section-1",
        contributing_chunk_ids=("chunk-1",),
        tenant_id="tenant-1",
        authorized=True,
        model_visible=True,
        text=text,
    )


def test_discriminated_schema_accepts_only_answer_or_abstain_payloads() -> None:
    schema = support_unit_answerability_schema([unit("E1.S1", "Supported text")])
    sent = responses_strict_schema(schema)
    validate_responses_strict_schema_shape(sent)
    branches = sent["properties"]["result"]["anyOf"]
    answer, abstain = branches
    assert set(answer["properties"]) == {"status", "answer_parts"}
    assert answer["properties"]["status"]["enum"] == ["ANSWER"]
    assert answer["properties"]["answer_parts"]["minItems"] == 1
    assert answer["properties"]["answer_parts"]["items"]["properties"]["support_ids"][
        "minItems"
    ] == 1
    assert set(abstain["properties"]) == {"status", "reason_code"}
    assert abstain["properties"]["status"]["enum"] == ["ABSTAIN"]


def test_prompt_has_no_literal_search_phrase_blocklist() -> None:
    assert "I could not find this in the document" not in ANSWERABILITY_OUTPUT_INSTRUCTIONS
    assert "Those outcomes are expressed only by ABSTAIN" in ANSWERABILITY_OUTPUT_INSTRUCTIONS


def test_answerability_parser_maps_discriminated_states() -> None:
    answer = parse_support_unit_answerability(
        json.dumps(
            {
                "result": {
                    "status": "ANSWER",
                    "answer_parts": [{"text": "Supported answer", "support_ids": ["E1.S1"]}],
                }
            }
        )
    )
    abstain = parse_support_unit_answerability(
        json.dumps(
            {
                "result": {
                    "status": "ABSTAIN",
                    "reason_code": "EVIDENCE_INSUFFICIENT",
                }
            }
        )
    )
    assert answer.abstain is False and len(answer.answer_parts) == 1
    assert abstain.abstain is True and abstain.reason_code == "EVIDENCE_INSUFFICIENT"


def test_unsupported_search_process_statement_fails_without_blocklist() -> None:
    audit = audit_support_relevance(
        "I could not find this in the document.",
        ["WebSphere Application Server supports Java 8 and later."],
        coverage_threshold=0.60,
    )
    assert audit["supported"] is False
    assert audit["failure_codes"] == ["SUPPORT_RELEVANCE_BELOW_THRESHOLD"]
    assert audit["blocklist_used"] is False


def test_supported_negative_claim_passes_from_evidence_not_phrase_filter() -> None:
    audit = audit_support_relevance(
        "The documentation states that there is no known ODR memory issue.",
        ["There is no known ODR memory issue documented for this release."],
        coverage_threshold=0.60,
    )
    assert audit["supported"] is True
    assert audit["blocklist_used"] is False


def test_critical_value_binding_remains_mandatory_inside_relevance_gate() -> None:
    audit = audit_support_relevance(
        "Hold the power button for 50 seconds.",
        ["Hold the power button for 5 seconds."],
        coverage_threshold=0.60,
    )
    assert audit["supported"] is False
    assert "CRITICAL_VALUE_DIRECT_CONFLICT" in audit["failure_codes"]


def test_all_unsupported_parts_create_forced_abstain() -> None:
    parsed = parse_support_unit_answerability(
        json.dumps(
            {
                "result": {
                    "status": "ANSWER",
                    "answer_parts": [
                        {
                            "text": "I could not find this in the document.",
                            "support_ids": ["E1.S1"],
                        }
                    ],
                }
            }
        )
    )
    result = validate_answerability_output(
        parsed,
        [unit("E1.S1", "WebSphere Application Server supports Java 8 and later.")],
        coverage_threshold=0.60,
    )
    assert result.forced_abstain is True
    assert result.output_reason_code == "EVIDENCE_INSUFFICIENT"
    assert result.valid_parts == []


def test_matching_raw_complete_preflight_is_required() -> None:
    payload = {
        "schema_acceptance": True,
        "result": {"state": "RAW_COMPLETE", "schema_hash": "schema-v4"},
    }
    assert preflight_allows_official(payload, schema_hash="schema-v4") is True
    assert preflight_allows_official(payload, schema_hash="stale") is False
