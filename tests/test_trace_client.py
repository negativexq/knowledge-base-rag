import httpx

from app.shared.trace_client import SpanSummary, fetch_trace_spans

_TRACE_ID = "6f3af6e0560f191c39f54f5e2e0ebd17"


def _jaeger_response(spans: list[dict]) -> dict:
    return {"data": [{"traceID": _TRACE_ID, "spans": spans}]}


def _span(name: str, start_time_us: int, duration_us: int) -> dict:
    return {"operationName": name, "startTime": start_time_us, "duration": duration_us}


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://jaeger.test")


def test_fetch_trace_spans_parses_and_sorts_by_start_time():
    spans = [
        _span("generate", 200, 5000),
        _span("embed_query", 100, 2000),
        _span("rerank", 150, 1000),
        _span("chat_request", 90, 6000),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_jaeger_response(spans))

    result = fetch_trace_spans(_TRACE_ID, client=_client_for(handler))

    assert result == [
        SpanSummary(name="chat_request", duration_ms=6.0, start_time_us=90),
        SpanSummary(name="embed_query", duration_ms=2.0, start_time_us=100),
        SpanSummary(name="rerank", duration_ms=1.0, start_time_us=150),
        SpanSummary(name="generate", duration_ms=5.0, start_time_us=200),
    ]


def test_fetch_trace_spans_retries_until_jaeger_has_indexed_the_trace():
    """Jaeger's OTLP ingestion is async (BatchSpanProcessor) — a trace may
    not be searchable immediately after the request that produced it
    finishes. See docs/PLANNING.md Sprint 12 closing note.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(200, json=_jaeger_response([]))
        return httpx.Response(200, json=_jaeger_response([_span("chat_request", 100, 1000)]))

    result = fetch_trace_spans(
        _TRACE_ID, client=_client_for(handler), max_attempts=5, retry_delay_seconds=0
    )

    assert call_count == 3
    assert result == [SpanSummary(name="chat_request", duration_ms=1.0, start_time_us=100)]


def test_fetch_trace_spans_keeps_retrying_when_root_span_is_missing():
    """Real bug found in Sprint 12's browser verification: BatchSpanProcessor
    exports spans in batches, not one at a time — some child spans (e.g.
    embed_query, rerank) can appear in Jaeger before the LAST-closing span
    (the "chat_request" root, or "generate" which finishes right before it)
    has been flushed. Treating "some spans exist" as "done" returned an
    incomplete chart missing the generate step. The real fix: only stop
    retrying once the root span specifically has appeared.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Partial batch: child spans present, root span not yet flushed.
            return httpx.Response(200, json=_jaeger_response([_span("embed_query", 100, 500)]))
        return httpx.Response(
            200,
            json=_jaeger_response(
                [_span("embed_query", 100, 500), _span("chat_request", 90, 2000)]
            ),
        )

    result = fetch_trace_spans(
        _TRACE_ID, client=_client_for(handler), max_attempts=5, retry_delay_seconds=0
    )

    assert call_count == 3
    assert result == [
        SpanSummary(name="chat_request", duration_ms=2.0, start_time_us=90),
        SpanSummary(name="embed_query", duration_ms=0.5, start_time_us=100),
    ]


def test_fetch_trace_spans_gives_up_after_max_attempts_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_jaeger_response([]))

    result = fetch_trace_spans(
        _TRACE_ID, client=_client_for(handler), max_attempts=3, retry_delay_seconds=0
    )

    assert result == []


def test_fetch_trace_spans_handles_no_data_at_all():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    result = fetch_trace_spans(
        _TRACE_ID, client=_client_for(handler), max_attempts=1, retry_delay_seconds=0
    )

    assert result == []


def _linked_span(
    name: str, span_id: str, parent_id: str | None, start_time_us: int, duration_us: int
) -> dict:
    span = _span(name, start_time_us, duration_us)
    span["spanID"] = span_id
    span["references"] = (
        [{"refType": "CHILD_OF", "traceID": _TRACE_ID, "spanID": parent_id}] if parent_id else []
    )
    return span


def test_fetch_trace_spans_keeps_only_the_chat_request_subtree():
    """Since FastAPI's native telemetry, "POST /chat" is the trace root and
    FastAPI adds its own operation spans (dependency resolution, endpoint)
    around chat_request. The UI's pipeline-step chart is about the RAG
    pipeline, so only chat_request and its descendants are returned."""
    spans = [
        _linked_span("POST /chat", "a", None, 10, 9000),
        _linked_span("resolve dependencies", "b", "a", 20, 100),
        _linked_span("run endpoint", "c", "a", 50, 8000),
        _linked_span("chat_request", "d", "c", 90, 6000),
        _linked_span("embed_query", "e", "d", 100, 2000),
        _linked_span("generate", "f", "d", 200, 5000),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_jaeger_response(spans))

    result = fetch_trace_spans(_TRACE_ID, client=_client_for(handler))

    assert [s.name for s in result] == ["chat_request", "embed_query", "generate"]
