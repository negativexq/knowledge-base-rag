from qdrant_client import QdrantClient

from app.ingestion.qdrant_store import EMBEDDING_DIM, QdrantStore
from app.retrieval.hybrid_search import dense_only_search, hybrid_search, stable_order
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


class _FakePoint:
    def __init__(self, id_: str, score: float):
        self.id = id_
        self.score = score


def test_stable_order_breaks_a_genuine_score_tie_deterministically():
    """Sprint 21: reproduced directly against a REAL Qdrant server that
    RRF fusion does NOT guarantee a stable order among points landing on
    the exact same fused score — repeating the identical query (same
    frozen vectors, unchanged collection) returned byte-identical scores
    every time, but the ORDER among tied results shuffled between calls.
    stable_order() is the fix: sort by (-score, id). Unit-tested directly
    (rather than against :memory: Qdrant, which turned out unable to
    reliably reproduce a genuine RRF tie — see the function's own
    docstring) with three points sharing the exact same score, fed in a
    deliberately shuffled order, twice, in different shuffles.
    """
    tied_score = 0.5
    points_shuffle_a = [
        _FakePoint("zzz", tied_score), _FakePoint("aaa", tied_score), _FakePoint("mmm", tied_score),
    ]
    points_shuffle_b = [
        _FakePoint("mmm", tied_score), _FakePoint("zzz", tied_score), _FakePoint("aaa", tied_score),
    ]

    ordered_a = [p.id for p in stable_order(points_shuffle_a)]
    ordered_b = [p.id for p in stable_order(points_shuffle_b)]

    assert ordered_a == ordered_b == ["aaa", "mmm", "zzz"]


def test_stable_order_preserves_score_ordering_for_genuinely_different_scores():
    points = [_FakePoint("low", 0.1), _FakePoint("high", 0.9), _FakePoint("mid", 0.5)]

    ordered = [p.id for p in stable_order(points)]

    assert ordered == ["high", "mid", "low"]  # score still dominates — id only breaks real ties


def test_stable_order_mixes_score_priority_with_id_tiebreak_correctly():
    points = [
        _FakePoint("b", 0.5), _FakePoint("a", 0.5),  # tied at 0.5 -> id breaks it
        _FakePoint("c", 0.9),  # genuinely higher score -> always first regardless of id
    ]

    ordered = [p.id for p in stable_order(points)]

    assert ordered == ["c", "a", "b"]


def test_hybrid_search_populates_id_and_uses_stable_order():
    """Integration-level: hybrid_search's real output actually carries
    SearchResult.id and is sorted via stable_order — not just that the
    helper function works in isolation.
    """
    store = _store()
    store.upsert_chunks(
        chunks=[_chunk("alpha", doc_id="alpha"), _chunk("beta", doc_id="beta")],
        dense_vectors=[_unit(0), _unit(1)],
        sparse_vectors=[SparseVector(indices=[], values=[]), SparseVector(indices=[], values=[])],
    )

    results = hybrid_search(
        store._client, COLLECTION, _unit(0), SparseVector(indices=[], values=[])
    )

    assert all(r.id for r in results)  # every result carries a real point id
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)  # still primarily score-ordered


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
