from fastapi import FastAPI

from app.api.chat import ChatDependencies
from app.api.chat import router as chat_router
from app.api.sources import router as sources_router
from app.api.sync import router as sync_router
from app.registry.store import DocumentRegistry
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager


def create_app(
    sync_manager: SyncManager,
    sync_history: SyncHistory,
    registry: DocumentRegistry,
    chat_deps: ChatDependencies | None = None,
) -> FastAPI:
    """Factory, not a module-level app instance — tests build one with fake
    components (no real Qdrant/Ollama/Notion needed), avoiding the
    import-time side effects a bare `app = FastAPI()` wired to real
    services at module scope would have. Real service wiring for actual
    deployment lives in app/wiring.py + app/server.py (Sprint 10 pulled
    forward the minimal piece of what Sprint 07's plan deferred to "Sprint
    11 (docker compose)" — this sprint's own DoD needs a real, running
    backend to browser-verify against). See docs/sprint-10-plan.md.

    `registry` is a separate parameter from `sync_manager` (which already
    owns its own registry internally) because GET /sources needs read
    access to it and SyncManager doesn't expose one — passing it here
    keeps that read-only query out of SyncManager's own interface.

    `chat_deps` is optional: tests that only exercise /sync or /sources
    never need it, and POST /chat simply isn't reachable without it.
    """
    app = FastAPI(title="Knowledge Base RAG")
    app.state.sync_manager = sync_manager
    app.state.sync_history = sync_history
    app.state.registry = registry
    app.state.chat_deps = chat_deps
    app.include_router(sync_router)
    app.include_router(sources_router)
    app.include_router(chat_router)
    return app
