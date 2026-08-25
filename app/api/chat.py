import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext, UserContext
from app.shared.tracing import get_tracer

router = APIRouter()


class ChatRequest(BaseModel):
    question: str


# Sprint 23: search_fn now takes the caller's RetrievalContext alongside
# the question — never just the question. There is no overload that
# lets a caller search without one; see app/retrieval/search.py::search.
SearchFn = Callable[[str, RetrievalContext], Awaitable[list[SearchResult]]]
StreamFn = Callable[[str, list[SearchResult]], AsyncIterator[dict]]


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


async def _sse_event_stream(
    question: str,
    deps: ChatDependencies,
    context: RetrievalContext,
    tracer: trace.Tracer | None = None,
) -> AsyncIterator[str]:
    tracer = tracer or get_tracer(__name__)
    # Wraps the whole request (search + generate), including every yield
    # below — a Python context manager stays entered across a generator's
    # yields, only closing once the generator is exhausted. This is the
    # trace's root span: app/ui/trace_client.py (Sprint 10, ported from
    # production-rag-platform's Sprint 8/12) waits specifically for a span
    # named "chat_request" as the signal that a trace is fully indexed,
    # since it's guaranteed to close last.
    with tracer.start_as_current_span("chat_request") as span:
        span.set_attribute("chat.question_char_count", len(question))
        chunks = await deps.search_fn(question, context)
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
            else:
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: grounding\ndata: {json.dumps(payload)}\n\n"


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
