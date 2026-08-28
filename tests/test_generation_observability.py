import pytest

from app.llm.generate import stream_answer
from app.llm.observability import GenerationObservation, normalize_validator_failure_codes
from app.retrieval.hybrid_search import SearchResult


def _chunk(text: str = "Refunds take 30 days.") -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "page_number": 2,
            "paragraph_index": 0,
            "text": text,
            "source_type": "pdf",
            "source_id": "doc",
        },
    )


class _FakeProvider:
    def __init__(self, answer: str):
        self.answer = answer

    async def stream_chat(self, messages, model):
        yield self.answer


async def _collect(answer: str, *, observation=None):
    return [
        event
        async for event in stream_answer(
            "How long?",
            [_chunk()],
            _FakeProvider(answer),
            model="qwen3.5:4b",
            prompt_version="v3",
            validation_mode="strict",
            evaluation_observation=observation,
        )
    ]


def test_validator_codes_are_stable_and_preserve_multiple_failures():
    assert normalize_validator_failure_codes(
        ["unauthorized_citation", "citation_suppression", "hidden_policy_disclosure"]
    ) == ["UNAUTHORIZED_CITATION_ID", "CITATION_SUPPRESSION", "OTHER_VALIDATION_FAILURE"]


@pytest.mark.asyncio
async def test_raw_capture_is_off_by_default_and_rejected_answer_is_not_visible():
    events = await _collect("Refunds take 30 days without a citation.")
    assert not any("raw_candidate_output" in event for event in events)
    assert [event for event in events if event["type"] == "token"] == []


@pytest.mark.asyncio
async def test_opt_in_capture_keeps_raw_validated_and_user_visible_boundaries_distinct():
    observation = GenerationObservation()
    events = await _collect("Refunds take 30 days without a citation.", observation=observation)
    assert observation.raw_candidate_available is True
    assert observation.raw_candidate_output
    assert observation.validator_pass is False
    assert observation.validated_output_available is False
    assert observation.user_visible_output_available is False
    assert observation.validator_failure_codes == ["CITATION_SUPPRESSION"]
    assert [event for event in events if event["type"] == "token"] == []


@pytest.mark.asyncio
async def test_opt_in_capture_records_validated_and_user_visible_answer_separately():
    observation = GenerationObservation()
    await _collect("Refunds take 30 days [s.pdf:doc/2/0].", observation=observation)
    assert observation.raw_candidate_output == "Refunds take 30 days [s.pdf:doc/2/0]."
    assert observation.validator_pass is True
    assert observation.validated_output_available is True
    assert observation.user_visible_output_available is True
    assert observation.citations_extracted_from_raw == [("pdf", "doc", "2/0")]
    assert observation.citations_extracted_from_validated == [("pdf", "doc", "2/0")]
