from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.api.chat import ChatDependencies
from app.connectors.base import Connector
from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.llm.provider import (
    ChatProvider,
    default_chat_model,
    default_embed_model,
    get_chat_provider,
)
from app.main import create_app
from app.migration.aliasing import resolve_active_collection_name
from app.migration.readiness import check_readiness
from app.migration.startup_guard import ensure_embedding_schema_match
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
    collection_name: str,
) -> tuple[ChatDependencies, ChatProvider]:
    """Curries real search()/stream_answer() calls into the two plain
    async callables ChatDependencies expects — the same shape
    app/evaluation/cli.py uses for its search_fn/generate_fn closures, so
    app/api/chat.py's own SSE/tracing logic stays testable without a real
    Qdrant/Ollama (see tests/test_api_chat.py) while this function is the
    one place real components get wired together for it.

    Also returns the ChatProvider it constructed — a SEPARATE instance
    from the `ollama` embedding client passed in (get_chat_provider always
    builds its own, even when generation_provider="ollama") — so the
    caller can close it on shutdown too.
    """
    reranker = CrossEncoderReranker()
    chat_provider = get_chat_provider(settings)
    embed_config = active_embedding_config(settings)

    async def search_fn(question: str) -> list[SearchResult]:
        return await search(
            question,
            ollama,
            sparse_encoder,
            qdrant_client,
            collection_name,
            default_embed_model(settings),
            reranker=reranker,
            query_prefix=embed_config.query_prefix(),
            dimensions=embed_config.output_dimension,
        )

    def stream_fn(question: str, chunks: list[SearchResult]):
        return stream_answer(
            question,
            chunks,
            chat_provider,
            model=default_chat_model(settings),
            prompt_version=settings.active_prompt_version,
        )

    return ChatDependencies(search_fn=search_fn, stream_fn=stream_fn), chat_provider


def build_app(settings: Settings) -> FastAPI:
    """Real-component wiring for `uvicorn app.server:app` — separate from
    app/main.py::create_app() (which stays a pure factory tests can call
    with fakes) so importing app/server.py is the only thing that touches
    real Qdrant/Ollama/SQLite at import time. See
    docs/adr/0005-real-wiring-pulled-forward.md.
    """
    setup_tracing()

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)

    # Sprint 22: fail fast if the configured embedding dimension doesn't
    # match whatever's actually in the active collection/alias — a stale
    # .env after a partial/aborted migration must never silently serve
    # dimension-mismatched traffic. See app/migration/startup_guard.py.
    ensure_embedding_schema_match(qdrant_client, settings)

    # Resolves to settings.qdrant_active_alias ("kb_active") once a
    # migration has activated at least once, or falls back to the
    # literal settings.qdrant_collection_name otherwise — see
    # app/migration/aliasing.py::resolve_active_collection_name. Every
    # call site below (store, embed_fn, chat search_fn) uses this SAME
    # resolved name, so serving is consistently pointed at one physical
    # collection for this process's lifetime.
    collection_name = resolve_active_collection_name(qdrant_client, settings)
    embed_config = active_embedding_config(settings)
    store = QdrantStore(
        client=qdrant_client,
        collection_name=collection_name,
        dense_dimension=embed_config.dimension,
    )
    registry = DocumentRegistry(settings.registry_db_path)
    # Fail fast if this registry's index predates the current point-ID
    # schema (Sprint 17.1) — refuse to start on a possibly-corrupt index
    # rather than serve traffic against it. See
    # app/registry/store.py::IndexSchemaMismatchError.
    registry.ensure_index_schema_version()
    history = SyncHistory(settings.registry_db_path)
    sparse_encoder = SparseEncoder()
    connectors = build_connectors(settings)

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text,
            model=embed_config.ollama_model,
            prefix=embed_config.document_prefix(),
            dimensions=embed_config.output_dimension,
        )

    manager = SyncManager(
        connectors=connectors,
        store=store,
        registry=registry,
        history=history,
        embed_fn=embed_fn,
        sparse_encoder=sparse_encoder,
        embedding_concurrency=settings.embedding_concurrency,
        pipeline_fingerprint=build_pipeline_fingerprint(embed_config),
    )
    chat_deps, chat_provider = build_chat_dependencies(
        settings, qdrant_client, ollama, sparse_encoder, collection_name
    )
    scheduler = SyncScheduler(manager, sync_intervals_from_settings(settings))

    async def readiness_check() -> dict:
        return await check_readiness(qdrant_client, ollama, settings)

    # Long-lived HTTP clients (Ollama x2 — embedding and chat are separate
    # instances — Notion, when configured — and Qdrant) all need closing
    # on app shutdown to avoid leaking connections; nothing previously
    # called any of them. See docs/sprint-15-plan.md,
    # docs/sprint-16-plan.md (QdrantClient.close() is sync, wrapped here
    # since on_shutdown hooks are async; each hook now runs in its own
    # try/except in app/main.py's lifespan, so one client failing to
    # close can't skip the rest).
    async def close_qdrant_client() -> None:
        qdrant_client.close()

    on_shutdown = [ollama.aclose, chat_provider.aclose, close_qdrant_client]
    for connector in connectors.values():
        if hasattr(connector, "aclose"):
            on_shutdown.append(connector.aclose)

    return create_app(
        manager,
        history,
        registry,
        chat_deps=chat_deps,
        list_ollama_models=ollama.list_models,
        scheduler=scheduler,
        on_shutdown=on_shutdown,
        readiness_check=readiness_check,
    )
