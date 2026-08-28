import logging
from collections.abc import AsyncIterator, Callable

from opentelemetry import trace

from app.llm.grounding import check_grounding
from app.llm.observability import GenerationObservation
from app.llm.output_policy import check_output_policy
from app.llm.prompt import build_messages, load_system_prompt
from app.llm.provider import ChatProvider
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import (
    SecurityValidationMode,
    validate_security_validation_mode,
)
from app.shared.tracing import get_tracer

logger = logging.getLogger(__name__)


async def stream_answer(
    query: str,
    chunks: list[SearchResult],
    ollama: ChatProvider,
    model: str,
    prompt_version: str,
    validation_mode: SecurityValidationMode = "strict",
    injection_eval_category: str | None = None,
    tracer: trace.Tracer | None = None,
    evaluation_observation: GenerationObservation | None = None,
    context_serializer: Callable[[list[SearchResult]], str] | None = None,
    system_prompt_suffix: str | None = None,
) -> AsyncIterator[dict]:
    """Stream a grounded answer as a sequence of events:
    {"type": "metadata", "prompt_version": str} first (so the caller knows
    which prompt answered before a single token arrives), then
    {"type": "token", "content": str} for each generated token, then exactly
    one {"type": "grounding", "grounded": bool, "has_citations": bool,
    "citations_found": [...], "ungrounded_citations": [...]} once
    generation completes.

    v1/v2 retain their historical fast behavior for reproducible baselines.
    v3 adds a deterministic output policy check. In ``fast`` mode tokens are
    still released immediately and the check is reported after generation.
    In ``strict`` mode the answer is buffered and released only if citation
    integrity and disclosure/suppression checks pass.

    The whole body (including every yield) runs inside a single "generate"
    span — a Python context manager stays entered across a generator's
    yields, only closing when the generator is exhausted, so the span's
    duration covers the entire stream, not just the time to the first token.
    """
    tracer = tracer or get_tracer(__name__)
    validation_mode = validate_security_validation_mode(validation_mode)

    with tracer.start_as_current_span("generate") as span:
        span.set_attribute("generate.model", model)
        span.set_attribute("generate.prompt_version", prompt_version)
        span.set_attribute("generate.context_chunk_count", len(chunks))
        span.set_attribute("security.untrusted_context_enabled", prompt_version == "v3")
        span.set_attribute("security.validation_mode", validation_mode)
        if injection_eval_category:
            span.set_attribute("security.injection_eval_category", injection_eval_category)

        # "generate" isn't the root span, but trace_id is shared across
        # every span in a trace, so this is the same ID needed to look up
        # the whole pipeline's step durations in Jaeger.
        trace_id = format(span.get_span_context().trace_id, "032x")
        yield {
            "type": "metadata",
            "prompt_version": prompt_version,
            "trace_id": trace_id,
            "untrusted_context_enabled": prompt_version == "v3",
            "security_validation_mode": validation_mode,
        }

        messages = build_messages(
            query,
            chunks,
            version=prompt_version,
            context_serializer=context_serializer,
            system_prompt_suffix=system_prompt_suffix,
        )
        answer_parts = []
        token_count = 0

        async for token in ollama.stream_chat(messages, model=model):
            token_count += 1
            answer_parts.append(token)
            if prompt_version != "v3" or validation_mode == "fast":
                yield {"type": "token", "content": token}

        answer = "".join(answer_parts)
        grounding = check_grounding(answer, chunks)
        output_policy = None
        if prompt_version == "v3":
            output_policy = check_output_policy(answer, chunks, load_system_prompt(prompt_version))
            span.set_attribute("security.output_policy_passed", output_policy.passed)
            if output_policy.violations:
                logger.warning(
                    "rag_output_policy_violation violations=%s mode=%s prompt_version=%s",
                    ",".join(output_policy.violations),
                    validation_mode,
                    prompt_version,
                )
            if validation_mode == "strict" and output_policy.passed:
                for token in answer_parts:
                    yield {"type": "token", "content": token}
        if evaluation_observation is not None:
            evaluation_observation.record(
                answer,
                grounding,
                output_policy,
                prompt_version=prompt_version,
                validation_mode=validation_mode,
            )
        span.set_attribute("generate.token_count", token_count)
        span.set_attribute("generate.grounded", grounding.grounded)
        span.set_attribute("generate.citation_count", len(grounding.citations_found))

        yield {
            "type": "grounding",
            "grounded": grounding.grounded,
            "has_citations": grounding.has_citations,
            "citations_found": grounding.citations_found,
            "ungrounded_citations": grounding.ungrounded_citations,
        }

        if output_policy is not None:
            yield {
                "type": "security_validation",
                **output_policy.as_dict(),
            }
            if validation_mode == "strict" and not output_policy.passed:
                yield {
                    "type": "error",
                    "message": "The answer was withheld because output policy validation failed.",
                }
