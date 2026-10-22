import asyncio
import json
from contextlib import aclosing

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage as ModelUsage
from pydantic_ai.usage import RunUsage, UsageLimits

from app.api.chat import ChatDependencies, _sse_event_stream
from app.llm import agent_observability as obs
from app.llm.agentic import AgentDependencies, EvidenceLedger, ToolProvider, run_agent
from app.llm.query_rewrite import ChatTurn, rewrite_query
from app.llm.structured_output import stream_support_unit_answer
from app.research.traces import TraceStore
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext


@pytest.fixture
def tracing(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.research")
    monkeypatch.setattr(obs, "get_tracer", lambda _: tracer)
    monkeypatch.setattr("app.llm.structured_output.get_tracer", lambda _: tracer)
    monkeypatch.setattr("app.llm.query_rewrite.get_tracer", lambda _: tracer)
    yield tracer, exporter
    provider.shutdown()


def block():
    return SearchResult(
        id="a",
        score=1,
        payload={
            "text": "The service uses TLS.",
            "source_type": "filesystem",
            "source_id": "manual",
            "tenant_id": "a",
            "document_version": "v1",
            "page_number": 1,
            "paragraph_index": 0,
        },
    )


def output(info, *, support="E1.S1", clarification=None):
    data = {
        "abstain": bool(clarification),
        "answer_parts": []
        if clarification
        else [{"text": "The service uses TLS.", "support_ids": [support]}],
    }
    if clarification:
        data["clarification"] = clarification
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, data)],
        usage=ModelUsage(input_tokens=100, output_tokens=20, cache_read_tokens=10),
    )


def chat_dependencies(model, *, timeout=5, retrieve=None):
    async def search(query, context, report):
        if retrieve is not None and query == "details":
            return await retrieve()
        return [block()]

    async def stream(query, blocks, retrieve=None):
        async def generator(query, initial):
            ledger = EvidenceLedger(lambda t: len(t.split()), 1000)
            ledger.add(initial)
            return await run_agent(
                FunctionModel(model, model_name="fake"),
                AgentDependencies(query, ledger, retrieve=retrieve),
                timeout_seconds=timeout,
            )

        async with aclosing(
            stream_support_unit_answer(
                query, blocks, None, model="fake", candidate_generator=generator
            )
        ) as events:
            async for event in events:
                yield event

    return ChatDependencies(
        search_fn=search,
        stream_fn=stream,
        agentic_rag_enabled=True,
        pipeline_version="pipeline_agentic_v1",
    )


@pytest.mark.asyncio
async def test_full_request_has_linked_model_tool_retry_and_release_spans(tracing, tmp_path):
    tracer, exporter = tracing
    count = 0

    def model(messages, info):
        nonlocal count
        count += 1
        if count == 1:
            return ModelResponse(
                parts=[ToolCallPart("search", {"query": "details"})],
                usage=ModelUsage(input_tokens=100, output_tokens=20, cache_read_tokens=10),
            )
        return output(info, support="E99.S1" if count == 2 else "E1.S1")

    tracker = obs.RequestUsage(
        {
            "fake": obs.ModelPrice(
                input_per_million=1, output_per_million=2, cached_input_per_million=0.1
            )
        }
    )
    store = TraceStore(tmp_path / "traces.db")
    events = [
        e
        async for e in _sse_event_stream(
            "PRIVATE QUESTION",
            chat_dependencies(model),
            RetrievalContext("a"),
            tracer=tracer,
            request_usage=tracker,
            trace_store=store,
            user_id="user",
        )
    ]
    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert names.count("llm.request") == 3
    assert "tool.search" in names and "agent.retry" in names and "answer.validate" in names
    root = next(s for s in spans if s.name == "chat_request")
    trace_id = format(root.context.trace_id, "032x")
    assert all(s.context.trace_id == root.context.trace_id for s in spans)
    assert all(s.parent is not None for s in spans if s.name != "chat_request")
    record = store.get(trace_id, "a", "user")
    assert record["outcome"] == "answered"
    assert record["usage"]["llm_requests"] == 3
    assert record["usage"]["input_tokens"] == 300
    assert record["usage"]["tool_calls"] == 1
    assert record["usage"]["retries"] == 1
    assert record["usage"]["cost_usd"] == pytest.approx(0.000393)
    assert root.attributes["langfuse.observation.type"] == "span"
    generate = next(s for s in spans if s.name == "generate")
    assert "gen_ai.operation.name" not in generate.attributes  # no double billing
    assert "PRIVATE QUESTION" not in repr([(s.attributes, s.events) for s in spans])
    assert json.loads(events[0].split("data: ")[1])["trace_id"] == trace_id
    assert store.get(trace_id, "b", "user") is None
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["failure", "timeout", "clarification"])
async def test_non_answer_outcomes_keep_trace_metadata_without_sensitive_errors(
    tracing, tmp_path, mode
):
    tracer, exporter = tracing

    async def model(messages, info):
        if mode == "failure":
            raise RuntimeError("SECRET provider request and credentials")
        if mode == "timeout":
            await asyncio.sleep(5)
        return output(info, clarification={"question": "Which platform?", "options": []})

    store = TraceStore(tmp_path / "traces.db")
    events = [
        e
        async for e in _sse_event_stream(
            "Question",
            chat_dependencies(model, timeout=0.02),
            RetrievalContext("a"),
            tracer=tracer,
            trace_store=store,
            user_id="user",
        )
    ]
    root = next(s for s in exporter.get_finished_spans() if s.name == "chat_request")
    expected = {"failure": "failed", "timeout": "timeout", "clarification": "clarification"}[mode]
    assert root.attributes["research.outcome"] == expected
    record = store.list("a", "user")[0]
    assert record["outcome"] == expected
    assert record["usage"]["cost_usd"] is None
    assert "SECRET" not in repr([(s.attributes, s.events) for s in exporter.get_finished_spans()])
    assert "event: metadata" in events[0]
    if mode == "clarification":
        assert any("event: clarification" in e for e in events)
        assert not any('"token"' in e for e in events)
    store.close()


@pytest.mark.asyncio
async def test_cancellation_closes_spans_and_finishes_trace_index(tracing, tmp_path):
    tracer, exporter = tracing

    def model(messages, info):
        return ModelResponse(parts=[ToolCallPart("search", {"query": "details"})])

    async def waiting():
        await asyncio.Event().wait()

    store = TraceStore(tmp_path / "traces.db")
    stream = _sse_event_stream(
        "Question",
        chat_dependencies(model, retrieve=waiting),
        RetrievalContext("a"),
        tracer=tracer,
        trace_store=store,
        user_id="user",
    )
    # The retrieval stage arrives first; wait for the agent's own search.
    while '"operation": "search", "status": "running"' not in await anext(stream):
        pass
    await stream.aclose()
    assert store.list("a", "user")[0]["outcome"] == "cancelled"
    assert (
        next(s for s in exporter.get_finished_spans() if s.name == "tool.search").attributes[
            "research.outcome"
        ]
        == "cancelled"
    )
    store.close()


@pytest.mark.asyncio
async def test_rewrite_provider_positional_model_is_traced_and_counted(tracing):
    class Provider:
        last_call_observation = None

        async def chat_json(self, messages, **kwargs):
            assert kwargs["model"] == "fake"
            self.last_call_observation = {"usage": {"input_tokens": 40, "output_tokens": 10}}
            return '{"standalone_question":"Install the Linux service"}'

    usage = obs.RequestUsage()
    with obs.usage_scope(usage):
        provider = ToolProvider(Provider(), RunUsage(), UsageLimits(), role="query_rewrite")
        result = await rewrite_query(
            provider,
            "How to install it?",
            [ChatTurn(role="user", content="Linux service")],
            model="fake",
            timeout_seconds=1,
            max_chars=100,
        )
    assert result.outcome == "REWRITTEN"
    assert usage.requests == 1 and usage.input_tokens == 40
    spans = tracing[1].get_finished_spans()
    assert (
        next(s for s in spans if s.name == "llm.request").attributes["research.model_role"]
        == "query_rewrite"
    )
    assert (
        "gen_ai.operation.name"
        not in next(s for s in spans if s.name == "rewrite_query").attributes
    )


def test_unknown_usage_and_missing_cache_prices_never_report_zero_cost(tracing):
    tracer, _ = tracing
    prices = obs.load_prices('{"m":{"input_per_million":1,"output_per_million":2}}')
    usage = obs.RequestUsage(prices)
    with tracer.start_as_current_span("missing-cache-price") as span:
        usage.record(
            span, provider="p", model="m", input_tokens=10, output_tokens=5, cached_tokens=3
        )
    assert usage.snapshot()["cost_usd"] is None
    assert not usage.snapshot()["cost_complete"]
    with tracer.start_as_current_span("missing-usage") as span:
        usage.record(span, provider="p", model="m", input_tokens=None, output_tokens=None)
    assert not usage.snapshot()["usage_complete"]


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"m":{"input_per_million":-1,"output_per_million":2}}',
        '{"m":{"input_per_million":NaN,"output_per_million":2}}',
    ],
)
def test_pricing_configuration_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        obs.load_prices(raw)


@pytest.mark.parametrize("provider_name", ["openai", "ollama"])
async def test_provider_observations_are_isolated_between_concurrent_requests(provider_name):
    from types import SimpleNamespace

    from app.llm.ollama_client import OllamaClient
    from app.llm.openai_client import OpenAIGeneratorClient

    if provider_name == "openai":
        provider = OpenAIGeneratorClient(api_key="test", sdk_client=SimpleNamespace())
    else:
        provider = OllamaClient(base_url="http://unused.invalid")
    ready = asyncio.Event()
    release = asyncio.Event()

    async def first():
        provider.last_call_observation = {"prompt_tokens": 11}
        ready.set()
        await release.wait()
        return provider.last_call_observation

    async def second():
        await ready.wait()
        provider.last_call_observation = {"prompt_tokens": 99}
        release.set()
        return provider.last_call_observation

    one, two = await asyncio.gather(first(), second())
    assert one == {"prompt_tokens": 11}
    assert two == {"prompt_tokens": 99}
    assert provider.last_call_observation is None
    if provider_name == "ollama":
        await provider.aclose()


def test_chat_trace_identity_cannot_be_selected_by_incoming_context(tracing):
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    from app.research.traces import request_trace

    tracer, exporter = tracing
    incoming = SpanContext(trace_id=123, span_id=456, is_remote=True, trace_flags=TraceFlags(1))
    with trace.use_span(NonRecordingSpan(incoming)):
        with request_trace(
            tracer=tracer,
            tenant="a",
            user="u",
            usage=obs.RequestUsage(),
            store=None,
            pipeline="agentic",
        ) as span:
            assert span.get_span_context().trace_id != incoming.trace_id
            with obs.operation("agent.run"):
                pass
    root = next(s for s in exporter.get_finished_spans() if s.name == "chat_request")
    child = next(s for s in exporter.get_finished_spans() if s.name == "agent.run")
    assert child.context.trace_id == root.context.trace_id
    assert root.parent is None and root.links[0].context == incoming
