import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.ingestion.models import Chunk
from app.retrieval.sparse import SparseVector

VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
EMBEDDING_DIM = 768  # nomic-embed-text native output size, verified via /api/embeddings
_POINT_ID_NAMESPACE = uuid.UUID("f0f6f7d2-8f7d-4c3d-9c1a-6b2e6a1f9d4e")


class UnexpectedCollectionSchemaError(Exception):
    """Raised when a Qdrant collection with the configured name already
    exists but doesn't have the sparse vector this app requires — instead
    of silently deleting and recreating it (a real, irreversible
    data-loss risk if the name is misconfigured or the collection
    predates this schema and holds real data). See
    docs/sprint-12-plan.md. Fix by deleting the collection yourself if
    it's genuinely safe to, or pointing QDRANT_COLLECTION_NAME at a fresh
    name.
    """


class QdrantStore:
    def __init__(self, client: QdrantClient, collection_name: str):
        self._client = client
        self._collection_name = collection_name

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection_name):
            info = self._client.get_collection(self._collection_name)

            sparse_vectors = info.config.params.sparse_vectors or {}
            if SPARSE_VECTOR_NAME not in sparse_vectors:
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists but is missing the "
                    f"{SPARSE_VECTOR_NAME!r} sparse vector this app requires. Qdrant can't add "
                    "a named vector to an existing collection, and this collection was left "
                    "untouched rather than deleted and recreated — delete it yourself if "
                    "that's genuinely safe, or point QDRANT_COLLECTION_NAME at a fresh "
                    "collection name."
                )

            # Sprint 17: create_collection() below always sets modifier=IDF
            # explicitly, but this check previously only verified the KEY
            # existed — a collection with a sparse vector using no
            # modifier (Qdrant's own default) or a different one passed
            # silently, even though create vs. validate disagreed on what
            # "correct schema" meant.
            sparse_modifier = sparse_vectors[SPARSE_VECTOR_NAME].modifier
            if sparse_modifier != qmodels.Modifier.IDF:
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists but its "
                    f"{SPARSE_VECTOR_NAME!r} sparse vector has modifier="
                    f"{sparse_modifier!r} — this app requires modifier="
                    f"{qmodels.Modifier.IDF.name}. Left untouched rather than deleted and "
                    "recreated — delete it yourself if that's genuinely safe, or point "
                    "QDRANT_COLLECTION_NAME at a fresh collection name."
                )

            # Sprint 17: an explicit membership check before subscripting
            # — a collection with SOME sparse config but no "dense" named
            # vector at all (a real, not hypothetical, misconfiguration:
            # Qdrant collections can be sparse-only or use a different
            # dense vector name) used to raise a raw KeyError here instead
            # of UnexpectedCollectionSchemaError, breaking the "fail
            # clearly, tell the human what's wrong" contract this
            # function exists for.
            dense_vectors = info.config.params.vectors or {}
            if VECTOR_NAME not in dense_vectors:
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists but is missing the "
                    f"{VECTOR_NAME!r} dense vector this app requires. Left untouched rather "
                    "than deleted and recreated — delete it yourself if that's genuinely "
                    "safe, or point QDRANT_COLLECTION_NAME at a fresh collection name."
                )

            # Sprint 16: a collection can have the right sparse config but
            # a stale/wrong dense dimension or distance metric (e.g. left
            # over from a different embedding model) — checking only
            # sparse presence let that pass silently and fail later,
            # confusingly, at the first upsert instead of here.
            dense_params = dense_vectors[VECTOR_NAME]
            schema_mismatch = (
                dense_params.size != EMBEDDING_DIM
                or dense_params.distance != qmodels.Distance.COSINE
            )
            if schema_mismatch:
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists but its "
                    f"{VECTOR_NAME!r} dense vector is size={dense_params.size}, "
                    f"distance={dense_params.distance.name} — this app requires "
                    f"size={EMBEDDING_DIM}, distance={qmodels.Distance.COSINE.name}. Left "
                    "untouched rather than deleted and recreated — delete it yourself if "
                    "that's genuinely safe, or point QDRANT_COLLECTION_NAME at a fresh "
                    "collection name."
                )

            return

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

    def delete_by_source(self, source_type: str, source_id: str) -> None:
        """Delete EVERY point belonging to one document, identified by its
        life-of-the-document-stable (source_type, source_id) pair — not by
        doc_id, which is a content hash and changes on every edit. Used by
        sync when a document has vanished from its connector entirely (a
        real, full deletion — see docs/sprint-13-plan.md for why a
        changed-but-still-present document uses delete_stale_versions()
        instead, since Sprint 13). Safe to call when the document has no
        points yet (e.g. brand new) — deletes zero, no error.
        """
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_type", match=qmodels.MatchValue(value=source_type)
                        ),
                        qmodels.FieldCondition(
                            key="source_id", match=qmodels.MatchValue(value=source_id)
                        ),
                    ]
                )
            ),
        )

    def delete_stale_versions(self, source_type: str, source_id: str, keep_version: str) -> None:
        """Delete every point for (source_type, source_id) whose
        document_version is NOT keep_version — the cleanup half of a
        zero-downtime versioned re-index with deferred cleanup (Sprint
        13): call ONLY after the new version's chunks have been fully
        embedded and upserted, so the old version's chunks stay
        searchable until the new ones are confirmed written. Between that
        upsert and this call, both versions are simultaneously present
        and searchable — a real, disclosed tradeoff (not eliminated here;
        see docs/sprint-13-plan.md and the README's re-index section) in
        exchange for closing the data-loss window Sprint 4's delete-first
        ordering had. Safe to call when the document has no points yet —
        deletes zero, no error.
        """
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_type", match=qmodels.MatchValue(value=source_type)
                        ),
                        qmodels.FieldCondition(
                            key="source_id", match=qmodels.MatchValue(value=source_id)
                        ),
                    ],
                    must_not=[
                        qmodels.FieldCondition(
                            key="document_version", match=qmodels.MatchValue(value=keep_version)
                        ),
                    ],
                )
            ),
        )

    def delete_version(self, source_type: str, source_id: str, document_version: str) -> None:
        """Delete every point for (source_type, source_id) whose
        document_version MATCHES the given one — the mirror image of
        delete_stale_versions (which deletes everything EXCEPT one
        version). Used to roll back a partially-upserted NEW version when
        a multi-batch re-index fails partway through: earlier batches may
        already be committed under this document_version, and a plain
        re-raise without cleanup would leave those partial NEW-version
        points sitting alongside the still-intact OLD version
        indefinitely (see docs/sprint-16-plan.md). Safe to call when no
        points carry this version yet — deletes zero, no error.
        """
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_type", match=qmodels.MatchValue(value=source_type)
                        ),
                        qmodels.FieldCondition(
                            key="source_id", match=qmodels.MatchValue(value=source_id)
                        ),
                        qmodels.FieldCondition(
                            key="document_version",
                            match=qmodels.MatchValue(value=document_version),
                        ),
                    ]
                )
            ),
        )

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
    ) -> None:
        # Sprint 17: zip() silently truncates to the shortest input — a
        # caller bug producing mismatched-length lists would otherwise
        # upsert fewer points than chunks exist with no error at all.
        if not len(chunks) == len(dense_vectors) == len(sparse_vectors):
            raise ValueError(
                f"chunks, dense_vectors, and sparse_vectors must be the same length, got "
                f"{len(chunks)}, {len(dense_vectors)}, {len(sparse_vectors)}"
            )
        points = [
            self._to_point(chunk, dense_vector, sparse_vector)
            for chunk, dense_vector, sparse_vector in zip(chunks, dense_vectors, sparse_vectors)
        ]
        self._client.upsert(collection_name=self._collection_name, points=points, wait=True)

    @staticmethod
    def point_id_for(chunk: Chunk) -> str:
        # source_id (Sprint 17) is required in this key: doc_id is only a
        # content hash, so two DIFFERENT documents with byte-identical
        # content (e.g. contract-a.pdf and contract-b.pdf, duplicated
        # text) would otherwise produce the same
        # (doc_id, page, paragraph, char_range) tuple for their
        # corresponding chunks and silently collide on point ID, with the
        # second upsert overwriting the first — no error, no visible
        # duplicate, just data loss. See docs/sprint-17-plan.md.
        key = (
            f"{chunk.source_type}:{chunk.source_id}:{chunk.doc_id}:{chunk.page_number}:"
            f"{chunk.paragraph_index}:{chunk.char_range[0]}:{chunk.char_range[1]}"
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
                "heading_path": list(chunk.heading_path),
                "document_version": chunk.document_version,
            },
        )
