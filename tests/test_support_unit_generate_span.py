"""The production answer path (support-ID contract, settings.support_ids_enabled)
must open the same "generate" span as the other generation paths: it carries
LLM latency in Jaeger, the GenAI attributes Langfuse maps onto a generation,
and the trace_id the Playground's trace tab looks up."""

import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

ANSWER_TEXT = "The limit is 120 requests per minute."
QUESTION = "What is the request limit for the public API?"


def _tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def _block() -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "text": ANSWER_TEXT,
            "source_type": "filesystem",
            "source_id": "fixture",
            "page_number": 1,
            "paragraph_index": 0,
            "tenant_id": "tenant-a",
            "authorized": True,
            "model_visible": True,
        },
    )


class _Provider:
    def __init__(self, payload=None, error: Exception | None = None):
        self._payload = payload
        self._error = error

    async def chat_json(self, messages, **kwargs):
        if self._error is not None:
            raise self._error
        return json.dumps(self._payload)


ANSWER = {"answer_parts": [{"text": ANSWER_TEXT, "support_ids": ["E1.S1"]}], "abstain": False}
ABSTAIN = {"answer_parts": [], "abstain": True, "reason_code": "INSUFFICIENT_EVIDENCE"}


async def _collect(provider, tracer, model="qwen"):
    return [
        event
        async for event in stream_support_unit_answer(
            QUESTION,
            [_block()],
            provider,
            model=model,
            validator_version="baseline",
            tracer=tracer,
        )
    ]


def _generate_span(exporter):
    [span] = [s for s in exporter.get_finished_spans() if s.name == "generate"]
    return span


@pytest.mark.asyncio
async def test_support_id_path_opens_a_generate_span_marked_as_llm_generation():
    tracer, exporter = _tracer_with_exporter()

    await _collect(_Provider(ANSWER), tracer, model="qwen3.5:4b")

    attrs = _generate_span(exporter).attributes
    assert attrs["generate.model"] == "qwen3.5:4b"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "qwen3.5:4b"
    assert attrs["langfuse.observation.type"] == "generation"
    assert attrs["pipeline.version"]
    assert attrs["generate.context_chunk_count"] == 1


@pytest.mark.asyncio
async def test_metadata_trace_id_matches_the_generate_span():
    tracer, exporter = _tracer_with_exporter()

    events = await _collect(_Provider(ANSWER), tracer)

    metadata = events[0]
    assert metadata["type"] == "metadata"
    assert metadata["trace_id"] == format(_generate_span(exporter).context.trace_id, "032x")


@pytest.mark.asyncio
async def test_generate_span_nests_under_the_callers_span():
    tracer, exporter = _tracer_with_exporter()

    with tracer.start_as_current_span("chat_request") as parent:
        await _collect(_Provider(ANSWER), tracer)

    span = _generate_span(exporter)
    assert span.parent is not None
    assert span.parent.span_id == parent.get_span_context().span_id


@pytest.mark.asyncio
async def test_span_records_the_answer_outcome():
    tracer, exporter = _tracer_with_exporter()

    await _collect(_Provider(ANSWER), tracer)

    attrs = _generate_span(exporter).attributes
    assert attrs["security.output_policy_passed"] is True
    assert attrs["generate.abstain"] is False
    assert attrs["generate.application_forced_abstention"] is False


@pytest.mark.asyncio
async def test_span_records_a_model_abstention():
    tracer, exporter = _tracer_with_exporter()

    await _collect(_Provider(ABSTAIN), tracer)

    attrs = _generate_span(exporter).attributes
    # A clean abstention is a valid, visible "not found" answer.
    assert attrs["security.output_policy_passed"] is True
    assert attrs["generate.abstain"] is True
    assert attrs["generate.application_forced_abstention"] is False


@pytest.mark.asyncio
async def test_span_records_a_forced_abstention_with_failure_codes():
    tracer, exporter = _tracer_with_exporter()
    unknown_id = {
        "answer_parts": [{"text": ANSWER_TEXT, "support_ids": ["E9.S9"]}],
        "abstain": False,
    }

    await _collect(_Provider(unknown_id), tracer)

    attrs = _generate_span(exporter).attributes
    assert attrs["generate.abstain"] is True
    assert attrs["generate.application_forced_abstention"] is True
    assert attrs["generate.validator_failure_codes"]


@pytest.mark.asyncio
async def test_span_never_carries_question_or_answer_text():
    tracer, exporter = _tracer_with_exporter()

    await _collect(_Provider(ANSWER), tracer)

    rendered = repr(dict(_generate_span(exporter).attributes))
    assert "120 requests" not in rendered
    assert "request limit" not in rendered
    assert "gen_ai.prompt" not in rendered
    assert "gen_ai.completion" not in rendered


@pytest.mark.asyncio
async def test_provider_failure_ends_the_span_as_an_error_and_propagates():
    tracer, exporter = _tracer_with_exporter()

    with pytest.raises(RuntimeError):
        await _collect(_Provider(error=RuntimeError("provider down")), tracer)

    assert _generate_span(exporter).status.status_code is StatusCode.ERROR
