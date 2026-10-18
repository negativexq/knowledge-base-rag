import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class SpanSummary:
    name: str
    duration_ms: float
    start_time_us: int
    span_id: str | None = None
    parent_span_id: str | None = None
    status: str = "unset"
    attributes: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None
    user_id: str | None = None


def _chat_request_subtree(spans: list[dict]) -> list[dict]:
    """Since FastAPI's native telemetry the trace root is the HTTP span
    ("POST /chat") with FastAPI's own operation spans around
    chat_request; the pipeline chart only wants chat_request and its
    descendants. Spans without Jaeger span IDs are returned unchanged."""
    root_id = next(
        (s.get("spanID") for s in spans if s.get("operationName") == _ROOT_SPAN_NAME), None
    )
    if root_id is None:
        return spans
    parent_of = {
        s["spanID"]: next(
            (r["spanID"] for r in s.get("references") or [] if r.get("refType") == "CHILD_OF"),
            None,
        )
        for s in spans
        if "spanID" in s
    }

    def in_subtree(span_id: str | None) -> bool:
        seen: set[str] = set()
        while span_id is not None and span_id not in seen:
            seen.add(span_id)
            if span_id == root_id:
                return True
            span_id = parent_of.get(span_id)
        return False

    return [s for s in spans if in_subtree(s.get("spanID"))]


# Explicit schema, not prefix-based: credentials, content and arbitrary SDK
# attributes/events never reach the browser through this endpoint.
SAFE_ATTRIBUTES = frozenset(
    {
        "document.action",
        "document.returned_passages",
        "document.scan_limited",
        "document.has_more",
        "tool.returned_blocks",
        "tool.added_blocks",
        "tool.verified",
        "tool.resolved",
        "tool.has_more",
        "tool.scan_limited",
        "research.outcome",
        "research.pipeline",
        "research.phase",
        "research.attempt",
        "research.model_role",
        "research.parent_trace_id",
        "research.request_index",
        "research.retry_count",
        "gen_ai.request.model",
        "gen_ai.provider.name",
        "gen_ai.operation.name",
        "gen_ai.tool.name",
        "gen_ai.tool.call.id",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.cache_read.input_tokens",
        "gen_ai.response.finish_reasons",
        "usage.available",
        "cost.status",
        "cost.usd",
        "cost.currency",
        "cost.pricing_id",
        "error.type",
        "validator.failure_codes",
        "research.llm_requests",
        "research.input_tokens",
        "research.output_tokens",
        "research.cached_tokens",
        "research.tool_calls",
        "research.retries",
        "research.cost_complete",
        "research.usage_complete",
        "research.known_cost_usd",
        "research.priced_requests",
        "generate.agent_requests",
        "generate.agent_tool_calls",
    }
)


def _summary(span: dict) -> SpanSummary:
    tags = {t["key"]: t.get("value") for t in span.get("tags", []) if "key" in t}
    status = str(tags.get("otel.status_code", "unset")).lower()
    if tags.get("error") is True:
        status = "error"
    return SpanSummary(
        name=span["operationName"],
        duration_ms=max(0, span["duration"]) / 1000,
        start_time_us=span["startTime"],
        span_id=span.get("spanID"),
        parent_span_id=next(
            (r["spanID"] for r in span.get("references", []) if r.get("refType") == "CHILD_OF"),
            None,
        ),
        status=status,
        attributes={k: v for k, v in tags.items() if k in SAFE_ATTRIBUTES},
        tenant_id=tags.get("security.tenant_id"),
        user_id=tags.get("research.user_id"),
    )


def _parse_spans(payload: dict) -> list[SpanSummary]:
    traces = payload.get("data") or []
    if not traces:
        return []
    spans = _chat_request_subtree(traces[0].get("spans") or [])
    return sorted(
        (_summary(s) for s in spans),
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
    a live Jaeger instance).

    A trace can appear PARTIALLY indexed (Jaeger's OTLP ingestion is async
    and batched) — some child spans flushed while the last-closing span
    hasn't been exported yet. `chat_request` (the root span) is
    guaranteed to close last, so its presence, not just "some spans
    exist", is the signal the trace is fully indexed. See
    docs/adr/0004-single-trace-per-sync-run.md. Retries a bounded number
    of times with a short delay rather than failing immediately or
    polling forever; returns an empty list (not an exception) if the
    trace never appears, so the UI can show a clear "not indexed yet"
    state instead of hanging.
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
