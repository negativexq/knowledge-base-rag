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
    # Sprint 21: defaulted for backward compatibility — every existing
    # SearchResult(score=..., payload=...) call site (production and
    # tests) keeps working unchanged. Only hybrid_search() populates and
    # relies on this, as a deterministic tie-break key — see its
    # docstring below for why this exists.
    id: str = ""


def stable_order(points: list) -> list:
    """Sorts Qdrant response points by (-score, id) — extracted as a
    pure function so the tie-break itself is directly unit-testable
    without needing a real Qdrant server to reproduce a genuine RRF
    score tie (attempted with :memory: mode; RRF's own rank-based
    fusion made even identically-scored dense/sparse candidates land on
    DIFFERENT fused scores there, since a tie requires identical rank
    in BOTH prefetches simultaneously — awkward to force reliably in a
    fast local test). `points` just needs `.score` and `.id` attributes
    — real Qdrant response points satisfy this already.
    """
    return sorted(points, key=lambda p: (-p.score, str(p.id)))


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
    # Sprint 21: Qdrant's RRF fusion genuinely does NOT guarantee a
    # stable order among points that land on the EXACT SAME fused
    # score — reproduced directly against a real server: repeating the
    # identical query (same frozen dense+sparse vectors) against an
    # unchanged collection returned scores that were byte-identical
    # every time, but the ORDER of results tied at the same score
    # shuffled between calls. Scores themselves are not the problem;
    # missing tie-breaking is. Point IDs are deterministic (uuid5 of
    # chunk identity — see QdrantStore.point_id_for), so sorting by
    # (-score, id) as a secondary key makes the final order fully
    # deterministic without changing which points are top_k or their
    # relative order for any GENUINELY different score — this only
    # resolves real ties, it never reorders non-tied results.
    points = stable_order(response.points)
    return [SearchResult(score=p.score, payload=p.payload, id=str(p.id)) for p in points]
