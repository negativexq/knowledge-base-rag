"""Authenticated research tools. No model calls are made by these endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.evidence.documents import DocumentRead
from app.security.models import RetrievalContext, UserContext

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/documents/read")
async def read_document(
    body: DocumentRead, request: Request, user: UserContext = Depends(get_current_user)
) -> dict:
    deps = request.app.state.chat_deps
    if deps is None or deps.documents_factory is None:
        raise HTTPException(503, "Document reading is unavailable")
    reader = deps.documents_factory(RetrievalContext.for_user(user), None)
    try:
        result = await reader.read(body)
    except ValueError as exc:
        raise HTTPException(422, "A nonempty search query is required") from exc
    return {"document": body.document.model_dump(), **result.as_dict()}
