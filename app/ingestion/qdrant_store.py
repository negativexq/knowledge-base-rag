import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ingestion.models import Chunk
from app.retrieval.sparse import SparseVector

VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
EMBEDDING_DIM = 768  # nomic-embed-text native output size, verified via /api/embeddings
_POINT_ID_NAMESPACE = uuid.UUID("f0f6f7d2-8f7d-4c3d-9c1a-6b2e6a1f9d4e")


class QdrantStore:
    def __init__(self, client: QdrantClient, collection_name: str):
        self._client = client
        self._collection_name = collection_name

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection_name):
            info = self._client.get_collection(self._collection_name)
            if SPARSE_VECTOR_NAME in (info.config.params.sparse_vectors or {}):
                return
            # Qdrant can't add a named vector to an existing collection —
            # recreate it. Safe here because dev collections are re-ingestable.
            self._client.delete_collection(self._collection_name)

        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config={
                VECTOR_NAME: qmodels.VectorParams(
                    size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                    modifier=qmodels.Modifier.IDF,
                )
            },
        )

    def count(self) -> int:
        return self._client.count(self._collection_name, exact=True).count

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
    ) -> None:
        points = [
            self._to_point(chunk, dense_vector, sparse_vector)
            for chunk, dense_vector, sparse_vector in zip(chunks, dense_vectors, sparse_vectors)
        ]
        self._client.upsert(collection_name=self._collection_name, points=points, wait=True)

    @staticmethod
    def point_id_for(chunk: Chunk) -> str:
        key = (
            f"{chunk.source_type}:{chunk.doc_id}:{chunk.page_number}:{chunk.paragraph_index}:"
            f"{chunk.char_range[0]}:{chunk.char_range[1]}"
        )
        return str(uuid.uuid5(_POINT_ID_NAMESPACE, key))

    def _to_point(
        self,
        chunk: Chunk,
        dense_vector: list[float],
        sparse_vector: SparseVector,
    ) -> qmodels.PointStruct:
        return qmodels.PointStruct(
            id=self.point_id_for(chunk),
            vector={
                VECTOR_NAME: dense_vector,
                SPARSE_VECTOR_NAME: qmodels.SparseVector(
                    indices=sparse_vector.indices, values=sparse_vector.values
                ),
            },
            payload={
                "doc_id": chunk.doc_id,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "page_number": chunk.page_number,
                "paragraph_index": chunk.paragraph_index,
                "char_range": list(chunk.char_range),
                "text": chunk.text,
            },
        )
