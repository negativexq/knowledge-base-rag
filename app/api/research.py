"""Authenticated research tools. No model calls are made by these endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.chat import _enforce_chat_rate_limit
from app.api.deps import get_current_user, require_role
from app.evidence.documents import DocumentRead
from app.research.feedback import FeedbackRequest, FeedbackReview, FeedbackStore
from app.security.models import RetrievalContext, Role, UserContext

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/documents/read")
async def read_document(
    body: DocumentRead, request: Request, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    deps = request.app.state.chat_deps
    if deps is None or deps.documents_factory is None:
        raise HTTPException(503, "Document reading is unavailable")
    reader = deps.documents_factory(RetrievalContext.for_user(user), None)
    try:
        result = await reader.read(body)
    except ValueError as exc:
        raise HTTPException(422, "A nonempty search query is required") from exc
    record = request.app.state.registry.get_document(
        user.tenant_id, body.document.source_type, body.document.source_id
    )
    return {
        "document": body.document.model_dump(),
        **result.as_dict(),
        "indexed_at": record.last_synced_at.isoformat() if record else None,
        "current_version": record.content_hash if record else None,
        "status": record.status if record else None,
    }


def feedback_store(request: Request) -> FeedbackStore:
    store = getattr(request.app.state, "research_feedback_store", None)
    if not isinstance(store, FeedbackStore):
        raise HTTPException(503, "Feedback storage is unavailable")
    return store


@router.post("/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackRequest, request: Request, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    _enforce_chat_rate_limit(request, user)
    return feedback_store(request).add(user.tenant_id, user.user_id, body)


@router.get("/feedback/mine")
async def own_feedback(
    request: Request, offset: int = Query(0, ge=0), user: UserContext = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return feedback_store(request).list(user.tenant_id, user=user.user_id, offset=offset)


@router.get("/feedback")
async def review_queue(
    request: Request,
    offset: int = Query(0, ge=0),
    status: Literal["open", "triaged", "resolved", "dismissed"] | None = None,
    user: UserContext = Depends(require_role(Role.OPERATOR)),
) -> list[dict[str, Any]]:
    return feedback_store(request).list(user.tenant_id, status=status, offset=offset)


@router.post("/feedback/{id}/review")
async def review_feedback(
    id: str,
    body: FeedbackReview,
    request: Request,
    user: UserContext = Depends(require_role(Role.OPERATOR)),
) -> dict[str, Any]:
    result = feedback_store(request).review(user.tenant_id, id, user.user_id, body)
    if result is None:
        raise HTTPException(404, "Feedback not found")
    return result
