from app.retrieval.sparse import SparseEncoder


def test_embed_document_is_deterministic():
    encoder = SparseEncoder()

    first = encoder.embed_document("hybrid search combines dense and sparse vectors")
    second = encoder.embed_document("hybrid search combines dense and sparse vectors")

    assert first.indices == second.indices
    assert first.values == second.values


def test_embed_document_produces_nonempty_sparse_vector():
    encoder = SparseEncoder()

    vector = encoder.embed_document("hybrid search combines dense and sparse vectors")

    assert len(vector.indices) > 0
    assert len(vector.indices) == len(vector.values)


def test_embed_query_uses_presence_only_weights():
    encoder = SparseEncoder()

    vector = encoder.embed_query("hybrid search")

    assert all(value == 1.0 for value in vector.values)


def test_shared_vocabulary_terms_produce_overlapping_indices():
    encoder = SparseEncoder()

    doc_vector = encoder.embed_document("the reranker improves retrieval quality")
    query_vector = encoder.embed_query("reranker quality")

    assert set(query_vector.indices) & set(doc_vector.indices)
