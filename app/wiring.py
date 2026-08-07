from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.api.chat import ChatDependencies
from app.connectors.base import Connector
from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX
from app.ingestion.qdrant_store import QdrantStore
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.llm.provider import default_chat_model, default_embed_model, get_chat_provider
from app.main import create_app
from app.registry.store import DocumentRegistry
from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import Settings
from app.shared.tracing import setup_tracing
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager
from app.sync.scheduler import SyncScheduler, sync_intervals_from_settings


def build_connectors(settings: Settings) -> dict[str, Connector]:
    """Which connectors are "active" — same question
    app.sync.scheduler.sync_intervals_from_settings answers for scheduling
    intervals, kept consistent here rather than re-deriving it: a
    connector without credentials (Notion without NOTION_API_KEY) isn't
    really connected, so it shouldn't appear in the Sources page or be
    syncable at all.
    """
    connectors: dict[str, Connector] = {
        "filesystem": LocalFilesystemConnector(settings.filesystem_root_path),
    }
    if settings.notion_api_key:
        connectors["notion"] = NotionConnector(api_key=settings.notion_api_key)
    return connectors


def build_chat_dependencies(
    settings: Settings,
    qdrant_client: QdrantClient,
    ollama: OllamaClient,
    sparse_encoder: SparseEncoder,
) -> ChatDependencies:
    """Curries real search()/stream_answer() calls into the two plain
    async callables ChatDependencies expects — the same shape
    app/evaluation/cli.py uses for its search_fn/generate_fn closures, so
    app/api/chat.py's own SSE/tracing logic stays testable without a real
    Qdrant/Ollama (see tests/test_api_chat.py) while this function is the
    one place real components get wired together for it.
    """
    reranker = CrossEncoderReranker()
    chat_provider = get_chat_provider(settings)

    async def search_fn(question: str) -> list[SearchResult]:
        return await search(
            question,
            ollama,
            sparse_encoder,
            qdrant_client,
            settings.qdrant_collection_name,
            default_embed_model(settings),
            reranker=reranker,
        )

    def stream_fn(question: str, chunks: list[SearchResult]):
        return stream_answer(
            question,
            chunks,
            chat_provider,
            model=default_chat_model(settings),
            prompt_version=settings.active_prompt_version,
        )

    return ChatDependencies(search_fn=search_fn, stream_fn=stream_fn)


def build_app(settings: Settings) -> FastAPI:
    """Real-component wiring for `uvicorn app.server:app` — separate from
    app/main.py::create_app() (which stays a pure factory tests can call
    with fakes) so importing app/server.py is the only thing that touches
    real Qdrant/Ollama/SQLite at import time. See docs/sprint-10-plan.md.
    """
    setup_tracing()

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=settings.qdrant_collection_name)
    registry = DocumentRegistry(settings.registry_db_path)
    history = SyncHistory(settings.registry_db_path)
    sparse_encoder = SparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

    manager = SyncManager(
        connectors=build_connectors(settings),
        store=store,
        registry=registry,
        history=history,
        embed_fn=embed_fn,
        sparse_encoder=sparse_encoder,
    )
    chat_deps = build_chat_dependencies(settings, qdrant_client, ollama, sparse_encoder)
    scheduler = SyncScheduler(manager, sync_intervals_from_settings(settings))

    return create_app(
        manager,
        history,
        registry,
        chat_deps=chat_deps,
        list_ollama_models=ollama.list_models,
        scheduler=scheduler,
    )
