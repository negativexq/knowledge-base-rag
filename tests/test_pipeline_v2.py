import json

import pytest

from app.evidence.section_aware import SectionAwareEvidenceBuilder, serialize_section_aware_context
from app.llm.observability import GenerationObservation
from app.llm.structured_output import (
    AnswerPart,
    EvidenceBackedAnswer,
    EvidenceBackedAnswerPart,
    EvidenceQuote,
    HardenedAnswer,
    HardenedAnswerPart,
    StructuredAnswer,
    normalize_evidence_quote,
    parse_evidence_backed_answer,
    parse_hardened_answer,
    parse_structured_answer,
    render_answer_parts,
    render_evidence_backed_answer,
    render_hardened_answer_parts,
    stream_evidence_backed_answer,
    stream_hardened_answer,
    stream_structured_answer,
    validate_evidence_backed_answer,
    validate_hardened_answer,
    validate_structured_answer,
)
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext
from app.shared.config import Settings


def _chunk(chunk_id: str, text: str, *, section: str = "Policy", tenant: str = "tenant-a"):
    return SearchResult(
        score=0.9,
        id=chunk_id,
        payload={
            "chunk_id": chunk_id,
            "source_type": "filesystem",
            "source_id": "returns",
            "document_version": "v1",
            "tenant_id": tenant,
            "page_number": 1,
            "paragraph_index": 0,
            "heading_path": [section],
            "heading_occurrence": 0,
            "text": text,
        },
    )


def test_portfolio_pipeline_defaults_and_num_ctx_are_locked():
    settings = Settings(_env_file=None)
    assert settings.rag_pipeline_v2 is True
    assert settings.support_ids_enabled is True
    assert settings.ollama_model == "qwen3.5:4b"
    assert settings.ollama_num_ctx == 4096
    assert settings.ollama_thinking is False


def test_raw_candidate_capture_is_opt_in_and_in_memory_only():
    observation = GenerationObservation()
    assert observation.raw_candidate_available is False
    assert observation.raw_candidate_output is None
    assert observation.user_visible_output_available is False


def test_v22_quote_matching_is_exact_after_safe_normalization():
    assert normalize_evidence_quote("  14\ncalendar   days  ") == "14 calendar days"
    source = _chunk("chunk", "within 14 calendar days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    result = validate_evidence_backed_answer(
        EvidenceBackedAnswer(
            [EvidenceBackedAnswerPart("14 days", [EvidenceQuote("E1", " 14\ncalendar days ")])],
            False,
        ),
        [block],
    )
    assert result.failure_codes == []
    assert result.valid_parts[0].evidence[0].quote == " 14\ncalendar days "


def test_v22_quote_validator_rejects_missing_quote_and_wrong_identity():
    source = _chunk("chunk", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    result = validate_evidence_backed_answer(
        EvidenceBackedAnswer(
            [
                EvidenceBackedAnswerPart("claim", [EvidenceQuote("E1", "30 days")]),
                EvidenceBackedAnswerPart("claim", [EvidenceQuote("E9", "14 calendar days")]),
            ],
            False,
        ),
        [block],
    )
    assert result.valid_parts == []
    assert "QUOTE_NOT_FOUND" in result.failure_codes
    assert "UNKNOWN_EVIDENCE_ID" in result.failure_codes
    assert result.application_abstain is True


def test_v22_application_abstention_is_authoritative():
    answer = parse_evidence_backed_answer(
        '{"answer_parts":[{"text":"guess","evidence":[]}],"abstain":false}'
    )
    result = validate_evidence_backed_answer(answer, [])
    assert result.application_abstain is True
    assert (
        render_evidence_backed_answer(result.valid_parts, abstain=result.application_abstain)
        == "I could not find this in the document."
    )


def test_v22_conflicting_model_abstention_contract_fails_closed():
    with pytest.raises(ValueError):
        parse_evidence_backed_answer(
            '{"answer_parts":[{"text":"claim","evidence":[]}],"abstain":true}'
        )


def test_v22_one_invalid_reference_does_not_keep_a_part_alive():
    source = _chunk("chunk", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    result = validate_evidence_backed_answer(
        EvidenceBackedAnswer(
            [
                EvidenceBackedAnswerPart(
                    "claim", [EvidenceQuote("E1", "14 calendar days"), EvidenceQuote("E9", "other")]
                )
            ],
            False,
        ),
        [block],
    )
    assert result.valid_parts == []
    assert result.application_abstain is True


def test_v22_unauthorized_id_cannot_be_remapped_by_matching_quote():
    source = _chunk("chunk", "secret")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    result = validate_evidence_backed_answer(
        EvidenceBackedAnswer(
            [EvidenceBackedAnswerPart("secret", [EvidenceQuote("E9", "secret")])], False
        ),
        [block],
    )
    assert result.valid_parts == []
    assert "UNKNOWN_EVIDENCE_ID" in result.failure_codes


@pytest.mark.asyncio
async def test_v22_stream_forces_safe_abstention_when_no_quote_survives():
    source = _chunk("chunk", "authorized but irrelevant")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    observation = GenerationObservation()
    events = [
        event
        async for event in stream_evidence_backed_answer(
            "unanswerable",
            [block],
            _StructuredProvider(
                {
                    "answer_parts": [
                        {
                            "text": "unsupported",
                            "evidence": [{"evidence_id": "E1", "quote": "missing"}],
                        }
                    ],
                    "abstain": False,
                }
            ),
            model="qwen3.5:4b",
            context_serializer=lambda chunks: "context",
            evaluation_observation=observation,
        )
    ]
    assert [event for event in events if event["type"] == "token"] == [
        {"type": "token", "content": "I could not find this in the document."}
    ]
    assert observation.model_abstention is False
    assert observation.application_forced_abstention is True
    assert observation.user_visible_output_available is True


@pytest.mark.asyncio
async def test_v22_valid_and_invalid_parts_are_separated():
    source = _chunk("chunk", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    observation = GenerationObservation()
    events = [
        event
        async for event in stream_evidence_backed_answer(
            "How long?",
            [block],
            _StructuredProvider(
                {
                    "answer_parts": [
                        {
                            "text": "14 calendar days",
                            "evidence": [{"evidence_id": "E1", "quote": "14 calendar days"}],
                        },
                        {
                            "text": "bad",
                            "evidence": [{"evidence_id": "E1", "quote": "not present"}],
                        },
                    ],
                    "abstain": False,
                }
            ),
            model="qwen3.5:4b",
            context_serializer=lambda chunks: "context",
            evaluation_observation=observation,
        )
    ]
    assert [event["content"] for event in events if event["type"] == "token"] == [
        "14 calendar days [E1]"
    ]
    assert observation.application_forced_abstention is False
    assert len(observation.validated_answer_parts) == 1
    assert len(observation.rejected_answer_parts) == 1


def test_section_builder_serialization_preserves_provenance_and_untrusted_data():
    anchor = _chunk("anchor", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(anchor, [anchor])
    context = serialize_section_aware_context([block])
    assert "section_aware_evidence" in context
    assert "anchor" in context
    assert "14 calendar days" in context
    assert "tenant-a" in context
    assert "canonical_citations" in context
    json.loads(json.dumps(context))


def test_section_key_never_crosses_source_or_tenant():
    anchor = _chunk("anchor", "anchor")
    other_source = _chunk("other", "should not be used")
    other_source.payload["source_id"] = "other"
    other_tenant = _chunk("tenant-b", "should not be used", tenant="tenant-b")
    candidates = [anchor, other_source, other_tenant]
    section = SectionAwareEvidenceBuilder._same_section(anchor, candidates)
    assert [item.id for item in section] == ["anchor"]


def test_structured_output_parser_and_renderer_do_not_invent_text():
    raw = json.dumps(
        {
            "answer_parts": [
                {
                    "text": "14 calendar days",
                    "citations": ["[s.filesystem:returns/Policy]"],
                }
            ],
            "abstain": False,
        }
    )
    parsed = parse_structured_answer(raw)
    assert render_answer_parts(parsed.answer_parts) == (
        "14 calendar days [s.filesystem:returns/Policy]"
    )
    assert "invented" not in render_answer_parts(parsed.answer_parts)


def test_structured_validator_rejects_unknown_and_unauthorized_citations():
    chunks = [_chunk("chunk", "14 calendar days")]
    valid = SectionAwareEvidenceBuilder._block(chunks[0], chunks)
    answer = StructuredAnswer(
        [
            AnswerPart("good", ["[s.filesystem:returns/Policy]"]),
            AnswerPart("bad", ["[s.filesystem:other/Policy]"]),
        ],
        False,
    )
    result = validate_structured_answer(answer, [valid])
    assert len(result.valid_parts) == 1
    assert result.rejected_parts[0]["failure_codes"] == ["UNKNOWN_CITATION_ID"]


class _StructuredProvider:
    def __init__(self, value):
        self.value = value

    async def chat_json(self, messages, *, model, think, temperature, schema, num_ctx):
        return json.dumps(self.value, ensure_ascii=False)


@pytest.mark.asyncio
async def test_claim_level_validation_preserves_valid_parts_but_not_invalid_parts():
    chunk = _chunk("chunk", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(chunk, [chunk])
    observation = GenerationObservation()
    events = [
        event
        async for event in stream_structured_answer(
            "How long?",
            [block],
            _StructuredProvider(
                {
                    "answer_parts": [
                        {
                            "text": "14 calendar days",
                            "citations": ["[s.filesystem:returns/Policy]"],
                        },
                        {"text": "unsupported", "citations": ["[s.filesystem:other/Policy]"]},
                    ],
                    "abstain": False,
                }
            ),
            model="qwen3.5:4b",
            context_serializer=lambda chunks: "context",
            evaluation_observation=observation,
        )
    ]
    tokens = [event["content"] for event in events if event["type"] == "token"]
    assert tokens == ["14 calendar days [s.filesystem:returns/Policy]"]
    assert observation.validator_pass is False
    assert observation.user_visible_output_available is True


@pytest.mark.asyncio
async def test_structured_top_level_schema_failure_remains_fail_closed():
    observation = GenerationObservation()
    events = [
        event
        async for event in stream_structured_answer(
            "How long?",
            [_chunk("chunk", "14 calendar days")],
            _StructuredProvider({"not_answer_parts": []}),
            model="qwen3.5:4b",
            context_serializer=lambda chunks: "context",
            evaluation_observation=observation,
        )
    ]
    assert not [event for event in events if event["type"] == "token"]
    assert observation.validator_pass is False
    assert observation.user_visible_output_available is False


def test_hardened_evidence_ids_are_local_and_resolve_to_provenance():
    source = _chunk("chunk", "14 days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    block.payload["evidence_id"] = "E1"
    result = validate_hardened_answer(
        HardenedAnswer([HardenedAnswerPart("14 days", ["E1"])], False), [block]
    )
    assert result.failure_codes == []
    assert render_hardened_answer_parts(result.valid_parts) == "14 days [E1]"


def test_hardened_unknown_evidence_rejects_only_the_bad_part():
    source = _chunk("chunk", "14 days")
    block = SectionAwareEvidenceBuilder._block(source, [source])
    answer = HardenedAnswer(
        [HardenedAnswerPart("14 days", ["E1"]), HardenedAnswerPart("other", ["E9"])], False
    )
    result = validate_hardened_answer(answer, [block])
    assert [part.text for part in result.valid_parts] == ["14 days"]
    assert result.rejected_parts[0]["failure_codes"] == ["UNKNOWN_EVIDENCE_ID"]


def test_hardened_parser_allows_only_conservative_json_fence_and_abstention():
    parsed = parse_hardened_answer(
        '```json\n{"answer_parts":[],"abstain":true,' '"reason_code":"INSUFFICIENT_EVIDENCE"}\n```'
    )
    assert parsed.abstain is True
    invalid = parse_hardened_answer('{"answer_parts":[],"abstain":false}')
    assert "ABSTAIN_CONTRACT_INVALID" in validate_hardened_answer(invalid, []).failure_codes


@pytest.mark.asyncio
async def test_hardened_stream_exposes_raw_and_keeps_invalid_part_hidden():
    chunk = _chunk("chunk", "14 calendar days")
    block = SectionAwareEvidenceBuilder._block(chunk, [chunk])
    observation = GenerationObservation()
    events = [
        event
        async for event in stream_hardened_answer(
            "How long?",
            [block],
            _StructuredProvider(
                {
                    "answer_parts": [
                        {"text": "14 calendar days", "evidence_ids": ["E1"]},
                        {"text": "bad", "evidence_ids": ["E9"]},
                    ],
                    "abstain": False,
                }
            ),
            model="qwen3.5:4b",
            context_serializer=lambda chunks: "context",
            evaluation_observation=observation,
        )
    ]
    assert [event["content"] for event in events if event["type"] == "token"] == [
        "14 calendar days [E1]"
    ]
    assert observation.raw_candidate_available is True
    assert observation.validator_pass is False
    assert observation.user_visible_output_available is True


@pytest.mark.asyncio
async def test_builder_calls_storage_only_for_same_authorized_boundary(monkeypatch):
    calls = []

    class FakeClient:
        def scroll(self, **kwargs):
            calls.append(kwargs)
            return [], None

    builder = SectionAwareEvidenceBuilder(FakeClient(), "collection")
    result = await builder.build([_chunk("anchor", "text")], RetrievalContext("tenant-a"))
    assert result.blocks
    assert calls[0]["collection_name"] == "collection"
    filter_keys = [condition.key for condition in calls[0]["scroll_filter"].must]
    assert "tenant_id" in filter_keys
