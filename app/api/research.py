"""Authenticated research tools. No model calls are made by these endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.chat import _enforce_chat_rate_limit
from app.api.deps import get_current_user, require_role, retrieval_context
from app.evidence.documents import DocumentRead
from app.research.feedback import FeedbackRequest, FeedbackReview, FeedbackStore
from app.security.audit import log_audit_event
from app.security.document_permissions import (
    DocumentPermissionStore,
    DocumentPolicy,
    PolicyConflictError,
)
from app.security.models import Role, UserContext

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/documents/read")
async def read_document(
    body: DocumentRead, request: Request, user: UserContext = Depends(get_current_user)
) -> dict[str, Any]:
    deps = request.app.state.chat_deps
    if deps is None or deps.documents_factory is None:
        raise HTTPException(503, "Document reading is unavailable")
    context = retrieval_context(request, user)
    if context.document_permissions is not None and not context.document_permissions.rules().allows(
        body.document.source_type, body.document.source_id
    ):
        raise HTTPException(404, "Document not found")
    reader = deps.documents_factory(context, None)
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


def permission_store(request: Request) -> DocumentPermissionStore:
    store = getattr(request.app.state, "document_permission_store", None)
    if not isinstance(store, DocumentPermissionStore):
        raise HTTPException(503, "Document permissions are unavailable")
    return store


@router.get("/document-permissions")
async def list_document_permissions(
    request: Request,
    offset: int = Query(0, ge=0, le=100000),
    user: UserContext = Depends(require_role(Role.ADMIN)),
) -> list[dict[str, Any]]:
    store = permission_store(request)
    records = request.app.state.registry.list_documents(tenant_id=user.tenant_id)
    return [
        store.get(user.tenant_id, r.source_type, r.source_id).model_dump()
        for r in records[offset : offset + 50]
    ]


@router.put("/document-permissions")
async def set_document_permissions(
    body: DocumentPolicy,
    request: Request,
    user: UserContext = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    store = permission_store(request)
    record = request.app.state.registry.get_document(
        user.tenant_id, body.source_type, body.source_id
    )
    if record is None:
        raise HTTPException(404, "Document not found")
    try:
        result = store.set(user.tenant_id, user.user_id, body)
    except PolicyConflictError as exc:
        raise HTTPException(409, "Permissions changed; reload before saving") from exc
    log_audit_event(
        "document_permissions_changed",
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        source_type=body.source_type,
        source_id=body.source_id,
        revision=result.revision,
        access=result.access,
    )
    return result.model_dump()
