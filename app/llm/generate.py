from collections.abc import AsyncIterator
from typing import Protocol

from opentelemetry import trace

from app.llm.grounding import check_grounding
from app.llm.prompt import build_messages
from app.retrieval.hybrid_search import SearchResult
from app.shared.tracing import get_tracer


class StreamingOllamaProtocol(Protocol):
    def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]: ...


async def stream_answer(
    query: str,
    chunks: list[SearchResult],
    ollama: StreamingOllamaProtocol,
    model: str,
    prompt_version: str,
    tracer: trace.Tracer | None = None,
) -> AsyncIterator[dict]:
    """Stream a grounded answer as a sequence of events:
    {"type": "metadata", "prompt_version": str} first (so the caller knows
    which prompt answered before a single token arrives), then
    {"type": "token", "content": str} for each generated token, then exactly
    one {"type": "grounding", "grounded": bool, "citations_found": [...],
    "ungrounded_citations": [...]} once generation completes.

    The grounding check is post-hoc by design — it can only run after the
    full answer (with its citations) exists, by which point the tokens have
    already been streamed, so a failed check warns instead of blocking the
    already-streamed answer.

    The whole body (including every yield) runs inside a single "generate"
    span — a Python context manager stays entered across a generator's
    yields, only closing when the generator is exhausted, so the span's
    duration covers the entire stream, not just the time to the first token.
    """
    tracer = tracer or get_tracer(__name__)

    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("generate.model", model)
        span.set_attribute("generate.prompt_version", prompt_version)
        span.set_attribute("generate.context_chunk_count", len(chunks))

        # "generate" isn't the root span, but trace_id is shared across
        # every span in a trace, so this is the same ID needed to look up
        # the whole pipeline's step durations in Jaeger.
        trace_id = format(span.get_span_context().trace_id, "032x")
        yield {"type": "metadata", "prompt_version": prompt_version, "trace_id": trace_id}

        messages = build_messages(query, chunks, version=prompt_version)
        answer_parts = []
        token_count = 0

        async for token in ollama.stream_chat(messages, model=model):
            token_count += 1
            answer_parts.append(token)
            yield {"type": "token", "content": token}

        grounding = check_grounding("".join(answer_parts), chunks)
        span.set_attribute("generate.token_count", token_count)
        span.set_attribute("generate.grounded", grounding.grounded)
        span.set_attribute("generate.citation_count", len(grounding.citations_found))

        yield {
            "type": "grounding",
            "grounded": grounding.grounded,
            "citations_found": grounding.citations_found,
            "ungrounded_citations": grounding.ungrounded_citations,
        }
