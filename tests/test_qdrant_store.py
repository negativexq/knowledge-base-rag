import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import (
    EMBEDDING_DIM,
    SPARSE_VECTOR_NAME,
    VECTOR_NAME,
    QdrantStore,
    UnexpectedCollectionSchemaError,
)
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
    document_version=None,
):
    return Chunk(
        doc_id=doc_id,
        source_type=source_type,
        source_id=source_id,
        page_number=page,
        paragraph_index=paragraph,
        char_range=char_range,
        text=text,
        document_version=document_version if document_version is not None else doc_id,
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


def test_ensure_collection_fails_fast_on_schema_mismatch_without_deleting_it():
    """A collection missing the sparse vector this app requires must NOT be
    silently deleted and recreated — that's a real, irreversible data-loss
    risk if the collection name is misconfigured or predates this schema
    and holds real data. See docs/sprint-12-plan.md.
    """
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE)
        },
    )
    client.upsert(
        COLLECTION,
        points=[qmodels.PointStruct(id=1, vector={VECTOR_NAME: _dense_vector()}, payload={})],
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    with pytest.raises(UnexpectedCollectionSchemaError, match=COLLECTION):
        store.ensure_collection()

    info = client.get_collection(COLLECTION)
    assert not (info.config.params.sparse_vectors or {})  # still dense-only, untouched
    assert client.count(COLLECTION, exact=True).count == 1  # the point wasn't wiped


def test_ensure_collection_fails_fast_on_wrong_dense_vector_size():
    """Sprint 16: a collection with the right sparse config but a stale or
    wrong dense dimension (e.g. left over from a different embedding
    model) used to pass ensure_collection() silently and only fail later,
    confusingly, at the first upsert.
    """
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()},
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    with pytest.raises(UnexpectedCollectionSchemaError, match=COLLECTION):
        store.ensure_collection()


def test_ensure_collection_fails_fast_on_wrong_distance_metric():
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.EUCLID)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()},
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    with pytest.raises(UnexpectedCollectionSchemaError, match=COLLECTION):
        store.ensure_collection()


def test_ensure_collection_accepts_correct_dense_and_sparse_schema():
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE)
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(modifier=qmodels.Modifier.IDF)
        },
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    store.ensure_collection()  # must not raise


def test_ensure_collection_fails_fast_when_vector_name_missing_entirely():
    """Sprint 17: before this, accessing
    info.config.params.vectors[VECTOR_NAME] with no membership check
    raised a raw KeyError instead of UnexpectedCollectionSchemaError when
    a collection had SOME sparse config but no "dense" named vector at
    all — breaking the "fail clearly, tell the human what's wrong"
    contract this function exists for.
    """
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            "not_dense": qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE)
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(modifier=qmodels.Modifier.IDF)
        },
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    with pytest.raises(UnexpectedCollectionSchemaError, match=COLLECTION):
        store.ensure_collection()


def test_ensure_collection_fails_fast_when_sparse_modifier_is_not_idf():
    """Sprint 17: the sparse check previously only verified the KEY
    existed, never that its modifier was actually IDF — even though
    create_collection() always sets IDF explicitly, so the two code
    paths (create vs. validate) didn't agree on what "correct schema"
    meant. A collection with a sparse vector using no modifier (Qdrant's
    own default) or a different one now fails fast instead of passing
    silently.
    """
    client = QdrantClient(":memory:")
    client.create_collection(
        COLLECTION,
        vectors_config={
            VECTOR_NAME: qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE)
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()},  # no modifier
    )

    store = QdrantStore(client=client, collection_name=COLLECTION)

    with pytest.raises(UnexpectedCollectionSchemaError, match=COLLECTION):
        store.ensure_collection()


def test_upsert_chunks_rejects_mismatched_length_inputs():
    """Sprint 17: upsert_chunks zipped chunks/dense_vectors/sparse_vectors
    with no length check — zip() silently truncates to the shortest
    input, so a caller bug (an off-by-one in a future batching change, a
    partial embed result) would silently upsert fewer points than chunks
    exist, with no error anywhere to catch it before it reached
    production data.
    """
    store = _store()
    chunk_a = _chunk(char_range=(0, 10))
    chunk_b = _chunk(char_range=(10, 20))

    with pytest.raises(ValueError, match="2.*1|1.*2"):
        store.upsert_chunks([chunk_a, chunk_b], [_dense_vector()], [_sparse_vector()])

    assert store.count() == 0  # nothing partially written


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
        "heading_path": list(chunk.heading_path),
        "document_version": chunk.document_version,
    }


def test_upsert_chunks_stores_heading_path_for_a_markdown_chunk():
    store = _store()
    chunk = Chunk(
        doc_id="doc1",
        source_type="markdown",
        source_id="readme",
        page_number=0,
        paragraph_index=0,
        char_range=(0, 10),
        text="hello world",
        heading_path=("Kurulum", "Adım 1"),
    )

    store.upsert_chunks([chunk], [_dense_vector()], [_sparse_vector()])

    point = store._client.retrieve(COLLECTION, ids=[QdrantStore.point_id_for(chunk)])[0]
    assert point.payload["heading_path"] == ["Kurulum", "Adım 1"]


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


def test_chunks_from_different_source_ids_produce_different_point_ids_even_with_same_doc_id():
    """Sprint 17: two different documents (e.g. contract-a.pdf and
    contract-b.pdf) that happen to have byte-identical content produce
    the same doc_id (content hash) — before this fix, point_id_for's key
    didn't include source_id, so their corresponding chunks collided on
    point ID and the second upsert silently overwrote the first.
    """
    chunk_a = _chunk(doc_id="same-hash", source_id="contract-a")
    chunk_b = _chunk(doc_id="same-hash", source_id="contract-b")

    assert QdrantStore.point_id_for(chunk_a) != QdrantStore.point_id_for(chunk_b)


def test_delete_by_source_removes_all_points_for_that_document():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(source_id="doc1", char_range=(0, 10)),
            _chunk(source_id="doc1", char_range=(10, 20)),
        ],
        [_dense_vector(), _dense_vector()],
        [_sparse_vector(), _sparse_vector()],
    )

    store.delete_by_source("pdf", "doc1")

    assert store.count() == 0


def test_delete_by_source_does_not_touch_other_documents():
    """Sprint 17: this test used to rely on _chunk()'s default doc_id
    ("doc1") for BOTH calls, so the two chunks collided on point ID
    before point_id_for included source_id — upsert_chunks silently wrote
    only ONE point, and the post-deletion `count() == 1` assertion
    passed for the wrong reason (there was only ever one point, not two
    independent documents where one survived). Explicit distinct doc_ids
    here make the "2 documents, 1 deleted, 1 survives" story actually
    true.
    """
    store = _store()
    store.upsert_chunks(
        [
            _chunk(doc_id="doc1-hash", source_id="doc1"),
            _chunk(doc_id="doc2-hash", source_id="doc2"),
        ],
        [_dense_vector(), _dense_vector()],
        [_sparse_vector(), _sparse_vector()],
    )
    assert store.count() == 2  # sanity: both documents really did land as separate points

    store.delete_by_source("pdf", "doc1")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_id"] == "doc2"


def test_two_documents_with_the_same_doc_id_and_coordinates_but_different_source_id_both_upsert():
    """The Sprint 17 fix, proven end to end at the upsert_chunks level:
    two chunks that share doc_id AND page/paragraph/char_range (the
    byte-identical-content scenario) but have different source_id must
    both actually land in Qdrant — not one silently overwriting the
    other. count() == 2 is asserted BEFORE any deletion happens, which
    is the exact assertion that was missing before and let the original
    collision bug hide undetected.
    """
    store = _store()
    chunk_a = _chunk(doc_id="same-hash", source_id="contract-a", text="text from contract a")
    chunk_b = _chunk(doc_id="same-hash", source_id="contract-b", text="text from contract b")

    store.upsert_chunks(
        [chunk_a, chunk_b], [_dense_vector(), _dense_vector()], [_sparse_vector(), _sparse_vector()]
    )

    assert store.count() == 2  # the critical assertion the original bug's test never made

    store.delete_by_source("pdf", "contract-a")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_id"] == "contract-b"
    assert remaining[0].payload["text"] == "text from contract b"


def test_delete_by_source_does_not_touch_a_different_source_type_with_the_same_source_id():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(source_type="pdf", source_id="readme"),
            _chunk(source_type="markdown", source_id="readme"),
        ],
        [_dense_vector(), _dense_vector()],
        [_sparse_vector(), _sparse_vector()],
    )

    store.delete_by_source("pdf", "readme")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_type"] == "markdown"


def test_delete_stale_versions_removes_only_the_old_version():
    store = _store()
    store.upsert_chunks(
        [_chunk(doc_id="v1", source_id="doc1", char_range=(0, 10), text="old text")],
        [_dense_vector()],
        [_sparse_vector()],
    )
    store.upsert_chunks(
        [_chunk(doc_id="v2", source_id="doc1", char_range=(0, 10), text="new text")],
        [_dense_vector()],
        [_sparse_vector()],
    )
    assert store.count() == 2  # sanity: both versions coexist before cleanup

    store.delete_stale_versions("pdf", "doc1", keep_version="v2")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["document_version"] == "v2"
    assert remaining[0].payload["text"] == "new text"


def test_delete_stale_versions_does_not_touch_other_documents():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(doc_id="v1", source_id="doc1"),
            _chunk(doc_id="v2", source_id="doc1"),
            _chunk(doc_id="unrelated", source_id="doc2"),
        ],
        [_dense_vector()] * 3,
        [_sparse_vector()] * 3,
    )

    store.delete_stale_versions("pdf", "doc1", keep_version="v2")

    assert store.count() == 2
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert {p.payload["source_id"] for p in remaining} == {"doc1", "doc2"}


def test_delete_stale_versions_does_not_touch_a_different_source_type_with_the_same_source_id():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(doc_id="v1", source_type="pdf", source_id="readme"),
            _chunk(doc_id="v2", source_type="markdown", source_id="readme"),
        ],
        [_dense_vector(), _dense_vector()],
        [_sparse_vector(), _sparse_vector()],
    )

    store.delete_stale_versions("pdf", "readme", keep_version="some-other-version")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_type"] == "markdown"


def test_delete_stale_versions_on_a_document_with_no_points_is_a_no_op():
    store = _store()
    store.delete_stale_versions("pdf", "never-existed", keep_version="v1")  # must not raise
    assert store.count() == 0


def test_delete_version_removes_only_points_with_the_given_version():
    store = _store()
    store.upsert_chunks(
        [_chunk(doc_id="v1", source_id="doc1", char_range=(0, 10), text="old text")],
        [_dense_vector()],
        [_sparse_vector()],
    )
    store.upsert_chunks(
        [_chunk(doc_id="v2", source_id="doc1", char_range=(0, 10), text="new text")],
        [_dense_vector()],
        [_sparse_vector()],
    )
    assert store.count() == 2  # sanity: both versions coexist before rollback

    store.delete_version("pdf", "doc1", document_version="v2")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["document_version"] == "v1"
    assert remaining[0].payload["text"] == "old text"


def test_delete_version_does_not_touch_other_documents():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(doc_id="v1", source_id="doc1"),
            _chunk(doc_id="v1", source_id="doc2"),
        ],
        [_dense_vector()] * 2,
        [_sparse_vector()] * 2,
    )

    store.delete_version("pdf", "doc1", document_version="v1")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_id"] == "doc2"


def test_delete_version_does_not_touch_a_different_source_type_with_the_same_source_id():
    store = _store()
    store.upsert_chunks(
        [
            _chunk(doc_id="v1", source_type="pdf", source_id="readme"),
            _chunk(doc_id="v1", source_type="markdown", source_id="readme"),
        ],
        [_dense_vector(), _dense_vector()],
        [_sparse_vector(), _sparse_vector()],
    )

    store.delete_version("pdf", "readme", document_version="v1")

    assert store.count() == 1
    remaining, _ = store._client.scroll(COLLECTION, limit=10)
    assert remaining[0].payload["source_type"] == "markdown"


def test_delete_version_on_a_document_with_no_points_is_a_no_op():
    store = _store()
    store.delete_version("pdf", "never-existed", document_version="v1")  # must not raise
    assert store.count() == 0


def test_delete_by_source_on_a_document_with_no_points_is_a_no_op():
    store = _store()

    store.delete_by_source("pdf", "never-existed")  # must not raise

    assert store.count() == 0
