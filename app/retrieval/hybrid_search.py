from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ingestion.qdrant_store import SPARSE_VECTOR_NAME, VECTOR_NAME
from app.retrieval.sparse import SparseVector

DEFAULT_TOP_K = 5
DEFAULT_PREFETCH_LIMIT = 20


@dataclass(frozen=True)
class SearchResult:
    score: float
    payload: dict


def dense_only_search(
    client: QdrantClient,
    collection_name: str,
    query_dense_vector: list[float],
    top_k: int = DEFAULT_TOP_K,
    filters: qmodels.Filter | None = None,
) -> list[SearchResult]:
    response = client.query_points(
        collection_name=collection_name,
        query=query_dense_vector,
        using=VECTOR_NAME,
        limit=top_k,
        query_filter=filters,
        with_payload=True,
    )
    return [SearchResult(score=p.score, payload=p.payload) for p in response.points]


def hybrid_search(
    client: QdrantClient,
    collection_name: str,
    query_dense_vector: list[float],
    query_sparse_vector: SparseVector,
    top_k: int = DEFAULT_TOP_K,
    prefetch_limit: int = DEFAULT_PREFETCH_LIMIT,
    filters: qmodels.Filter | None = None,
) -> list[SearchResult]:
    # A single top-level query_filter is pushed down into each Prefetch's
    # candidate selection against a real Qdrant server, not just applied
    # after fusion. NOTE: qdrant-client's local (":memory:") mode does NOT
    # reproduce this — it drops the filter entirely for prefetch+fusion
    # queries, so any test exercising this must run against a real server.
    response = client.query_points(
        collection_name=collection_name,
        prefetch=[
            qmodels.Prefetch(query=query_dense_vector, using=VECTOR_NAME, limit=prefetch_limit),
            qmodels.Prefetch(
                query=qmodels.SparseVector(
                    indices=query_sparse_vector.indices, values=query_sparse_vector.values
                ),
                using=SPARSE_VECTOR_NAME,
                limit=prefetch_limit,
            ),
        ],
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=top_k,
        query_filter=filters,
        with_payload=True,
    )
    return [SearchResult(score=p.score, payload=p.payload) for p in response.points]
