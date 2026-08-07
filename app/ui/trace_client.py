import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SpanSummary:
    name: str
    duration_ms: float
    start_time_us: int


def _parse_spans(payload: dict) -> list[SpanSummary]:
    traces = payload.get("data") or []
    if not traces:
        return []
    spans = traces[0].get("spans") or []
    return sorted(
        (
            SpanSummary(
                name=s["operationName"],
                duration_ms=s["duration"] / 1000,
                start_time_us=s["startTime"],
            )
            for s in spans
        ),
        key=lambda span: span.start_time_us,
    )


_ROOT_SPAN_NAME = "chat_request"


def fetch_trace_spans(
    trace_id: str,
    jaeger_url: str = "http://localhost:16686",
    max_attempts: int = 5,
    retry_delay_seconds: float = 1.0,
    client: httpx.Client | None = None,
) -> list[SpanSummary]:
    """Fetch and parse span timings for a trace from Jaeger's HTTP API
    (`GET /api/traces/{traceID}`, response shape confirmed for real against
    a live Jaeger instance — see docs/PLANNING.md Sprint 12 closing note).

    Jaeger's OTLP ingestion runs through a BatchSpanProcessor (Sprint 8) —
    async and batched, not synchronous. That means a trace can show up
    PARTIALLY indexed: child spans (embed_query, rerank, ...) flushed in an
    earlier batch while the last-closing span hasn't been exported yet —
    confirmed for real in Sprint 12's browser verification, where an early
    version of this function returned a chart missing the "generate" step.
    `chat_request` (the root span, Sprint 8) is guaranteed to close last —
    its presence is used as the signal that the trace is fully indexed,
    not just "some spans exist". Retries a bounded number of times with a
    short delay rather than failing immediately or polling forever; returns
    an empty list (not an exception) if the trace never appears, so the UI
    can show a clear "not indexed yet" state instead of hanging.
    """
    owns_client = client is None
    client = client or httpx.Client(base_url=jaeger_url, timeout=5.0)
    try:
        for attempt in range(max_attempts):
            response = client.get(f"/api/traces/{trace_id}")
            response.raise_for_status()
            spans = _parse_spans(response.json())
            if any(s.name == _ROOT_SPAN_NAME for s in spans):
                return spans
            if attempt < max_attempts - 1:
                time.sleep(retry_delay_seconds)
        return []
    finally:
        if owns_client:
            client.close()
