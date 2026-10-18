import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import get_current_user
from app.evaluation.answerability import extract_answerability_observation
from app.evaluation.critical_validator_runtime import ValidatorSelector
from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.evaluation.semantic_answerability import SemanticEvaluator
from app.evidence.documents import DocumentReaderFactory
from app.evidence.support_units import section_label
from app.llm.citation_location import location_for
from app.llm.prompt import NOT_FOUND_PHRASE
from app.llm.query_rewrite import ChatTurn, RewriteResult
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport, RetrievalStage
from app.security.audit import CONTENT_SCREENING_FLAGGED, RATE_LIMITED, log_audit_event
from app.security.content_screening import ScreeningResult, screen_input, screen_output
from app.security.models import RetrievalContext, UserContext
from app.security.rate_limit import SlidingWindowRateLimiter
from app.shared.config import SecurityValidationMode
from app.shared.tracing import get_tracer

router = APIRouter()

# Sprint 24: how much of a chunk's text the Evidence Inspector's source
# card receives. Enough to recognize the passage a citation points at,
# not the whole document — this is an evidence preview, not a document
# reader.
SNIPPET_CHAR_LIMIT = 600


# Hard cap on what the request body may carry; the configured
# chat_history_max_turns (usually far lower) is what is actually used.
MAX_HISTORY_TURNS_IN_REQUEST = 50
# Sources one request may scope its answer to.
MAX_SCOPE_SOURCES = 50


class ChatRequest(BaseModel):
    question: str
    # Recent turns of this conversation, oldest first. Client-supplied and
    # therefore untrusted: used only to rewrite a follow-up question into a
    # standalone query (app/llm/query_rewrite.py), never sent to the answer
    # model as conversation.
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS_IN_REQUEST)
    # Answer only from these sources ("ask this document"). A user filter:
    # it narrows retrieval and is AND-ed with the tenant ACL in the Qdrant
    # query (app/retrieval/search.py), so it can never reach another
    # tenant's points. None searches every source the user may read.
    source_ids: list[Annotated[str, StringConstraints(min_length=1)]] | None = Field(
        default=None, min_length=1, max_length=MAX_SCOPE_SOURCES
    )


# Sprint 23: search_fn takes the caller's RetrievalContext alongside the
# question — never just the question. There is no overload that lets a
# caller search without one; see app/retrieval/search.py::search.
#
# Sprint 24: it also takes a RetrievalReport the caller pre-creates, so
# the SSE stream can report what the retrieval pipeline REALLY did
# (measured stage timings/counts) without changing search()'s return
# type. See app/retrieval/report.py.
#
# A request scoped to some sources passes them as the keyword source_ids;
# an unscoped request calls with the three positional arguments only.
SearchFn = Callable[..., Awaitable[list[SearchResult]]]
StreamFn = Callable[[str, list[SearchResult]], AsyncIterator[dict]]
EvidenceFn = Callable[[list[SearchResult], RetrievalContext], Awaitable[list[SearchResult]]]
RewriteFn = Callable[[str, list[ChatTurn]], Awaitable[RewriteResult]]


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
    # A merged evidence block (a small source taken in full) is located at
    # its anchor, the chunk retrieval actually hit, so the snippet is the
    # anchor's text rather than the start of the document; the block's
    # sections are listed so the card can show it spans more than one.
    section_chunks = payload.get("section_chunks") or []
    anchor = next(
        (c for c in section_chunks if c.get("chunk_id") == payload.get("anchor_chunk_id")),
        None,
    )
    snippet_text = anchor["text"] if anchor is not None else payload.get("text", "")
    labels = [section_label(c) for c in section_chunks] or [section_label(payload)]
    section_labels = list(dict.fromkeys(label for label in labels if label))
    return {
        "rank": rank,
        "source_type": payload.get("source_type"),
        "source_id": payload.get("source_id"),
        "citation_location": citation_location,
        "page_number": payload.get("page_number"),
        "paragraph_index": payload.get("paragraph_index"),
        "heading_path": payload.get("heading_path") or [],
        "snippet": _snippet(snippet_text),
        "section_labels": section_labels,
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
    rewrite_fn: RewriteFn | None = None
    # The answer path may search once more for a computed answer's missing
    # operands (app/llm/operand_resolver.py), within this request's scope.
    operand_resolver_enabled: bool = False
    agentic_rag_enabled: bool = False
    documents_factory: DocumentReaderFactory | None = None


@dataclass(frozen=True)
class _ContentScreening:
    """Shadow-mode screening state for one request: who asked (for the
    audit log) and the already-computed input findings. The answer is
    screened at the end of the stream."""

    mode: str
    user_id: str
    tenant_id: str
    input_result: ScreeningResult

    def audit(self, direction: str, result: ScreeningResult) -> None:
        if result.flagged:
            log_audit_event(
                CONTENT_SCREENING_FLAGGED,
                direction=direction,
                mode=self.mode,
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                endpoint="/chat",
                **result.audit_fields(),
            )


def _generation_skip_reason(answerability_reason: str, chunks: list[SearchResult]) -> str | None:
    """Why the model must not be called, or None when there is evidence.
    Deterministic only: an empty evidence set, never a score threshold
    (reranker scores rank, they do not measure sufficiency)."""
    if answerability_reason != "FEATURES_AVAILABLE":
        return answerability_reason
    if not chunks:
        return "NO_EVIDENCE_BLOCKS"
    return None


async def _no_evidence_answer(
    deps: ChatDependencies, trace_id: str, reason: str
) -> AsyncIterator[dict]:
    """The same event shape a generation path yields for a clean model
    abstention, without the model call. trace_id is the chat_request span's,
    since no generate span exists."""
    yield {
        "type": "metadata",
        "prompt_version": deps.prompt_version,
        "pipeline_version": deps.pipeline_version,
        "output_contract_version": deps.output_contract_version,
        "trace_id": trace_id,
        "generation_skipped": reason,
    }
    yield {"type": "token", "content": NOT_FOUND_PHRASE}
    yield {
        "type": "security_validation",
        "passed": True,
        "violations": [],
        "validator_failure_codes": [],
        "citation_suppressed": True,
        "hidden_prompt_leaked": False,
        "abstain": True,
        "application_forced_abstention": False,
    }


async def _sse_event_stream(
    question: str,
    deps: ChatDependencies,
    context: RetrievalContext,
    tracer: trace.Tracer | None = None,
    screening: _ContentScreening | None = None,
    history: list[ChatTurn] | None = None,
    source_ids: list[str] | None = None,
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
    # trace's root span: app/shared/trace_client.py (Sprint 10, ported from
    # production-rag-platform's Sprint 8/12) waits specifically for a span
    # named "chat_request" as the signal that a trace is fully indexed,
    # since it's guaranteed to close last.
    with tracer.start_as_current_span("chat_request") as span:
        span.set_attribute("chat.question_char_count", len(question))
        if screening is not None:
            span.set_attribute("guardrail.mode", screening.mode)
            span.set_attributes(screening.input_result.span_attributes("guardrail.input"))
        # Only what the user is actually shown, for output screening.
        shown_tokens: list[str] = []
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
        history = history or []
        span.set_attribute("chat.history_turns", len(history))
        rewrite: RewriteResult | None = None
        if history and deps.rewrite_fn is not None:
            rewrite = await deps.rewrite_fn(question, history)
            span.set_attribute("query_rewrite.outcome", rewrite.outcome)
            # From here on the standalone question is the question: search,
            # answerability and the answer model all see the same text.
            question = rewrite.question
        scope = {"source_ids": source_ids} if source_ids else {}
        chunks = await deps.search_fn(question, context, report, **scope)
        if rewrite is not None:
            detail: dict = {"outcome": rewrite.outcome, "history_turns": len(history)}
            if rewrite.rewritten:
                detail["search_query"] = rewrite.question
            report.stages.insert(
                0, RetrievalStage("query_rewrite", rewrite.duration_ms, detail=detail)
            )
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
        generation_skip_reason = (
            None
            if deps.agentic_rag_enabled
            else _generation_skip_reason(observation.reason, chunks)
        )
        span.set_attribute("answerability.generation_skipped", generation_skip_reason is not None)
        token_counts = [chunk.payload.get("token_count") for chunk in chunks]
        report.context.update(
            {
                "retrieved_chunk_count": len(chunks),
                "top_context_tokens": (
                    sum(token_counts)
                    if token_counts and all(isinstance(value, int) for value in token_counts)
                    else None
                ),
            }
        )
        if capture is not None:
            capture.merge_stage(
                "retrieval",
                {"stage_timings_ms": {stage.name: stage.duration_ms for stage in report.stages}},
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
        answer_events = (
            _no_evidence_answer(
                deps, format(span.get_span_context().trace_id, "032x"), generation_skip_reason
            )
            if generation_skip_reason is not None
            else deps.stream_fn(
                question,
                chunks,
                **(
                    {"retrieve": _scoped_retrieve(deps, context, scope)}
                    if deps.operand_resolver_enabled or deps.agentic_rag_enabled
                    else {}
                ),
                **(
                    {"documents": deps.documents_factory(context, source_ids)}
                    if deps.agentic_rag_enabled and deps.documents_factory
                    else {}
                ),
            )
        )
        async for event in answer_events:
            if event["type"] == "token":
                if screening is not None:
                    shown_tokens.append(event["content"])
                yield f"data: {json.dumps({'token': event['content']})}\n\n"
            elif event["type"] == "evidence_update":
                sources = [source_payload(i, c) for i, c in enumerate(event["blocks"], 1)]
                yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
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

        if screening is not None:
            output_result = screen_output("".join(shown_tokens))
            span.set_attributes(output_result.span_attributes("guardrail.output"))
            screening.audit("output", output_result)

        yield "event: done\ndata: {}\n\n"
    if capture is not None:
        capture.write(deps.forensic_capture_dir)
    reset_current_capture(capture_token)


def _scoped_retrieve(deps: ChatDependencies, context: RetrievalContext, scope: dict):
    """A search for the operand resolver: the same caller, ACL and document
    scope as the request's own search, with its own report."""

    async def retrieve(query: str) -> list[SearchResult]:
        found = await deps.search_fn(query, context, RetrievalReport(), **scope)
        if deps.agentic_rag_enabled and deps.evidence_fn is not None:
            return await deps.evidence_fn(found, context)
        return found

    return retrieve


def _enforce_chat_rate_limit(request: Request, user: UserContext) -> None:
    """Per-user limit, checked before the question itself so that rejected
    (e.g. oversized or blank) questions still count. Runs after
    authentication: unauthenticated callers get 401, never a rate-limit
    slot."""
    limiter: SlidingWindowRateLimiter | None = getattr(request.app.state, "chat_rate_limiter", None)
    if limiter is None:
        return
    retry_after = limiter.check(f"{user.tenant_id}:{user.user_id}")
    if retry_after is not None:
        log_audit_event(
            RATE_LIMITED,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            endpoint=request.url.path,
            retry_after_seconds=retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many chat requests; retry later.",
            headers={"Retry-After": str(retry_after)},
        )


def _validated_question(request: Request, question: str) -> str:
    """Trimmed, non-empty and bounded, so no retrieval or LLM work is spent
    on an empty or oversized question."""
    question = question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")
    max_chars: int | None = getattr(request.app.state, "chat_max_question_chars", None)
    if max_chars is not None and len(question) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=f"Question is too long: {len(question)} characters, maximum is {max_chars}.",
        )
    return question


def _bounded_history(request: Request, history: list[ChatTurn]) -> list[ChatTurn]:
    """The most recent configured number of non-blank turns, each cut to
    the per-turn character limit, so the rewrite prompt stays bounded."""
    max_turns: int = getattr(request.app.state, "chat_history_max_turns", 0)
    max_chars: int = getattr(request.app.state, "chat_history_turn_max_chars", 2000)
    if max_turns <= 0:
        return []
    turns = [
        ChatTurn(role=turn.role, content=turn.content.strip()[:max_chars])
        for turn in history
        if turn.content.strip()
    ]
    return turns[-max_turns:]


@router.post("/chat")
async def chat(
    chat_request: ChatRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    _enforce_chat_rate_limit(request, user)
    question = _validated_question(request, chat_request.question)
    deps: ChatDependencies = request.app.state.chat_deps
    context = RetrievalContext.for_user(user)
    screening = _screen_question(request, user, question)
    history = _bounded_history(request, chat_request.history)
    return StreamingResponse(
        _sse_event_stream(
            question,
            deps,
            context,
            screening=screening,
            history=history,
            source_ids=chat_request.source_ids,
        ),
        media_type="text/event-stream",
    )


def _screen_question(
    request: Request, user: UserContext, question: str
) -> _ContentScreening | None:
    """Shadow mode: record prompt-injection and PII findings for the question,
    never block. Runs after the length check, so the regexes only ever see a
    bounded input."""
    mode = getattr(request.app.state, "content_screening_mode", "off")
    if mode == "off":
        return None
    screening = _ContentScreening(
        mode=mode,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        input_result=screen_input(question),
    )
    screening.audit("input", screening.input_result)
    return screening
