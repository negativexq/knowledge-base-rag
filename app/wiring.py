import logging
import time
from contextlib import aclosing

from fastapi import FastAPI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.api.chat import ChatDependencies
from app.connectors.base import Connector
from app.connectors.filesystem import LocalFilesystemConnector
from app.connectors.notion import NotionConnector
from app.evaluation.forensic_capture import current_capture, metadata_for_chunks
from app.evaluation.semantic_answerability import OllamaSemanticEvaluator
from app.evidence.documents import DocumentReader
from app.evidence.section_aware import SectionAwareEvidenceBuilder, serialize_section_aware_context
from app.ingestion.chunking_config import QWEN3_EMBEDDING_TOKENIZER, QWEN3_TOKENIZER_REVISION
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.qdrant_store import QdrantStore
from app.ingestion.tokenizer import token_count
from app.llm.embedding_models import active_embedding_config
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.llm.provider import (
    ChatProvider,
    default_chat_model,
    default_context_tokens,
    default_embed_model,
    default_evidence_tokens,
    get_chat_provider,
)
from app.llm.query_rewrite import ChatTurn, RewriteResult, rewrite_query
from app.llm.structured_output import stream_evidence_backed_answer, stream_support_unit_answer
from app.llm.visual_answer import asks_visual, pdf_page_renderer
from app.main import create_app
from app.migration.aliasing import resolve_active_collection_name
from app.migration.readiness import check_readiness
from app.migration.startup_guard import ensure_embedding_schema_match
from app.registry.store import DocumentRegistry
from app.reranker.cross_encoder import CrossEncoderReranker
from app.research.feedback import FeedbackStore
from app.research.traces import TraceStore
from app.retrieval.filters import build_filter, combine_filters, filter_authorized_candidates
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.security.auth import build_token_authenticator
from app.security.document_permissions import DocumentPermissionStore
from app.security.models import RetrievalContext
from app.shared.config import Settings
from app.shared.tracing import langfuse_export_from, setup_tracing
from app.sync.history import SyncHistory
from app.sync.manager import SyncManager
from app.sync.scheduler import SyncScheduler, sync_intervals_from_settings

logger = logging.getLogger(__name__)


def count_prompt_tokens(text: str) -> int:
    """Token count for fitting the answer prompt into num_ctx. The Qwen3
    embedding tokenizer shares the Qwen3 chat models' vocabulary, is already
    loaded for chunking, and counts Turkish far closer than a word split."""
    return token_count(text, QWEN3_EMBEDDING_TOKENIZER, QWEN3_TOKENIZER_REVISION)


def build_reranker(settings: Settings):
    """Build the server-owned production reranker, or explicitly disable it."""
    if not settings.reranker_enabled:
        return None
    return CrossEncoderReranker(
        settings.reranker_model,
        trust_remote_code=settings.reranker_trust_remote_code,
        max_concurrency=settings.reranker_max_concurrency,
        device=settings.reranker_device,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )


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


def connector_tenant_ids(settings: Settings) -> dict[str, str]:
    """Which tenant owns each connector's documents — SERVER-
    SIDE configuration only, keyed the same way build_connectors() keys
    its dict (by source_type). This app has exactly one connector
    instance per source_type, so this is a 1:1 source_type->tenant
    mapping today, not a general multi-tenant-per-connector scheme —
    matches this app's existing architecture rather than inventing a
    new one. Used by build_app() to give SyncManager a real tenant_id
    for every ingest_connector() call it makes; never derived from a
    request.
    """
    return {
        "filesystem": settings.filesystem_tenant_id,
        "notion": settings.notion_tenant_id,
    }


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
    reranker = build_reranker(settings)
    chat_provider = get_chat_provider(settings)
    embed_config = active_embedding_config(settings)
    semantic_evaluator = None
    if settings.semantic_answerability_enabled and settings.semantic_answerability_shadow:
        semantic_evaluator = OllamaSemanticEvaluator(
            ollama,
            model=settings.answerability_eval_model,
            timeout_seconds=settings.answerability_eval_timeout_seconds,
            retries=settings.answerability_eval_retries,
        )

    evidence_builder = (
        SectionAwareEvidenceBuilder(
            qdrant_client,
            collection_name,
            token_budget=default_evidence_tokens(settings),
            count_tokens=count_prompt_tokens,
        )
        if settings.rag_pipeline_v2 or settings.support_ids_enabled
        else None
    )

    async def search_fn(
        question: str,
        context: RetrievalContext,
        report: RetrievalReport,
        source_ids: list[str] | None = None,
        filters: qm.Filter | None = None,
    ) -> list[SearchResult]:
        return await search(
            question,
            ollama,
            sparse_encoder,
            qdrant_client,
            collection_name,
            default_embed_model(settings),
            context,
            reranker=reranker,
            top_k=settings.reranker_candidate_k,
            top_n=settings.reranker_top_n,
            query_prefix=embed_config.query_prefix(),
            dimensions=embed_config.output_dimension,
            report=report,
            source_ids=source_ids,
            filters=combine_filters(build_filter(source_ids=source_ids), filters),
        )

    async def evidence_fn(
        chunks: list[SearchResult], context: RetrievalContext
    ) -> list[SearchResult]:
        if evidence_builder is None:
            return chunks
        started = time.perf_counter()
        result = await evidence_builder.build(chunks, context)
        capture = current_capture()
        if capture is not None:
            capture.stage(
                "evidence_build",
                {
                    "input_chunk_ids": result.input_chunk_ids,
                    "contributing_chunk_ids": result.contributing_chunk_ids,
                    "blocks_count": len(result.blocks),
                    "context_tokens": result.context_tokens,
                    "expanded": result.expanded,
                    "budget_exhausted": result.budget_exhausted,
                    "truncated_block_count": result.truncated_block_count,
                    "dropped_expansion_count": result.dropped_expansion_count,
                    "final_blocks": metadata_for_chunks(
                        result.blocks, include_text=capture.raw_text
                    ),
                    "evidence_build_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            )
        return result.blocks

    async def rewrite_fn(question: str, history: list[ChatTurn]) -> RewriteResult:
        rewrite_provider = chat_provider
        if settings.agentic_rag_enabled or settings.adaptive_rag_enabled:
            from pydantic_ai.usage import RunUsage, UsageLimits

            from app.llm.agentic import ToolProvider

            rewrite_provider = ToolProvider(
                chat_provider,
                RunUsage(),
                UsageLimits(),
                provider_name=settings.generation_provider,
                role="query_rewrite",
            )
        return await rewrite_query(
            rewrite_provider,
            question,
            history,
            model=default_chat_model(settings),
            timeout_seconds=settings.query_rewrite_timeout_seconds,
            max_chars=settings.chat_max_question_chars,
            think=settings.ollama_thinking,
            num_ctx=default_context_tokens(settings),
        )

    page_renderer = pdf_page_renderer(settings.filesystem_root_path)

    def classic_stream(question: str, chunks: list[SearchResult], retrieve=None):
        return stream_support_unit_answer(
            question,
            chunks,
            chat_provider,
            model=default_chat_model(settings),
            prompt_version=settings.support_id_prompt_version,
            think=settings.ollama_thinking,
            num_ctx=default_context_tokens(settings),
            validator_version=settings.critical_validator_version,
            shadow_enabled=settings.critical_validator_v3_shadow_enabled,
            architecture_v2_shadow_enabled=settings.critical_validator_arch_v2_shadow_enabled,
            count_tokens=count_prompt_tokens,
            derived_answers=settings.derived_answers_enabled,
            operand_resolver=settings.derived_answers_enabled and settings.operand_resolver_enabled,
            retrieve=retrieve,
            visual_answers=settings.visual_answers_enabled,
            render_page=page_renderer,
        )

    async def agent_stream(question: str, chunks: list[SearchResult], retrieve, documents, first):
        from app.llm.agentic import (
            PIPELINE_VERSION,
            AgentDependencies,
            EvidenceLedger,
            agent_model,
            agent_model_settings,
            run_agent,
        )

        if settings.adaptive_rag_enabled:
            from app.llm.adaptive import PIPELINE_VERSION, run_adaptive_agent

            runner = run_adaptive_agent
        else:
            runner = run_agent

        # Operations the withheld fixed path already ran on this same evidence.
        tried: set[str] = set()
        if first is not None:
            if settings.derived_answers_enabled and settings.operand_resolver_enabled:
                tried.add("resolve_calculation")
            if (
                settings.visual_answers_enabled
                and getattr(chat_provider, "supports_images", False)
                and asks_visual(question)
            ):
                tried.add("read_pages")

        async def candidate_generator(query, initial_blocks):
            context_tokens = default_context_tokens(settings)
            budget = min(settings.agentic_evidence_token_budget, context_tokens // 2)
            ledger = EvidenceLedger(
                count_prompt_tokens,
                budget,
                context=documents.context if documents is not None else None,
                source_ids=documents.source_ids if documents is not None else None,
            )
            ledger.add(initial_blocks)
            from app.llm.agent_observability import RequestUsage, load_prices

            agent_deps = AgentDependencies(
                query,
                ledger,
                retrieve=retrieve,
                documents=documents,
                observations=RequestUsage(load_prices(settings.model_pricing_json)),
                provider=chat_provider,
                provider_name=settings.generation_provider,
                scope_validation_enabled=settings.agentic_scope_validation_enabled,
                generation_kwargs={
                    "model": default_chat_model(settings),
                    "think": settings.ollama_thinking,
                    "num_ctx": context_tokens,
                    "num_predict": 1024,
                    "temperature": 0.0,
                },
                derived_answers=settings.derived_answers_enabled,
                operand_resolver=settings.operand_resolver_enabled,
                visual_answers=settings.visual_answers_enabled,
                render_page=(
                    page_renderer
                    if documents is not None
                    and documents.context.tenant_id == settings.filesystem_tenant_id
                    else None
                ),
                validator_version=settings.critical_validator_version,
                shadow_enabled=settings.critical_validator_v3_shadow_enabled,
                architecture_v2_shadow_enabled=settings.critical_validator_arch_v2_shadow_enabled,
                classic_tried=frozenset(tried),
                classic_failure_codes=first.failure_codes if first is not None else (),
                reread_first=first is not None,
            )
            model_settings = agent_model_settings(settings, context_tokens)
            async with agent_model(settings) as native_model:
                return await runner(
                    native_model,
                    agent_deps,
                    max_requests=settings.agentic_max_requests,
                    max_tool_calls=settings.agentic_max_tool_calls,
                    max_tokens=settings.agentic_max_tokens,
                    timeout_seconds=settings.agentic_timeout_seconds,
                    retries=settings.agentic_output_retries,
                    research_policy=settings.agentic_research_policy,
                    model_settings=model_settings,
                    **(
                        {
                            "fast_path": settings.adaptive_fast_path_enabled,
                            "evidence_needs_enabled": settings.adaptive_evidence_needs_enabled,
                        }
                        if settings.adaptive_rag_enabled
                        else {}
                    ),
                    **(
                        {
                            "role_model_settings": {
                                role: {
                                    "openai_reasoning_effort": effort,
                                    "max_tokens": 8192 if effort != "none" else 1024,
                                    # A None override omits inherited temperature for reasoning.
                                    "temperature": None if effort != "none" else 0.0,
                                }
                                for role, effort in {
                                    "extractor": settings.adaptive_extraction_reasoning,
                                    "extraction_checker": settings.adaptive_extraction_reasoning,
                                    "finalizer": settings.adaptive_final_reasoning,
                                    "answerer": settings.adaptive_final_reasoning,
                                    "need_planner": settings.adaptive_final_reasoning,
                                    "source_selector": settings.adaptive_final_reasoning,
                                    "quantity_selector": settings.adaptive_final_reasoning,
                                    "quantity_collector": settings.adaptive_final_reasoning,
                                    "quantity_checker": settings.adaptive_final_reasoning,
                                    "answer_repair": settings.adaptive_final_reasoning,
                                    "scoped_extraction_checker": settings.adaptive_final_reasoning,
                                    "scope_validator": settings.adaptive_final_reasoning,
                                }.items()
                            }
                        }
                        if settings.adaptive_rag_enabled
                        and settings.generation_provider == "openai"
                        else {}
                    ),
                )

        async with aclosing(
            stream_support_unit_answer(
                question,
                chunks,
                chat_provider,
                model=default_chat_model(settings),
                prompt_version=settings.support_id_prompt_version,
                validator_version=settings.critical_validator_version,
                shadow_enabled=settings.critical_validator_v3_shadow_enabled,
                architecture_v2_shadow_enabled=settings.critical_validator_arch_v2_shadow_enabled,
                derived_answers=settings.derived_answers_enabled,
                num_ctx=default_context_tokens(settings),
                candidate_generator=candidate_generator,
            )
        ) as events:
            async for event in events:
                if event["type"] == "metadata":
                    event = {**event, "pipeline_version": PIPELINE_VERSION}
                yield event

    async def stream_fn(question: str, chunks: list[SearchResult], retrieve=None, documents=None):
        if settings.adaptive_rag_enabled:
            async with aclosing(
                agent_stream(question, chunks, retrieve, documents, None)
            ) as events:
                async for event in events:
                    yield event
            return
        if settings.agentic_rag_enabled:
            from app.llm.escalation import classic_first

            scope = documents.source_ids if documents is not None else None
            async with aclosing(
                classic_first(
                    chunks,
                    lambda blocks: classic_stream(question, blocks, retrieve),
                    lambda first: agent_stream(question, chunks, retrieve, documents, first),
                    # Multi-document requests (comparisons) need the agent's contract.
                    direct=settings.agentic_mode == "always"
                    or (scope is not None and len(scope) > 1),
                    authorize=(
                        (lambda blocks: filter_authorized_candidates(blocks, documents.context))
                        if documents is not None
                        else None
                    ),
                )
            ) as events:
                async for event in events:
                    yield event
            return
        if settings.support_ids_enabled:
            async for event in classic_stream(question, chunks, retrieve):
                yield event
            return
        if settings.rag_pipeline_v2:
            async for event in stream_evidence_backed_answer(
                question,
                chunks,
                chat_provider,
                model=default_chat_model(settings),
                prompt_version=settings.active_prompt_version,
                validation_mode=settings.security_validation_mode,
                context_serializer=serialize_section_aware_context,
                think=settings.ollama_thinking,
                num_ctx=default_context_tokens(settings),
            ):
                yield event
            return
        async for event in stream_answer(
            question,
            chunks,
            chat_provider,
            model=default_chat_model(settings),
            prompt_version=settings.active_prompt_version,
            validation_mode=settings.security_validation_mode,
        ):
            yield event

    return (
        ChatDependencies(
            search_fn=search_fn,
            stream_fn=stream_fn,
            prompt_version=settings.active_prompt_version,
            security_validation_mode=settings.security_validation_mode,
            semantic_evaluator=semantic_evaluator,
            evidence_fn=evidence_fn
            if settings.rag_pipeline_v2 or settings.support_ids_enabled
            else None,
            agentic_rag_enabled=settings.agentic_rag_enabled or settings.adaptive_rag_enabled,
            documents_factory=lambda context, source_ids: DocumentReader(
                qdrant_client, collection_name, context, source_ids
            ),
            pipeline_version=(
                "pipeline_adaptive_v1"
                if settings.adaptive_rag_enabled
                else "pipeline_agentic_v1"
                if settings.agentic_rag_enabled
                else "pipeline_support_ids"
                if settings.support_ids_enabled
                else "pipeline_v2_2_evidence_backed"
                if settings.rag_pipeline_v2
                else "pipeline_v1"
            ),
            output_contract_version=(
                "output_contract_support_ids"
                if settings.support_ids_enabled
                else "output_contract_v2_2"
                if settings.rag_pipeline_v2
                else "legacy"
            ),
            critical_validator_version=settings.critical_validator_version,
            critical_validator_v3_shadow_enabled=settings.critical_validator_v3_shadow_enabled,
            critical_validator_arch_v2_shadow_enabled=settings.critical_validator_arch_v2_shadow_enabled,
            forensic_capture_enabled=settings.rag_forensic_capture_enabled,
            forensic_capture_raw_text=settings.rag_forensic_capture_raw_text,
            forensic_capture_dir=settings.rag_forensic_capture_dir,
            operand_resolver_enabled=settings.derived_answers_enabled
            and settings.operand_resolver_enabled,
            rewrite_fn=rewrite_fn if settings.query_rewrite_enabled else None,
        ),
        chat_provider,
    )


def build_app(settings: Settings) -> FastAPI:
    """Real-component wiring for `uvicorn app.server:app` — separate from
    app/main.py::create_app() (which stays a pure factory tests can call
    with fakes) so importing app/server.py is the only thing that touches
    real Qdrant/Ollama/SQLite at import time. See
    docs/adr/0005-real-wiring-pulled-forward.md.
    """
    tracer_provider = setup_tracing(
        endpoint=settings.otel_exporter_otlp_endpoint,
        langfuse=langfuse_export_from(settings),
    )

    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        connect_timeout=settings.ollama_connect_timeout_seconds,
        timeout=settings.ollama_read_timeout_seconds,
        overall_timeout=settings.ollama_overall_timeout_seconds,
    )
    qdrant_client = QdrantClient(url=settings.qdrant_url)

    # Fail fast if the configured embedding dimension doesn't
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
    # schema — refuse to start on a possibly-corrupt index
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

    tenant_ids = {
        source_type: tenant_id
        for source_type, tenant_id in connector_tenant_ids(settings).items()
        if source_type in connectors
    }
    manager = SyncManager(
        connectors=connectors,
        store=store,
        registry=registry,
        history=history,
        embed_fn=embed_fn,
        sparse_encoder=sparse_encoder,
        embedding_concurrency=settings.embedding_concurrency,
        pipeline_fingerprint=build_pipeline_fingerprint(embed_config, settings.chunking_config()),
        tenant_ids=tenant_ids,
        chunking_config=settings.chunking_config(),
    )
    chat_deps, chat_provider = build_chat_dependencies(
        settings, qdrant_client, ollama, sparse_encoder, collection_name
    )
    scheduler = SyncScheduler(manager, sync_intervals_from_settings(settings))

    async def readiness_check() -> dict:
        return await check_readiness(qdrant_client, ollama, settings)

    # Security boundary wiring. auth_enabled defaults True —
    # False is a real, explicit escape hatch (see app/api/deps.py) that
    # must never be silent, hence the loud warning log here.
    if not settings.auth_enabled:
        logger.warning(
            "AUTH_ENABLED=false — authentication is DISABLED. Every request is treated as "
            "an ADMIN in tenant 'local-dev'. This must NEVER be used outside local "
            "development. See docs/security.md."
        )
    token_authenticator = build_token_authenticator(
        settings.auth_tokens_json,
        app_env=settings.app_env,
        auth_enabled=settings.auth_enabled,
    )

    # Long-lived HTTP clients (Ollama x2 — embedding and chat are separate
    # instances — Notion, when configured — and Qdrant) all need closing
    # on app shutdown to avoid leaking connections; nothing previously
    # called any of them. QdrantClient.close() is sync, wrapped here
    # since on_shutdown hooks are async; each hook now runs in its own
    # try/except in app/main.py's lifespan, so one client failing to
    # close can't skip the rest).
    async def close_qdrant_client() -> None:
        qdrant_client.close()

    feedback = FeedbackStore(settings.research_feedback_db_path)
    request_traces = TraceStore(settings.request_trace_db_path)
    document_permissions = DocumentPermissionStore(
        settings.document_permissions_db_path, settings.document_default_access
    )

    async def close_feedback() -> None:
        feedback.close()
        request_traces.close()
        document_permissions.close()

    on_shutdown = [ollama.aclose, chat_provider.aclose, close_qdrant_client, close_feedback]
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
        token_authenticator=token_authenticator,
        auth_enabled=settings.auth_enabled,
        tenant_ids=tenant_ids,
        qdrant_client=qdrant_client,
        cors_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        settings=settings,
        tracer_provider=tracer_provider,
        research_feedback_store=feedback,
        request_trace_store=request_traces,
        document_permission_store=document_permissions,
    )
