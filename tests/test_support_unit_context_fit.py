"""The support-ID answer call must fit the model's context window: prompt
plus the reserved output budget may not exceed num_ctx, or the model runs out
of room mid-JSON (seen live: 4079 prompt tokens in a 4096 window left 17
output tokens, and the answer came back cut off). When it does not fit, the
lowest-ranked support units are dropped before the call. A cut-off or
unparseable answer is reported precisely and the user sees a message, never
an empty answer."""

import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.llm.structured_output import (
    _MESSAGE_FRAMING_TOKENS,
    SUPPORT_ID_MAX_OUTPUT_TOKENS,
    UNVERIFIED_ANSWER_PHRASE,
    stream_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult


def _tracer():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _block(index: int, text: str) -> SearchResult:
    return SearchResult(
        score=1.0 - index / 100,
        id=f"chunk-{index}",
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": f"doc-{index}",
            "page_number": 1,
            "paragraph_index": index,
            "tenant_id": "tenant-a",
            "authorized": True,
            "model_visible": True,
        },
    )


BLOCKS = [_block(i, f"Fact number {i} is stated here in full.") for i in range(1, 7)]


class _Provider:
    def __init__(self, raw: str, observation: dict | None = None):
        self.raw = raw
        self.last_call_observation = observation
        self.messages: list[dict] | None = None
        self.kwargs: dict = {}

    async def chat_json(self, messages, model, **kwargs):
        self.messages = messages
        self.kwargs = kwargs
        return self.raw


def _words(text: str) -> int:
    return len(text.split())


def _prompt_tokens(messages) -> int:
    """Message text plus the fixed chat-template allowance per message."""
    return sum(_words(m["content"]) + _MESSAGE_FRAMING_TOKENS for m in messages)


ANSWER = json.dumps(
    {"answer_parts": [{"text": "Fact number 1.", "support_ids": ["E1.S1"]}], "abstain": False}
)


async def _run(provider, *, num_ctx=None, count_tokens=None):
    tracer, exporter = _tracer()
    events = [
        event
        async for event in stream_support_unit_answer(
            "Which facts are stated?",
            BLOCKS,
            provider,
            model="qwen",
            validator_version="baseline",
            num_ctx=num_ctx if num_ctx is not None else 4096,
            count_tokens=count_tokens,
            tracer=tracer,
        )
    ]
    [span] = [s for s in exporter.get_finished_spans() if s.name == "generate"]
    return events, dict(span.attributes)


def _unit_ids(messages) -> list[str]:
    content = messages[-1]["content"]
    return [line.split()[2].rstrip("]") for line in content.splitlines() if "SUPPORT UNIT" in line]


# --- fitting the context window ------------------------------------------------


@pytest.mark.asyncio
async def test_everything_is_sent_when_it_fits():
    provider = _Provider(ANSWER)

    _, attrs = await _run(provider, num_ctx=100_000, count_tokens=_words)

    assert len(_unit_ids(provider.messages)) == 6
    assert attrs["generate.support_units_dropped"] == 0
    assert attrs["generate.prompt_token_estimate"] == _prompt_tokens(provider.messages)


@pytest.mark.asyncio
async def test_lowest_ranked_units_are_dropped_until_prompt_and_output_fit():
    full = _Provider(ANSWER)
    await _run(full, num_ctx=100_000, count_tokens=_words)
    full_tokens = _prompt_tokens(full.messages)
    # Room for the reserved output plus the prompt minus roughly two units.
    num_ctx = SUPPORT_ID_MAX_OUTPUT_TOKENS + full_tokens - 20

    provider = _Provider(ANSWER)
    _, attrs = await _run(provider, num_ctx=num_ctx, count_tokens=_words)

    kept = _unit_ids(provider.messages)
    assert kept == ["E1.S1", "E2.S1", "E3.S1", "E4.S1"][: len(kept)]
    assert len(kept) < 6
    assert attrs["generate.support_units_dropped"] == 6 - len(kept)
    assert attrs["generate.prompt_token_estimate"] + SUPPORT_ID_MAX_OUTPUT_TOKENS <= num_ctx


@pytest.mark.asyncio
async def test_the_top_unit_is_kept_even_if_nothing_fits():
    provider = _Provider(ANSWER)

    _, attrs = await _run(provider, num_ctx=10, count_tokens=_words)

    assert _unit_ids(provider.messages) == ["E1.S1"]
    assert attrs["generate.support_units_dropped"] == 5


@pytest.mark.asyncio
async def test_validation_only_accepts_ids_that_were_sent():
    """A dropped unit's ID must not validate, even if the model guesses it."""
    raw = json.dumps(
        {"answer_parts": [{"text": "Fact 6.", "support_ids": ["E6.S1"]}], "abstain": False}
    )
    provider = _Provider(raw)

    events, _ = await _run(provider, num_ctx=10, count_tokens=_words)

    [validation] = [e for e in events if e["type"] == "security_validation"]
    assert validation["passed"] is False or validation["abstain"] is True
    assert provider.kwargs["schema"]["properties"]["answer_parts"]["items"]["properties"][
        "support_ids"
    ]["items"]["enum"] == ["E1.S1"]


@pytest.mark.asyncio
async def test_without_a_token_counter_nothing_is_dropped():
    provider = _Provider(ANSWER)

    _, attrs = await _run(provider, num_ctx=10, count_tokens=None)

    assert len(_unit_ids(provider.messages)) == 6
    assert "generate.support_units_dropped" not in attrs


# --- truncated or invalid output ----------------------------------------------


@pytest.mark.asyncio
async def test_output_cut_off_by_the_context_limit_is_reported_as_truncated():
    provider = _Provider(
        '{"answer_parts":[{"text":"Fact number',
        observation={"done_reason": "length", "prompt_tokens": 4079, "output_tokens": 17},
    )

    events, attrs = await _run(provider)

    [validation] = [e for e in events if e["type"] == "security_validation"]
    assert validation["passed"] is False
    assert validation["validator_failure_codes"] == ["OUTPUT_TRUNCATED"]
    assert attrs["generate.done_reason"] == "length"
    assert attrs["generate.provider_prompt_tokens"] == 4079
    assert attrs["generate.provider_output_tokens"] == 17


@pytest.mark.asyncio
async def test_unparseable_output_still_shows_the_user_a_message():
    provider = _Provider("not json at all", observation={"done_reason": "stop"})

    events, _ = await _run(provider)

    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert tokens == [UNVERIFIED_ANSWER_PHRASE]
    [validation] = [e for e in events if e["type"] == "security_validation"]
    assert validation["passed"] is False
    assert validation["validator_failure_codes"] == ["TOP_LEVEL_SCHEMA_INVALID"]


@pytest.mark.asyncio
async def test_truncated_output_shows_the_message_not_the_partial_text():
    provider = _Provider(
        '{"answer_parts":[{"text":"Fact number',
        observation={"done_reason": "length"},
    )

    events, _ = await _run(provider)

    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert tokens == [UNVERIFIED_ANSWER_PHRASE]
    assert all("Fact number" not in t for t in tokens)
