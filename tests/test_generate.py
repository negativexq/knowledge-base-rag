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


async def _collect(query, chunks, ollama, model="qwen", prompt_version="v1", tracer=None):
    return [
        event
        async for event in stream_answer(
            query, chunks, ollama, model=model, prompt_version=prompt_version, tracer=tracer
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
    assert events[-1]["citations_found"] == [("pdf", "doc", 2, 0)]


@pytest.mark.asyncio
async def test_stream_answer_grounding_event_flags_fabricated_citation():
    chunks = [_chunk(2, 0, "Refunds take 30 days.")]
    ollama = _FakeOllama(["Refunds take 30 days [s.pdf:doc/99/0]."])  # 99 was never in context

    events = await _collect("How long?", chunks, ollama)

    grounding_event = events[-1]
    assert grounding_event["grounded"] is False
    assert grounding_event["ungrounded_citations"] == [("pdf", "doc", 99, 0)]


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
