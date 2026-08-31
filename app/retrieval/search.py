import asyncio
from typing import Protocol

from opentelemetry import trace
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.evaluation.forensic_capture import metadata_for_chunks
from app.llm.provider import EmbeddingProvider
from app.reranker.config import RERANKER_CANDIDATE_K, RERANKER_TOP_N
from app.retrieval.filters import build_acl_filter, build_filter, filter_authorized_candidates
from app.retrieval.hybrid_search import DEFAULT_PREFETCH_LIMIT, SearchResult, hybrid_search
from app.retrieval.report import RetrievalReport, stage_timer
from app.retrieval.sparse import SparseVector
from app.security.models import RetrievalContext
from app.shared.tracing import get_tracer

# Query-side counterpart to app/ingestion/ingest.py's SEARCH_DOCUMENT_PREFIX —
# nomic-embed-text requires this prefix on the *query* text for retrieval to
# work well.
SEARCH_QUERY_PREFIX = "search_query: "

# Provisional, like the chunker's chunk size — a starting assumption pending
# real signal from evaluation (Sprint 9).
# Compatibility exports for existing callers; values live in
# app.reranker.config so wiring and UI cannot drift.
RERANK_CANDIDATE_K = RERANKER_CANDIDATE_K
RERANK_TOP_N = RERANKER_TOP_N


class SparseEncoderProtocol(Protocol):
    def embed_query(self, text: str) -> SparseVector: ...


class RerankerProtocol(Protocol):
    def rerank(
        self, query: str, candidates: list[SearchResult], top_n: int
    ) -> list[SearchResult]: ...


async def search(
    query: str,
    ollama: EmbeddingProvider,
    sparse_encoder: SparseEncoderProtocol,
    qdrant_client: QdrantClient,
    collection_name: str,
    embed_model: str,
    context: RetrievalContext,
    reranker: RerankerProtocol | None = None,
    top_k: int = RERANK_CANDIDATE_K,
    top_n: int = RERANK_TOP_N,
    doc_ids: list[str] | None = None,
    source_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    page_numbers: list[int] | None = None,
    filters: qmodels.Filter | None = None,
    tracer: trace.Tracer | None = None,
    query_prefix: str = SEARCH_QUERY_PREFIX,
    dimensions: int | None = None,
    report: RetrievalReport | None = None,
) -> list[SearchResult]:
    # Sprint 18: query_prefix is a parameter (defaulting to nomic's own
    # SEARCH_QUERY_PREFIX, so every existing caller is unaffected) rather
    # than a hardcoded constant, so scripts/benchmark_embeddings.py can
    # reuse this EXACT retrieval code path for a challenger embedding
    # model with its own instruction format
    # (app/llm/embedding_models.py::EmbeddingModelConfig.query_prefix())
    # instead of silently applying nomic's "search_query: " to it. Using
    # the same search() for both keeps retrieval configuration (top_k,
    # top_n, RRF, filters) guaranteed identical between baseline and
    # challenger — only the prefix and embed_model differ.
    #
    # Sprint 19: dimensions (default None, every existing caller
    # unaffected) is passed straight through to ollama.embed() — without
    # it, a Matryoshka-truncated config (e.g. qwen3-4b@1024) would embed
    # the QUERY at its native dimension while the collection was indexed
    # at the truncated one, a real dimension mismatch Qdrant rejects
    # outright. Reproduced for real running the Sprint 19 benchmark
    # before this parameter was added — see docs/sprint-19-plan.md.
    #
    # Sprint 23: `context` is REQUIRED (no default) — every call site in
    # this codebase (production chat, benchmark scripts, evaluation CLI,
    # migration quality gate) must now say explicitly whether it's
    # authorizing as a real tenant-scoped user
    # (RetrievalContext.for_user(...)) or as privileged internal system
    # code (RetrievalContext.system()). There is no third, implicit
    # option — see app/retrieval/filters.py::build_acl_filter, which
    # raises rather than building an unrestricted filter for anything
    # in between.
    #
    # Sprint 24: `report` (default None — every non-UI caller is
    # unaffected and pays nothing) collects REAL measured stage
    # timings/counts for the operations console's Retrieval inspector.
    # See app/retrieval/report.py: nothing in it is estimated, and a
    # stage the pipeline genuinely doesn't run is simply absent.
    tracer = tracer or get_tracer(__name__)

    with tracer.start_as_current_span("embed_query") as span:
        span.set_attribute("embed.model", embed_model)
        with stage_timer(report, "query_embedding", model=embed_model, dimensions=dimensions):
            dense_vector = await ollama.embed(
                query, model=embed_model, prefix=query_prefix, dimensions=dimensions
            )
        with stage_timer(report, "sparse_encoding", model="Qdrant/bm25") as timer:
            sparse_vector = sparse_encoder.embed_query(query)
            timer.candidates_out = len(sparse_vector.indices)

    # The ACL is built from `context` alone — never from request filters.
    # One bounded raw candidate list is retrieved using only additional user
    # filters, then the server-owned ACL is applied immediately below. This
    # provides a safe raw count without a second retrieval call; unauthorized
    # payloads are discarded before reranking.
    with tracer.start_as_current_span("build_acl_filter") as span:
        acl_filter = build_acl_filter(context)
        span.set_attribute("acl.is_system", context.is_system)
        span.set_attribute("acl.tenant_scoped", acl_filter is not None)

    user_filters = filters or build_filter(doc_ids, source_types, source_ids, page_numbers)
    if report is not None:
        report.acl_applied = acl_filter is not None
        report.acl_tenant_id = context.tenant_id
        report.is_system_context = context.is_system
        report.user_filters_applied = user_filters is not None
        report.reranker = {
            "enabled": reranker is not None,
            "model": getattr(reranker, "model_name", None),
            "backend": getattr(reranker, "backend", None),
            "candidate_k": top_k,
            "top_n": top_n,
        }

    with tracer.start_as_current_span("retrieve_hybrid") as span:
        span.set_attribute("retrieve.top_k", top_k)
        # Dense, sparse, and RRF fusion all happen inside ONE Qdrant
        # query_points call (prefetch + FusionQuery) — Qdrant does the
        # fusion server-side, so this app never observes the per-branch
        # dense/sparse candidate lists separately. `prefetch_limit` is
        # therefore reported as the CONFIGURED per-branch limit (a real
        # config value), not as a measured count of what each branch
        # returned — a number this code genuinely cannot see.
        with stage_timer(
            report,
            "hybrid_retrieval",
            fusion="RRF",
            branches=["dense", "sparse_bm25"],
            configured_prefetch_limit_per_branch=DEFAULT_PREFETCH_LIMIT,
            fusion_performed_by="qdrant",
        ) as timer:
            raw_candidates = hybrid_search(
                qdrant_client,
                collection_name,
                dense_vector,
                sparse_vector,
                top_k=top_k,
                filters=user_filters,
            )
            candidates = filter_authorized_candidates(raw_candidates, context)
            timer.candidates_in = len(raw_candidates)
            timer.candidates_out = len(candidates)
            timer.top_score = candidates[0].score if candidates else None
        if report is not None:
            report.pre_acl_candidate_count = len(raw_candidates)
            report.authorized_candidate_count = len(candidates)
            if report.forensic_capture is not None:
                top20_metadata = metadata_for_chunks(raw_candidates)
                for item, candidate in zip(top20_metadata, raw_candidates, strict=True):
                    item["authorized"] = context.is_system or (
                        candidate.payload.get("tenant_id") == context.tenant_id
                    )
                report.forensic_capture.stage(
                    "retrieval",
                    {
                        "candidate_count": len(raw_candidates),
                        "authorized_candidate_count": len(candidates),
                        "configured_top_k": top_k,
                        "rrf_top20_observed": top20_metadata,
                    },
                )
        span.set_attribute("retrieve.raw_candidate_count", len(raw_candidates))
        span.set_attribute("retrieve.candidate_count", len(candidates))
        if candidates:
            span.set_attribute("retrieve.top_score", candidates[0].score)

    if reranker is not None:
        with tracer.start_as_current_span("rerank") as span:
            span.set_attribute("rerank.top_n", top_n)
            with stage_timer(
                report,
                "rerank",
                model=getattr(reranker, "model_name", type(reranker).__name__),
                backend=getattr(reranker, "backend", None),
                top_n=top_n,
            ) as timer:
                # CrossEncoder inference is synchronous CPU/MPS work. Keep
                # the production ordering (ACL -> retrieve -> rerank -> top_n)
                # while moving it off the event loop. The production
                # CrossEncoder exposes async_rerank(), which also bounds
                # concurrent calls on its shared model instance.
                async_rerank = getattr(reranker, "async_rerank", None)
                if async_rerank is not None:
                    results = await async_rerank(query, candidates, top_n)
                else:
                    results = await asyncio.to_thread(reranker.rerank, query, candidates, top_n)
                timer.candidates_in = len(candidates)
                timer.candidates_out = len(results)
                timer.top_score = results[0].score if results else None
            if results:
                span.set_attribute("rerank.top_score", results[0].score)
            if report is not None and report.forensic_capture is not None:
                report.forensic_capture.merge_stage(
                    "reranker",
                    {
                        "input_candidate_ids": [item.id for item in candidates],
                        "output_candidate_ids": [item.id for item in results],
                        "bge_top5_observed": metadata_for_chunks(results),
                    },
                )
        return results

    # No reranker configured — the report gets NO "rerank" stage at all
    # (rather than a zero-duration placeholder), so the UI renders the
    # pipeline that actually ran.
    with stage_timer(report, "truncate_to_top_n", top_n=top_n) as timer:
        results = candidates[:top_n]
        timer.candidates_in = len(candidates)
        timer.candidates_out = len(results)
        timer.top_score = results[0].score if results else None
    if report is not None and report.forensic_capture is not None:
        report.forensic_capture.merge_stage(
            "reranker",
            {
                "input_candidate_ids": [item.id for item in candidates],
                "output_candidate_ids": [item.id for item in results],
                "bge_top5_observed": metadata_for_chunks(results),
            },
        )
    return results
