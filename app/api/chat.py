import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.critical_validator_runtime import ValidatorSelector
from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.evaluation.semantic_answerability import SemanticEvaluator
from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.security.models import RetrievalContext, UserContext
from app.shared.config import SecurityValidationMode
from app.shared.tracing import get_tracer

router = APIRouter()

# Sprint 24: how much of a chunk's text the Evidence Inspector's source
# card receives. Enough to recognize the passage a citation points at,
# not the whole document — this is an evidence preview, not a document
# reader.
SNIPPET_CHAR_LIMIT = 600


class ChatRequest(BaseModel):
    question: str


# Sprint 23: search_fn takes the caller's RetrievalContext alongside the
# question — never just the question. There is no overload that lets a
# caller search without one; see app/retrieval/search.py::search.
#
# Sprint 24: it also takes a RetrievalReport the caller pre-creates, so
# the SSE stream can report what the retrieval pipeline REALLY did
# (measured stage timings/counts) without changing search()'s return
# type. See app/retrieval/report.py.
SearchFn = Callable[[str, RetrievalContext, RetrievalReport], Awaitable[list[SearchResult]]]
StreamFn = Callable[[str, list[SearchResult]], AsyncIterator[dict]]
EvidenceFn = Callable[[list[SearchResult], RetrievalContext], Awaitable[list[SearchResult]]]


def _snippet(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= SNIPPET_CHAR_LIMIT:
        return text
    return text[:SNIPPET_CHAR_LIMIT].rstrip() + "…"


def source_payload(rank: int, result: SearchResult) -> dict:
    """One authorized chunk, shaped for the Evidence Inspector.

    `citation_location` is computed with the SAME location_for() the
    citation tag itself is built from (app/llm/prompt.py) and validated
    against (app/llm/grounding.py) — so the UI can match a rendered
    citation to its source card by exact identity, never by guessing.

    `score` is whatever the final ranking stage actually produced (the
    reranker's score when reranking ran, the RRF fused score otherwise)
    — it is NOT normalized, rescaled, or invented, so the UI must label
    it for what it is rather than as a universal relevance percentage.
    """
    payload = result.payload
    # location_for() requires page_number/paragraph_index whenever
    # heading_path is empty — always true for a real indexed chunk
    # (QdrantStore._to_point writes both unconditionally), but this is a
    # SERIALIZATION boundary: a malformed/legacy point must degrade to a
    # source card with no citation location, not take down the whole
    # answer stream with a KeyError mid-response.
    try:
        citation_location = location_for(payload)
    except KeyError:
        citation_location = None
    return {
        "rank": rank,
        "source_type": payload.get("source_type"),
        "source_id": payload.get("source_id"),
        "citation_location": citation_location,
        "page_number": payload.get("page_number"),
        "paragraph_index": payload.get("paragraph_index"),
        "heading_path": payload.get("heading_path") or [],
        "snippet": _snippet(payload.get("text", "")),
        "score": result.score,
        "document_version": payload.get("document_version"),
        "tenant_id": payload.get("tenant_id"),
        "visibility": payload.get("visibility"),
        "token_count": payload.get("token_count"),
    }


@dataclass
class ChatDependencies:
    """Wired once by app/wiring.py::build_app() with real search()/
    stream_answer() closures (the same currying pattern
    app/evaluation/cli.py uses for its search_fn/generate_fn) and stored
    on app.state.chat_deps. Kept this thin so this module's own SSE
    formatting/tracing logic can be exercised in tests with plain async
    fakes — no real Qdrant/Ollama needed (see tests/test_api_chat.py).
    """

    search_fn: SearchFn
    stream_fn: StreamFn
    prompt_version: str = "unknown"
    security_validation_mode: SecurityValidationMode = "strict"
    semantic_evaluator: SemanticEvaluator | None = None
    evidence_fn: EvidenceFn | None = None
    pipeline_version: str = "pipeline_v1"
    output_contract_version: str = "legacy"
    critical_validator_version: ValidatorSelector = "architecture_v2"
    critical_validator_v3_shadow_enabled: bool = False
    critical_validator_arch_v2_shadow_enabled: bool = False
    forensic_capture_enabled: bool = False
    forensic_capture_raw_text: bool = False
    forensic_capture_dir: str | None = None


async def _sse_event_stream(
    question: str,
    deps: ChatDependencies,
    context: RetrievalContext,
    tracer: trace.Tracer | None = None,
) -> AsyncIterator[str]:
    tracer = tracer or get_tracer(__name__)
    capture = (
        ForensicCapture.create(question, raw_text=deps.forensic_capture_raw_text)
        if deps.forensic_capture_enabled
        else None
    )
    capture_token = set_current_capture(capture)
    # Wraps the whole request (search + generate), including every yield
    # below — a Python context manager stays entered across a generator's
    # yields, only closing once the generator is exhausted. This is the
    # trace's root span: app/ui/trace_client.py (Sprint 10, ported from
    # production-rag-platform's Sprint 8/12) waits specifically for a span
    # named "chat_request" as the signal that a trace is fully indexed,
    # since it's guaranteed to close last.
    with tracer.start_as_current_span("chat_request") as span:
        span.set_attribute("chat.question_char_count", len(question))
        report = RetrievalReport(forensic_capture=capture)
        report.prompt_policy_version = deps.prompt_version
        report.untrusted_context_enabled = deps.prompt_version == "v3"
        report.security_validation_mode = deps.security_validation_mode
        report.validator = {
            "version": deps.critical_validator_version,
            "shadow_enabled": deps.critical_validator_v3_shadow_enabled,
            "architecture_v2_shadow_enabled": deps.critical_validator_arch_v2_shadow_enabled,
        }
        span.set_attribute("validator.version", deps.critical_validator_version)
        span.set_attribute("validator.shadow_enabled", deps.critical_validator_v3_shadow_enabled)
        span.set_attribute(
            "validator.shadow.architecture_v2_enabled",
            deps.critical_validator_arch_v2_shadow_enabled,
        )
        chunks = await deps.search_fn(question, context, report)
        anchor_chunks = chunks
        authorized_candidate_count = report.authorized_candidate_count
        if authorized_candidate_count is None:
            authorized_candidate_count = len(chunks)
        observation = extract_answerability_observation(
            chunks,
            authorized_candidate_count=authorized_candidate_count,
            pre_acl_candidate_count=report.pre_acl_candidate_count,
        )
        report.answerability = observation.as_dict()
        answerability_features = observation.features
        for name, value in (
            (
                "answerability.authorized_candidate_count",
                answerability_features.authorized_candidate_count,
            ),
            (
                "answerability.pre_acl_candidate_count",
                answerability_features.pre_acl_candidate_count,
            ),
            ("answerability.reranked_count", answerability_features.reranked_count),
            ("answerability.top1_score", answerability_features.top1_score),
            ("answerability.margin", answerability_features.top1_top2_margin),
            (
                "answerability.distinct_source_count",
                answerability_features.distinct_source_count_top5,
            ),
            ("answerability.feature_latency_ms", answerability_features.feature_latency_ms),
        ):
            if value is not None:
                span.set_attribute(name, value)
        span.set_attribute("answerability.reason", observation.reason)
        if deps.semantic_evaluator is not None:
            semantic_observation = await deps.semantic_evaluator.evaluate(
                question,
                chunks,
                deterministic_reason=observation.reason
                if observation.reason != "FEATURES_AVAILABLE"
                else None,
            )
            report.semantic_answerability = semantic_observation.as_dict()
            semantic_fields = semantic_observation.as_dict()
            ambiguity = semantic_fields.get("ambiguity") or {}
            sufficiency = semantic_fields.get("sufficiency") or {}
            span.set_attribute(
                "semantic_answerability.ambiguity_decision", ambiguity.get("decision", "")
            )
            span.set_attribute(
                "semantic_answerability.sufficiency_decision", sufficiency.get("decision", "")
            )
            span.set_attribute(
                "semantic_answerability.shadow_action",
                semantic_observation.shadow_action,
            )
            span.set_attribute("semantic_answerability.latency_ms", semantic_observation.latency_ms)
            span.set_attribute(
                "semantic_answerability.parse_error", semantic_observation.parse_error
            )
            span.set_attribute(
                "semantic_answerability.support_count",
                len(sufficiency.get("supporting_chunk_ids", [])),
            )
        if deps.evidence_fn is not None:
            chunks = await deps.evidence_fn(anchor_chunks, context)
            span.set_attribute("pipeline.evidence_block_count", len(chunks))
        token_counts = [chunk.payload.get("token_count") for chunk in chunks]
        report.context.update({
            "retrieved_chunk_count": len(chunks),
            "top_context_tokens": (
                sum(token_counts)
                if token_counts and all(isinstance(value, int) for value in token_counts)
                else None
            ),
        })
        if capture is not None:
            capture.merge_stage(
                "retrieval",
                {
                    "stage_timings_ms": {
                        stage.name: stage.duration_ms for stage in report.stages
                    }
                },
            )
            capture.merge_stage(
                "visible_pipeline",
                {
                    "pipeline_version": deps.pipeline_version,
                    "output_contract_version": deps.output_contract_version,
                    "validator_version": deps.critical_validator_version,
                    "shadow_enabled": deps.critical_validator_v3_shadow_enabled,
                    "architecture_v2_shadow_enabled": (
                        deps.critical_validator_arch_v2_shadow_enabled
                    ),
                    "final_evidence_blocks": [
                        {
                            "rank": index,
                            "chunk_id": str(chunk.id or chunk.payload.get("chunk_id", "")),
                            "source_id": chunk.payload.get("source_id"),
                            "section_key": chunk.payload.get("section_key")
                            or chunk.payload.get("heading_path"),
                            "evidence_id": chunk.payload.get("evidence_id", f"E{index}"),
                            "document_version": chunk.payload.get("document_version"),
                            "truncated": bool(chunk.payload.get("truncated", False)),
                            "text": chunk.payload.get("text", ""),
                        }
                        for index, chunk in enumerate(chunks, 1)
                    ],
                },
            )

        # Sprint 24: the authorized context is emitted BEFORE the first
        # token, so the Evidence Inspector is populated while the answer
        # is still streaming rather than only after it finishes. These
        # are exactly the chunks generation receives — post-ACL,
        # post-rerank — so "what the UI shows as evidence" and "what the
        # model was actually given" cannot drift apart.
        sources = [source_payload(i, c) for i, c in enumerate(chunks, start=1)]
        yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
        yield f"event: retrieval\ndata: {json.dumps(report.as_dict())}\n\n"
        security_payload = {
            **report.as_dict()["authorization"],
            **report.as_dict()["security"],
        }
        yield f"event: security\ndata: {json.dumps(security_payload)}\n\n"

        # stream_answer() (app/llm/generate.py) already yields its own
        # "metadata" event carrying a trace_id extracted from its own
        # "generate" span — since that span nests under this one (same
        # trace, OTel context propagation), that trace_id already
        # identifies this whole request; no need to re-extract or
        # override it here.
        async for event in deps.stream_fn(question, chunks):
            if event["type"] == "token":
                yield f"data: {json.dumps({'token': event['content']})}\n\n"
            elif event["type"] == "metadata":
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: metadata\ndata: {json.dumps(payload)}\n\n"
            elif event["type"] == "security_validation":
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: security\ndata: {json.dumps(payload)}\n\n"
            elif event["type"] == "error":
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
            else:
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: grounding\ndata: {json.dumps(payload)}\n\n"

        yield "event: done\ndata: {}\n\n"
    if capture is not None:
        capture.write(deps.forensic_capture_dir)
    reset_current_capture(capture_token)


@router.post("/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    deps: ChatDependencies = request.app.state.chat_deps
    context = RetrievalContext.for_user(user)
    return StreamingResponse(
        _sse_event_stream(chat_request.question, deps, context), media_type="text/event-stream"
    )
