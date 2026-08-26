import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.llm.generate import stream_answer
from app.retrieval.hybrid_search import SearchResult


def _local_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _chunk(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_type": "pdf",
            "source_id": "doc",
        },
    )


class _FakeOllama:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens
        self.received_messages = None
        self.received_model = None

    async def stream_chat(self, messages, model):
        self.received_messages = messages
        self.received_model = model
        for token in self._tokens:
            yield token


async def _collect(
    query,
    chunks,
    ollama,
    model="qwen",
    prompt_version="v1",
    validation_mode="fast",
    tracer=None,
):
    return [
        event
        async for event in stream_answer(
            query,
            chunks,
            ollama,
            model=model,
            prompt_version=prompt_version,
            validation_mode=validation_mode,
            tracer=tracer,
        )
    ]


@pytest.mark.asyncio
async def test_stream_answer_first_event_is_metadata_with_prompt_version():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    events = await _collect("How long?", chunks, ollama, prompt_version="v2")

    assert events[0]["type"] == "metadata"
    assert events[0]["prompt_version"] == "v2"
    assert "trace_id" in events[0]


@pytest.mark.asyncio
async def test_stream_answer_metadata_trace_id_matches_the_generate_span():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])
    tracer, exporter = _local_tracer_with_exporter()

    events = await _collect("How long?", chunks, ollama, tracer=tracer)

    generate_span = next(s for s in exporter.get_finished_spans() if s.name == "generate")
    expected_trace_id = format(generate_span.context.trace_id, "032x")
    assert events[0]["trace_id"] == expected_trace_id
    assert len(events[0]["trace_id"]) == 32


@pytest.mark.asyncio
async def test_stream_answer_yields_token_events_in_order():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds ", "take ", "30 days ", "[s.pdf:doc/2/0]."])

    events = await _collect("How long?", chunks, ollama)

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["content"] for e in token_events] == [
        "Refunds ",
        "take ",
        "30 days ",
        "[s.pdf:doc/2/0].",
    ]


@pytest.mark.asyncio
async def test_stream_answer_emits_grounding_event_last():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/2/0]."])

    events = await _collect("How long?", chunks, ollama)

    assert events[-1]["type"] == "grounding"
    assert events[-1]["grounded"] is True
    assert events[-1]["citations_found"] == [("pdf", "doc", "2/0")]


@pytest.mark.asyncio
async def test_stream_answer_grounding_event_flags_fabricated_citation():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/99/0]."])  # 99 was never in context

    events = await _collect("How long?", chunks, ollama)

    grounding_event = events[-1]
    assert grounding_event["grounded"] is False
    assert grounding_event["has_citations"] is True
    assert grounding_event["ungrounded_citations"] == [("pdf", "doc", "99/0")]


@pytest.mark.asyncio
async def test_stream_answer_grounding_event_is_not_grounded_with_zero_citations():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["I could not find this in the document."])

    events = await _collect("How long?", chunks, ollama)

    grounding_event = events[-1]
    assert grounding_event["grounded"] is False
    assert grounding_event["has_citations"] is False
    assert grounding_event["citations_found"] == []


@pytest.mark.asyncio
async def test_stream_answer_passes_built_messages_to_ollama():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    await _collect("How long?", chunks, ollama, model="qwen")

    roles = [m["role"] for m in ollama.received_messages]
    assert roles == ["system", "user"]
    assert "How long?" in ollama.received_messages[1]["content"]
    assert ollama.received_model == "qwen"


@pytest.mark.asyncio
async def test_stream_answer_uses_requested_prompt_version_content():
    from app.llm.prompt import load_system_prompt

    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["ok"])

    await _collect("How long?", chunks, ollama, prompt_version="v2")

    assert ollama.received_messages[0]["content"] == load_system_prompt("v2")


@pytest.mark.asyncio
async def test_stream_answer_creates_generate_span_with_attributes():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/2/0]."])
    tracer, exporter = _local_tracer_with_exporter()

    await _collect("How long?", chunks, ollama, model="qwen", prompt_version="v1", tracer=tracer)

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "generate" in spans
    attrs = spans["generate"].attributes
    assert attrs["generate.model"] == "qwen"
    assert attrs["generate.prompt_version"] == "v1"
    assert attrs["generate.context_chunk_count"] == 1
    assert attrs["generate.token_count"] == 1
    assert attrs["generate.grounded"] is True
    assert attrs["generate.citation_count"] == 1


@pytest.mark.asyncio
async def test_stream_answer_generate_span_does_not_contain_full_answer_text():
    # high-cardinality data (full chunk text / full generated answer) must
    # never end up as a span attribute.
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/2/0]."])
    tracer, exporter = _local_tracer_with_exporter()

    await _collect("How long?", chunks, ollama, tracer=tracer)

    generate_span = next(s for s in exporter.get_finished_spans() if s.name == "generate")
    for value in generate_span.attributes.values():
        assert "Refunds take 30 days" not in str(value)


@pytest.mark.asyncio
async def test_v3_fast_reports_untrusted_context_and_output_validation():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/2/0]."])

    events = await _collect("How long?", chunks, ollama, prompt_version="v3")

    assert events[0]["untrusted_context_enabled"] is True
    security = next(event for event in events if event["type"] == "security_validation")
    assert security["passed"] is True
    assert any("retrieved_context" in message["content"] for message in ollama.received_messages)


@pytest.mark.asyncio
async def test_v3_default_mode_is_strict_and_withholds_before_token_release():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days without a citation."])

    events = [
        event
        async for event in stream_answer(
            "How long?", chunks, ollama, model="qwen", prompt_version="v3"
        )
    ]

    assert [event for event in events if event["type"] == "token"] == []
    assert (
        next(event for event in events if event["type"] == "security_validation")["passed"]
        is False
    )
    assert any(event["type"] == "error" for event in events)


@pytest.mark.asyncio
async def test_v3_strict_withholds_answer_when_citation_policy_fails():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days without a citation."])

    events = await _collect(
        "How long?", chunks, ollama, prompt_version="v3", validation_mode="strict"
    )

    assert [event for event in events if event["type"] == "token"] == []
    security = next(event for event in events if event["type"] == "security_validation")
    assert security["passed"] is False
    assert any(event["type"] == "error" for event in events)


@pytest.mark.asyncio
async def test_v3_strict_withholds_unauthorized_citation_before_token_release():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.filesystem:other-secret/1/0]."])

    events = await _collect(
        "How long?", chunks, ollama, prompt_version="v3", validation_mode="strict"
    )

    assert [event for event in events if event["type"] == "token"] == []
    security = next(event for event in events if event["type"] == "security_validation")
    assert security["passed"] is False
    assert "unauthorized_citation" in security["violations"]


@pytest.mark.asyncio
async def test_v3_fast_violation_is_reported_after_tokens_may_have_streamed():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.filesystem:other-secret/1/0]."])

    events = await _collect(
        "How long?", chunks, ollama, prompt_version="v3", validation_mode="fast"
    )

    assert [event["content"] for event in events if event["type"] == "token"]
    security = next(event for event in events if event["type"] == "security_validation")
    assert security["passed"] is False
    assert "unauthorized_citation" in security["violations"]


@pytest.mark.asyncio
async def test_v3_strict_releases_only_after_policy_passes():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/2/0]."])

    events = await _collect(
        "How long?", chunks, ollama, prompt_version="v3", validation_mode="strict"
    )

    assert [event["content"] for event in events if event["type"] == "token"] == [
        "Refunds take 30 days [s.pdf:doc/2/0]."
    ]
    assert (
        next(event for event in events if event["type"] == "security_validation")["passed"]
        is True
    )
