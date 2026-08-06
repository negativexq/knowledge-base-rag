from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import EMBEDDING_DIM, SPARSE_VECTOR_NAME, VECTOR_NAME, QdrantStore
from app.retrieval.sparse import SparseVector

COLLECTION = "test_chunks"


def _store() -> QdrantStore:
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    return store


def _chunk(
    doc_id="doc1",
    source_type="pdf",
    source_id="doc1",
    page=1,
    paragraph=0,
    char_range=(0, 10),
    text="hello world",
):
    return Chunk(
        doc_id=doc_id,
        source_type=source_type,
        source_id=source_id,
        page_number=page,
        paragraph_index=paragraph,
        char_range=char_range,
        text=text,
    )


def _dense_vector(seed: float = 0.1) -> list[float]:
    return [seed] * EMBEDDING_DIM


def _sparse_vector() -> SparseVector:
    return SparseVector(indices=[1, 2, 3], values=[0.5, 0.3, 0.9])


def test_ensure_collection_creates_dense_cosine_vector_of_correct_size():
    store = _store()

    info = store._client.get_collection(COLLECTION)
    vector_params = info.config.params.vectors[VECTOR_NAME]

    assert vector_params.size == EMBEDDING_DIM
    assert vector_params.distance.name == "COSINE"


def test_ensure_collection_creates_sparse_vector_with_idf_modifier():
    store = _store()

    info = store._client.get_collection(COLLECTION)
    sparse_params = info.config.params.sparse_vectors[SPARSE_VECTOR_NAME]

    assert sparse_params.modifier == qmodels.Modifier.IDF


def test_ensure_collection_is_idempotent():
    store = _store()

    store.ensure_collection()
    store.ensure_collection()

    assert store.count() == 0


def test_ensure_collection_recreates_a_dense_only_collection_missing_sparse_vector():
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE)
        },
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()

    info = client.get_collection(COLLECTION)
    assert SPARSE_VECTOR_NAME in info.config.params.sparse_vectors


def test_upsert_chunks_writes_one_point_per_chunk_with_correct_payload():
    store = _store()
    chunk = _chunk()

    store.upsert_chunks([chunk], [_dense_vector()], [_sparse_vector()])

    assert store.count() == 1
    point = store._client.retrieve(COLLECTION, ids=[QdrantStore.point_id_for(chunk)])[0]
    assert point.payload == {
        "doc_id": chunk.doc_id,
        "source_type": chunk.source_type,
        "source_id": chunk.source_id,
        "page_number": chunk.page_number,
        "paragraph_index": chunk.paragraph_index,
        "char_range": list(chunk.char_range),
        "text": chunk.text,
    }


def test_upsert_chunks_writes_both_dense_and_sparse_vectors():
    store = _store()
    chunk = _chunk()

    store.upsert_chunks([chunk], [_dense_vector()], [_sparse_vector()])

    point = store._client.retrieve(
        COLLECTION, ids=[QdrantStore.point_id_for(chunk)], with_vectors=True
    )[0]
    # Cosine-distance collections store L2-normalized vectors, so we only
    # check direction (all components equal), not the exact raw magnitude.
    stored_dense = point.vector[VECTOR_NAME]
    assert len(stored_dense) == EMBEDDING_DIM
    assert len(set(round(v, 6) for v in stored_dense)) == 1
    assert list(point.vector[SPARSE_VECTOR_NAME].indices) == _sparse_vector().indices


def test_upserting_the_same_chunk_twice_does_not_duplicate():
    store = _store()
    chunk = _chunk()

    store.upsert_chunks([chunk], [_dense_vector()], [_sparse_vector()])
    store.upsert_chunks([chunk], [_dense_vector()], [_sparse_vector()])

    assert store.count() == 1


def test_different_chunks_produce_different_point_ids():
    chunk_a = _chunk(char_range=(0, 10))
    chunk_b = _chunk(char_range=(10, 20))

    assert QdrantStore.point_id_for(chunk_a) != QdrantStore.point_id_for(chunk_b)


def test_point_id_is_deterministic_for_same_chunk_fields():
    chunk_a = _chunk()
    chunk_b = _chunk()

    assert QdrantStore.point_id_for(chunk_a) == QdrantStore.point_id_for(chunk_b)


def test_chunks_from_different_source_types_produce_different_point_ids():
    chunk_a = _chunk(source_type="pdf")
    chunk_b = _chunk(source_type="markdown")

    assert QdrantStore.point_id_for(chunk_a) != QdrantStore.point_id_for(chunk_b)
