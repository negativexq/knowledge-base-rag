"""Content-free spans and request-local usage accounting for agent workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field

from app.shared.tracing import get_tracer, mark_llm_generation


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    cached_input_per_million: float | None = Field(default=None, ge=0)
    cache_write_per_million: float | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"


def load_prices(raw: str) -> dict[str, ModelPrice]:
    values = json.loads(raw)
    if not isinstance(values, dict) or len(values) > 100:
        raise ValueError("Model pricing must be an object with at most 100 models")
    return {str(key): ModelPrice.model_validate(value) for key, value in values.items()}


@dataclass
class RequestUsage:
    prices: dict[str, ModelPrice] = field(default_factory=dict)
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    priced_requests: int = 0
    usage_requests: int = 0
    known_cost_usd: float = 0
    tool_calls: int = 0
    retries: int = 0

    def record(
        self,
        span: trace.Span,
        *,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        self.requests += 1
        span.set_attribute("research.request_index", self.requests)
        known = (
            input_tokens is not None
            and output_tokens is not None
            and (input_tokens > 0 or output_tokens > 0)
        )
        span.set_attribute("usage.available", known)
        if not known:
            span.set_attribute("cost.status", "usage_unavailable")
            return
        self.usage_requests += 1
        incoming, outgoing = max(0, input_tokens or 0), max(0, output_tokens or 0)
        cached = min(max(0, cached_tokens), incoming)
        written = min(max(0, cache_write_tokens), incoming - cached)
        self.input_tokens += incoming
        self.output_tokens += outgoing
        self.cached_tokens += cached
        span.set_attribute("gen_ai.usage.input_tokens", incoming)
        span.set_attribute("gen_ai.usage.output_tokens", outgoing)
        span.set_attribute("gen_ai.usage.cache_read.input_tokens", cached)
        price = self.prices.get(f"{provider}:{model}") or self.prices.get(model)
        if (
            price is None
            or (cached and price.cached_input_per_million is None)
            or (written and price.cache_write_per_million is None)
        ):
            span.set_attribute("cost.status", "pricing_unavailable")
            return
        cost_in = (
            (incoming - cached - written) * price.input_per_million
            + cached * (price.cached_input_per_million or 0)
            + written * (price.cache_write_per_million or 0)
        ) / 1e6
        cost_out = outgoing * price.output_per_million / 1e6
        cost = cost_in + cost_out
        self.known_cost_usd += cost
        self.priced_requests += 1
        span.set_attribute("cost.status", "estimated")
        span.set_attribute("cost.usd", cost)
        span.set_attribute("cost.currency", "USD")
        span.set_attribute(
            "cost.pricing_id", hashlib.sha256(price.model_dump_json().encode()).hexdigest()[:16]
        )
        # Langfuse custom usage/cost fields; only the actual call is a generation.
        span.set_attribute(
            "langfuse.observation.usage_details",
            json.dumps({"input": incoming, "output": outgoing}),
        )
        span.set_attribute(
            "langfuse.observation.cost_details",
            json.dumps({"input": cost_in, "output": cost_out, "total": cost}),
        )

    def snapshot(self) -> dict[str, Any]:
        complete = self.priced_requests == self.requests
        return {
            "llm_requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "usage_complete": self.usage_requests == self.requests,
            "priced_requests": self.priced_requests,
            "cost_complete": complete,
            "cost_usd": self.known_cost_usd if complete else None,
            "known_cost_usd": self.known_cost_usd,
            "tool_calls": self.tool_calls,
            "retries": self.retries,
        }


_current: ContextVar[RequestUsage | None] = ContextVar("research_usage", default=None)


def current_usage() -> RequestUsage | None:
    return _current.get()


@contextmanager
def usage_scope(usage: RequestUsage) -> Iterator[RequestUsage]:
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def outcome(span: trace.Span, value: str, code: str | None = None) -> None:
    span.set_attribute("research.outcome", value)
    if code:
        span.set_attribute("error.type", code)
    if value in {"failed", "timeout", "budget_exceeded", "rejected", "retrying"}:
        span.set_status(Status(StatusCode.ERROR))
    elif value not in {"running", "cancelled"}:
        span.set_status(Status(StatusCode.OK))


@contextmanager
def operation(
    name: str,
    *,
    kind: str = "span",
    new_root: bool = False,
    tracer: trace.Tracer | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[trace.Span]:
    tracer = tracer or get_tracer("app.llm.agentic")
    # Exception messages, stack traces, arguments and model content are never exported.
    parent = trace.get_current_span().get_span_context()
    with tracer.start_as_current_span(
        name,
        context=Context() if new_root else None,
        links=[trace.Link(parent)] if new_root and parent.is_valid else None,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        span.set_attribute("langfuse.observation.type", kind)
        span.set_attribute("research.outcome", "running")
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except (asyncio.CancelledError, GeneratorExit):
            outcome(span, "cancelled")
            raise
        except BaseException as exc:
            code = type(exc).__name__
            state = (
                "timeout"
                if isinstance(exc, TimeoutError)
                else "retrying"
                if code == "ModelRetry"
                else "budget_exceeded"
                if code == "UsageLimitExceeded"
                else "failed"
            )
            outcome(span, state, code)
            raise
        else:
            # Preserve explicit domain outcomes such as rejected or clarification.
            if span.is_recording():
                current = getattr(span, "attributes", {}).get("research.outcome")
                if current == "running":
                    outcome(span, "completed")


def mark_model(span: trace.Span, provider: str, model: str, role: str) -> None:
    mark_llm_generation(span, model)
    span.set_attribute("gen_ai.provider.name", provider)
    span.set_attribute("research.model_role", role)
