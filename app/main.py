from fastapi import FastAPI

from app.api.sync import router as sync_router
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager


def create_app(sync_manager: SyncManager, sync_history: SyncHistory) -> FastAPI:
    """Factory, not a module-level app instance — tests build one with fake
    components (no real Qdrant/Ollama/Notion needed), avoiding the
    import-time side effects a bare `app = FastAPI()` wired to real
    services at module scope would have. Real service wiring for actual
    deployment (uvicorn app.main:app) is Sprint 11's job (docker compose) —
    building it now, unexercised, would be speculative. See
    docs/sprint-07-plan.md.
    """
    app = FastAPI(title="Knowledge Base RAG")
    app.state.sync_manager = sync_manager
    app.state.sync_history = sync_history
    app.include_router(sync_router)
    return app
