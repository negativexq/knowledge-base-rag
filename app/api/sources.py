from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/sources")
async def list_sources(request: Request) -> list[dict]:
    manager = request.app.state.sync_manager
    registry = request.app.state.registry

    return [
        {
            "source_type": source_type,
            "document_count": len(registry.list_documents(source_type=source_type)),
            "is_running": manager.is_running(source_type),
        }
        for source_type in manager.known_source_types
    ]
