"""Filter + hybrid fusion tests against a REAL Qdrant server — required
because qdrant-client's local (":memory:") mode does NOT correctly apply a
query_filter to a prefetch+FusionQuery request (confirmed: it silently
ignores the filter and returns unfiltered candidates).

Skipped automatically if Qdrant isn't reachable, so it doesn't break
CI/offline runs.
"""

import socket

import pytest
from qdrant_client import QdrantClient

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.retrieval.filters import build_filter
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.sparse import SparseVector

COLLECTION = "test_filters_e2e"


def _qdrant_up() -> bool:
    try:
        with socket.create_connection(("localhost", 6333), timeout=0.5):
            return True
    except OSError:
        return False


def _chunk(doc_id: str, page: int, text: str) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        source_type="pdf",
        source_id=doc_id,
        page_number=page,
        paragraph_index=0,
        char_range=(0, 1),
        text=text,
    )


def _dense_vector(near_query: bool) -> list[float]:
    # doc "other" is deliberately made to score *higher* on the dense side
    # than doc "target", so a naive (unfiltered) search would rank it first.
    v = [0.0] * EMBEDDING_DIM
    v[0] = 1.0 if near_query else 0.9
    v[1] = 0.0 if near_query else 0.1
    return v


@pytest.mark.skipif(not _qdrant_up(), reason="requires real Qdrant on :6333")
def test_filtered_and_unfiltered_search_return_different_correct_result_sets():
    client = QdrantClient(url="http://localhost:6333")
    client.delete_collection(COLLECTION)
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()

    target_chunk = _chunk("target-doc", page=1, text="the answer is in the target document")
    other_chunks = [_chunk("other-doc", page=i, text=f"other document chunk {i}") for i in range(5)]

    store.upsert_chunks(
        [target_chunk],
        [_dense_vector(near_query=False)],
        [SparseVector(indices=[1], values=[1.0])],
    )
    store.upsert_chunks(
        other_chunks,
        [_dense_vector(near_query=True)] * len(other_chunks),
        [SparseVector(indices=[2], values=[1.0])] * len(other_chunks),
    )

    query_dense = _dense_vector(near_query=True)
    query_sparse = SparseVector(indices=[1], values=[1.0])  # only matches target-doc

    unfiltered = hybrid_search(client, COLLECTION, query_dense, query_sparse, top_k=10)
    filtered = hybrid_search(
        client,
        COLLECTION,
        query_dense,
        query_sparse,
        top_k=10,
        filters=build_filter(doc_ids=["other-doc"]),
    )

    unfiltered_doc_ids = {r.payload["doc_id"] for r in unfiltered}
    filtered_doc_ids = {r.payload["doc_id"] for r in filtered}

    assert "target-doc" in unfiltered_doc_ids  # sparse match surfaces it when unfiltered
    assert filtered_doc_ids == {"other-doc"}  # filter excludes target-doc entirely
    assert unfiltered_doc_ids != filtered_doc_ids  # concrete, different, correct result sets

    client.delete_collection(COLLECTION)
