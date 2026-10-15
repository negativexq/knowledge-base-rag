"""The support-ID answer stream reports how the prompt was fitted and how the
model call ended, so the Playground can explain an answer: prompt size
against its limit, units sent and dropped (metadata, before generation), and
done_reason plus token counts (the validation event, after generation)."""

import json

import pytest

from app.llm.structured_output import SUPPORT_ID_MAX_OUTPUT_TOKENS, stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

BLOCKS = [
    SearchResult(
        score=1.0 - index / 100,
        id=f"chunk-{index}",
        payload={
            "text": f"Fact number {index} is stated here in full.",
            "source_type": "filesystem",
            "source_id": f"doc-{index}",
            "page_number": 1,
            "paragraph_index": index,
            "tenant_id": "tenant-a",
        },
    )
    for index in range(1, 5)
]
ANSWER = json.dumps(
    {"answer_parts": [{"text": "Fact number 1.", "support_ids": ["E1.S1"]}], "abstain": False}
)


class _Provider:
    def __init__(self, observation):
        self.last_call_observation = observation

    async def chat_json(self, messages, model, **kwargs):
        return ANSWER


async def _events(provider, **kwargs) -> dict[str, dict]:
    events = [
        event
        async for event in stream_support_unit_answer(
            "Which facts?", BLOCKS, provider, model="qwen", validator_version="baseline", **kwargs
        )
    ]
    return {event["type"]: event for event in events}


@pytest.mark.asyncio
async def test_metadata_reports_the_prompt_fit():
    events = await _events(
        _Provider(None), num_ctx=100_000, count_tokens=lambda text: len(text.split())
    )

    fit = events["metadata"]["prompt_fit"]
    assert fit["prompt_token_limit"] == 100_000 - SUPPORT_ID_MAX_OUTPUT_TOKENS
    assert 0 < fit["prompt_tokens"] <= fit["prompt_token_limit"]
    assert fit["units_sent"] == 4
    assert fit["units_dropped"] == 0


@pytest.mark.asyncio
async def test_dropped_units_are_counted_in_the_prompt_fit():
    events = await _events(_Provider(None), num_ctx=10, count_tokens=lambda t: len(t.split()))

    fit = events["metadata"]["prompt_fit"]
    assert (fit["units_sent"], fit["units_dropped"]) == (1, 3)


@pytest.mark.asyncio
async def test_without_a_token_counter_there_is_no_prompt_fit():
    events = await _events(_Provider(None))

    assert events["metadata"]["prompt_fit"] is None


@pytest.mark.asyncio
async def test_validation_event_reports_how_generation_ended():
    observation = {"done_reason": "stop", "prompt_tokens": 2697, "output_tokens": 40}

    events = await _events(_Provider(observation))

    assert events["security_validation"]["generation"] == {
        "done_reason": "stop",
        "prompt_tokens": 2697,
        "output_tokens": 40,
    }


@pytest.mark.asyncio
async def test_generation_facts_are_null_when_the_provider_records_none():
    events = await _events(_Provider(None))

    assert events["security_validation"]["generation"] == {
        "done_reason": None,
        "prompt_tokens": None,
        "output_tokens": None,
    }
