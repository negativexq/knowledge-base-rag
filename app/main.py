import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI

from app.api.chat import ChatDependencies
from app.api.chat import router as chat_router
from app.api.health import ListModelsFn
from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.api.sync import router as sync_router
from app.registry.store import DocumentRegistry
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager

logger = logging.getLogger(__name__)


class SchedulerProtocol(Protocol):
    """Shape of app.sync.scheduler.SyncScheduler — kept as a Protocol
    (rather than importing SyncScheduler directly) so tests can pass a
    plain spy without constructing a real one.
    """

    def start(self) -> None: ...
    async def stop(self) -> None: ...


def create_app(
    sync_manager: SyncManager,
    sync_history: SyncHistory,
    registry: DocumentRegistry,
    chat_deps: ChatDependencies | None = None,
    list_ollama_models: ListModelsFn | None = None,
    scheduler: SchedulerProtocol | None = None,
    on_shutdown: list[Callable[[], Awaitable[None]]] | None = None,
) -> FastAPI:
    """Factory, not a module-level app instance — tests build one with fake
    components (no real Qdrant/Ollama/Notion needed), avoiding the
    import-time side effects a bare `app = FastAPI()` wired to real
    services at module scope would have. Real service wiring lives in
    app/wiring.py + app/server.py — see
    docs/adr/0005-real-wiring-pulled-forward.md.

    `registry` is a separate parameter from `sync_manager` (which already
    owns its own registry internally) because GET /sources needs read
    access to it and SyncManager doesn't expose one — passing it here
    keeps that read-only query out of SyncManager's own interface.

    `chat_deps` is optional: tests that only exercise /sync or /sources
    never need it, and POST /chat simply isn't reachable without it.

    `scheduler` is optional too, wired into this app's FastAPI `lifespan`
    — see docs/adr/0006-scheduler-wired-via-fastapi-lifespan.md. Every
    existing test passes None, so none of them get a real background
    asyncio loop running during a unit test.

    `on_shutdown` is a list of no-arg async callables run after
    `scheduler.stop()` during lifespan shutdown — real deployments
    (app/wiring.py::build_app()) use it to close long-lived HTTP clients
    (Ollama, Notion, Qdrant) that would otherwise leak connections on
    exit. Same optional-hook pattern as `scheduler`; defaults to None, so
    no existing test needs to know about it. Each hook runs inside its
    own try/except (Sprint 16) — one client's aclose() raising (e.g.
    Notion erroring on a half-open connection) must not skip closing the
    rest.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if scheduler is not None:
            scheduler.start()
        yield
        if scheduler is not None:
            await scheduler.stop()
        for hook in on_shutdown or []:
            try:
                await hook()
            except Exception:
                logger.exception("on_shutdown hook %r failed", hook)

    app = FastAPI(title="Knowledge Base RAG", lifespan=lifespan)
    app.state.sync_manager = sync_manager
    app.state.sync_history = sync_history
    app.state.registry = registry
    app.state.chat_deps = chat_deps
    app.state.list_ollama_models = list_ollama_models
    app.include_router(sync_router)
    app.include_router(sources_router)
    app.include_router(chat_router)
    app.include_router(health_router)
    return app
