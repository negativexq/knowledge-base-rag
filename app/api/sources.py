from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.security.models import UserContext

router = APIRouter()


@router.get("/sources")
async def list_sources(
    request: Request, user: UserContext = Depends(get_current_user)
) -> list[dict]:
    """Sprint 23: tenant-scoped — a caller only ever sees source_types
    that (a) this app knows about AND (b) are owned by the caller's OWN
    tenant (app.state.tenant_ids, server-side connector configuration).
    document_count is likewise computed from registry.list_documents()
    FILTERED to the caller's tenant_id — never an unscoped count — so
    this endpoint can't be used to enumerate another tenant's document
    counts or even learn that a source_type exists for a tenant other
    than the caller's own.
    """
    manager = request.app.state.sync_manager
    registry = request.app.state.registry
    tenant_ids: dict[str, str] = getattr(request.app.state, "tenant_ids", {})

    return [
        {
            "source_type": source_type,
            "document_count": len(
                registry.list_documents(tenant_id=user.tenant_id, source_type=source_type)
            ),
            "is_running": manager.is_running(source_type),
        }
        for source_type in manager.known_source_types
        if tenant_ids.get(source_type) == user.tenant_id
    ]
