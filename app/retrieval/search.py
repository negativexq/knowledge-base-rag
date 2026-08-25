from typing import Protocol

from opentelemetry import trace
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.llm.provider import EmbeddingProvider
from app.retrieval.filters import build_filter
from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.retrieval.sparse import SparseVector
from app.shared.tracing import get_tracer

# Query-side counterpart to app/ingestion/ingest.py's SEARCH_DOCUMENT_PREFIX —
# nomic-embed-text requires this prefix on the *query* text for retrieval to
# work well.
SEARCH_QUERY_PREFIX = "search_query: "

# Provisional, like the chunker's chunk size — a starting assumption pending
# real signal from evaluation (Sprint 9).
RERANK_CANDIDATE_K = 20  # how many hybrid candidates to fetch before reranking
RERANK_TOP_N = 5  # how many results to return after reranking


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
    tracer = tracer or get_tracer(__name__)

    with tracer.start_as_current_span("embed_query") as span:
        span.set_attribute("embed.model", embed_model)
        dense_vector = await ollama.embed(query, model=embed_model, prefix=query_prefix)
        sparse_vector = sparse_encoder.embed_query(query)

    resolved_filters = filters or build_filter(doc_ids, source_types, source_ids, page_numbers)

    with tracer.start_as_current_span("retrieve_hybrid") as span:
        span.set_attribute("retrieve.top_k", top_k)
        candidates = hybrid_search(
            qdrant_client,
            collection_name,
            dense_vector,
            sparse_vector,
            top_k=top_k,
            filters=resolved_filters,
        )
        span.set_attribute("retrieve.candidate_count", len(candidates))
        if candidates:
            span.set_attribute("retrieve.top_score", candidates[0].score)

    if reranker is not None:
        with tracer.start_as_current_span("rerank") as span:
            span.set_attribute("rerank.top_n", top_n)
            results = reranker.rerank(query, candidates, top_n=top_n)
            if results:
                span.set_attribute("rerank.top_score", results[0].score)
        return results

    return candidates[:top_n]
