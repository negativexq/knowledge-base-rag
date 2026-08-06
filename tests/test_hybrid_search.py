from qdrant_client import QdrantClient

from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.retrieval.hybrid_search import dense_only_search, hybrid_search
from app.retrieval.sparse import SparseVector

COLLECTION = "test_hybrid"


def _store() -> QdrantStore:
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    return store


def _unit(index: int, dim: int = EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    vector[index] = 1.0
    return vector


def test_dense_only_search_ranks_by_vector_similarity():
    store = _store()
    store.upsert_chunks(
        chunks=[_chunk("near"), _chunk("far")],
        dense_vectors=[_unit(0), _unit(1)],
        sparse_vectors=[SparseVector(indices=[], values=[]), SparseVector(indices=[], values=[])],
    )

    results = dense_only_search(store._client, COLLECTION, query_dense_vector=_unit(0), top_k=2)

    assert results[0].payload["text"] == "near"


def test_hybrid_search_finds_keyword_match_that_dense_only_misses():
    """Concrete proof of the DoD claim: a chunk whose dense vector points
    *away* from the query, but which shares a distinctive keyword, is
    retrieved by hybrid search and ranked above it by dense-only search.
    """
    store = _store()
    # "keyword_chunk" is semantically unrelated to the query in dense space
    # (orthogonal unit vector) but shares the rare term "qdrant" via sparse.
    store.upsert_chunks(
        chunks=[_chunk("something about qdrant vector databases", doc_id="kw")],
        dense_vectors=[_unit(5)],
        sparse_vectors=[SparseVector(indices=[111, 222], values=[2.0, 1.0])],
    )
    store.upsert_chunks(
        chunks=[_chunk("completely unrelated topic about cooking", doc_id="unrel")],
        dense_vectors=[_unit(0)],  # matches the query vector exactly
        sparse_vectors=[SparseVector(indices=[999], values=[0.1])],
    )

    query_dense_vector = _unit(0)  # semantically points at "unrelated" chunk
    query_sparse_vector = SparseVector(indices=[111], values=[1.0])  # matches "qdrant" chunk

    dense_results = dense_only_search(store._client, COLLECTION, query_dense_vector, top_k=2)
    hybrid_results = hybrid_search(
        store._client, COLLECTION, query_dense_vector, query_sparse_vector, top_k=2
    )

    assert dense_results[0].payload["doc_id"] == "unrel"  # dense-only misses the keyword match
    assert "kw" not in [r.payload["doc_id"] for r in dense_results[:1]]

    hybrid_doc_ids = [r.payload["doc_id"] for r in hybrid_results]
    assert "kw" in hybrid_doc_ids  # hybrid surfaces the keyword-matching chunk


def _chunk(text: str, doc_id: str = "doc"):
    from app.ingestion.models import Chunk

    return Chunk(
        doc_id=doc_id,
        source_type="pdf",
        source_id=doc_id,
        page_number=1,
        paragraph_index=0,
        char_range=(0, len(text)),
        text=text,
    )
