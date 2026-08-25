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
    def __init__(
        self, client: QdrantClient, collection_name: str, dense_dimension: int = EMBEDDING_DIM
    ):
        # Sprint 18: parameterized so a benchmark collection can use a
        # different embedding model's real output dimension (e.g.
        # Qwen3-Embedding-4B) without touching the production default —
        # every existing call site omits this and gets EMBEDDING_DIM
        # (nomic's 768), unchanged.
        self._client = client
        self._collection_name = collection_name
        self._dense_dimension = dense_dimension

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

            # Sprint 17.1: Qdrant supports a collection with a single
            # UNNAMED vector (vectors_config=VectorParams(...) passed
            # directly, not wrapped in a {name: ...} dict) — in that case
            # info.config.params.vectors is a VectorParams OBJECT, not a
            # dict. `VECTOR_NAME not in dense_vectors` below wouldn't
            # crash on that today, but only by accident: Pydantic
            # BaseModel supports __iter__ (yielding (field, value)
            # pairs), so Python's `in` falls back to that and always
            # returns False — coincidentally landing on the right
            # exception type, but for the wrong reason, relying on
            # undocumented behavior a future Pydantic/qdrant-client
            # version is free to change. This app always requires a
            # NAMED dense vector (so it can coexist with the named
            # sparse vector in the same collection) — state that
            # explicitly instead.
            dense_vectors = info.config.params.vectors or {}
            if not isinstance(dense_vectors, dict):
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists with an unnamed "
                    f"(single) dense vector configuration — this app requires a NAMED dense "
                    f"vector called {VECTOR_NAME!r} so it can coexist with the named sparse "
                    "vector in the same collection. Left untouched rather than deleted and "
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
                dense_params.size != self._dense_dimension
                or dense_params.distance != qmodels.Distance.COSINE
            )
            if schema_mismatch:
                raise UnexpectedCollectionSchemaError(
                    f"Collection {self._collection_name!r} already exists but its "
                    f"{VECTOR_NAME!r} dense vector is size={dense_params.size}, "
                    f"distance={dense_params.distance.name} — this app requires "
                    f"size={self._dense_dimension}, distance={qmodels.Distance.COSINE.name}. "
                    "Left untouched rather than deleted and recreated — delete it yourself if "
                    "that's genuinely safe, or point QDRANT_COLLECTION_NAME at a fresh "
                    "collection name."
                )

            return

        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config={
                VECTOR_NAME: qmodels.VectorParams(
                    size=self._dense_dimension, distance=qmodels.Distance.COSINE
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                    modifier=qmodels.Modifier.IDF,
                )
            },
        )

        # Sprint 17.3: every filtered query this app makes
        # (delete_by_source, delete_stale_versions, delete_version,
        # has_document_version, count_for_document_version,
        # list_point_ids_for_version, list_source_ids) filters on some
        # combination of exactly these three payload fields, and
        # Sprint 17.2's reconciliation logic measurably increased how
        # often those queries run (once per unchanged document, every
        # sync). Only applied to a BRAND NEW collection — an existing
        # collection that already passed schema validation above is
        # never mutated here, consistent with this function's "don't
        # touch an existing collection" policy elsewhere. No query-
        # latency benchmark was run against real Qdrant this sprint;
        # see docs/sprint-17-3-plan.md for the reasoning.
        # Sprint 23: tenant_id joins this list — it's now the single
        # most-filtered field in the collection (build_acl_filter adds
        # it to EVERY retrieval call, not just maintenance queries).
        for field_name in ("tenant_id", "source_type", "source_id", "document_version"):
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

    def count(self) -> int:
        return self._client.count(self._collection_name, exact=True).count

    def has_document_version(
        self, tenant_id: str, source_type: str, source_id: str, document_version: str
    ) -> bool:
        """Cheap presence check: does at least one point exist for this
        (tenant_id, source_type, source_id, document_version)? A limit=1
        scroll, not an exact count — used by ingest_connector (Sprint
        17.2) to detect registry/Qdrant drift: a document whose
        content_hash hasn't changed can still have had its Qdrant points
        disappear by some means other than this app's own delete calls
        (manual deletion, external tooling, data loss) while the
        registry has no way to notice on its own. See
        docs/sprint-17-2-plan.md. tenant_id (Sprint 23) is part of every
        one of these lookups so a query for one tenant's document can
        never observe another tenant's points, even if they somehow
        shared a (source_type, source_id) pair.
        """
        points, _ = self._client.scroll(
            collection_name=self._collection_name,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                    ),
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
            ),
            limit=1,
        )
        return len(points) > 0

    def count_for_document_version(
        self, tenant_id: str, source_type: str, source_id: str, document_version: str
    ) -> int:
        """Exact count of points for this (tenant_id, source_type,
        source_id, document_version) — more expensive than
        has_document_version (a real count query, not a bounded presence
        scroll). Used (Sprint 17.2 bonus) to detect PARTIAL index loss —
        some but not all of a multi-chunk document's points missing —
        which a plain presence check can't distinguish from a
        fully-intact index.
        """
        return self._client.count(
            collection_name=self._collection_name,
            count_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                    ),
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
            ),
            exact=True,
        ).count

    def list_point_ids_for_version(
        self, tenant_id: str, source_type: str, source_id: str, document_version: str
    ) -> set[str]:
        """Every point ID currently present for this (tenant_id,
        source_type, source_id, document_version) — the primitive Sprint
        17.3's duplicate-point cleanup is built on: delete_stale_versions
        only removes points whose document_version DIFFERS from a kept
        version, so points that already share the CURRENT version (a
        stale point-ID-scheme leftover, or any other source of
        same-version duplicates — see docs/sprint-17-3-plan.md) are
        invisible to it. Comparing this set against the point IDs a
        fresh chunk+embed pass actually expects (point_id_for) is what
        surfaces those duplicates so they can be deleted explicitly.
        Paginated (a real collection can hold many points per document).
        """
        ids: set[str] = set()
        offset = None
        scroll_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                ),
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
        while True:
            points, offset = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=scroll_filter,
                limit=1000,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            ids.update(str(p.id) for p in points)
            if offset is None:
                break
        return ids

    def delete_points(self, point_ids: list[str]) -> None:
        """Delete specific points by ID — used (Sprint 17.3) to remove
        unexpected same-version duplicates that delete_stale_versions
        can't reach. A no-op for an empty list (Qdrant's delete API
        accepts an empty PointIdsList without error, but this avoids
        even making the call).
        """
        if not point_ids:
            return
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.PointIdsList(points=list(point_ids)),
        )

    def list_source_ids(self, tenant_id: str, source_type: str) -> set[str]:
        """Every distinct source_id currently present in Qdrant for this
        (tenant_id, source_type) — used (Sprint 17.3) to find documents
        whose points exist in Qdrant but whose registry row is gone
        entirely (a reset/lost registry, a partial restore), which the
        registry-only deletion loop in ingest_connector can't see on its
        own. Paginated (a real collection can hold many points per
        document, and many documents per source_type). Scoped by
        tenant_id (Sprint 23) so this drift-detection scan can never
        surface (and therefore never trigger deletion of) another
        tenant's documents.
        """
        ids: set[str] = set()
        offset = None
        scroll_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                ),
                qmodels.FieldCondition(
                    key="source_type", match=qmodels.MatchValue(value=source_type)
                ),
            ]
        )
        while True:
            points, offset = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=scroll_filter,
                limit=1000,
                offset=offset,
                with_payload=["source_id"],
                with_vectors=False,
            )
            ids.update(p.payload["source_id"] for p in points)
            if offset is None:
                break
        return ids

    def delete_by_source(self, tenant_id: str, source_type: str, source_id: str) -> None:
        """Delete EVERY point belonging to one document, identified by its
        life-of-the-document-stable (tenant_id, source_type, source_id)
        triple — not by doc_id, which is a content hash and changes on
        every edit. Used by sync when a document has vanished from its
        connector entirely (a real, full deletion — see
        docs/sprint-13-plan.md for why a changed-but-still-present
        document uses delete_stale_versions() instead, since Sprint 13).
        Safe to call when the document has no points yet (e.g. brand
        new) — deletes zero, no error. tenant_id (Sprint 23) guards
        against this ever deleting another tenant's points that happen
        to share a (source_type, source_id) pair.
        """
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                        ),
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

    def delete_stale_versions(
        self, tenant_id: str, source_type: str, source_id: str, keep_version: str
    ) -> None:
        """Delete every point for (tenant_id, source_type, source_id)
        whose document_version is NOT keep_version — the cleanup half of
        a zero-downtime versioned re-index with deferred cleanup (Sprint
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
                            key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                        ),
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

    def delete_version(
        self, tenant_id: str, source_type: str, source_id: str, document_version: str
    ) -> None:
        """Delete every point for (tenant_id, source_type, source_id)
        whose document_version MATCHES the given one — the mirror image
        of delete_stale_versions (which deletes everything EXCEPT one
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
                            key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                        ),
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
        #
        # Sprint 23: tenant_id is prepended for the exact same reason —
        # without it, tenant A's "handbook.pdf" chunk 1 and tenant B's
        # "handbook.pdf" chunk 1 (identical source_type/source_id/doc_id/
        # page/paragraph/char_range, a real possibility once two tenants
        # share a source_type) would collide on point ID, and the second
        # tenant's upsert would silently overwrite the first's point —
        # cross-tenant data loss, not just a citation bug.
        key = (
            f"{chunk.tenant_id}:{chunk.source_type}:{chunk.source_id}:{chunk.doc_id}:"
            f"{chunk.page_number}:{chunk.paragraph_index}:{chunk.char_range[0]}:"
            f"{chunk.char_range[1]}"
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
                # Sprint 23: tenant_id/visibility are the ACL payload
                # fields app/retrieval/filters.py::build_acl_filter and
                # app/security/models.py::RetrievalContext enforce
                # against at retrieval time — mandatory, not optional
                # metadata. "visibility" defaults to "tenant" (shared
                # within the owning tenant); a future "private" value
                # would need an allowed_user_ids-style condition too,
                # not added here since nothing in this app produces
                # private-visibility chunks yet — see docs/security.md's
                # known limitations.
                "tenant_id": chunk.tenant_id,
                "visibility": "tenant",
                "doc_id": chunk.doc_id,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "page_number": chunk.page_number,
                "paragraph_index": chunk.paragraph_index,
                "char_range": list(chunk.char_range),
                "text": chunk.text,
                "heading_path": list(chunk.heading_path),
                "heading_occurrence": chunk.heading_occurrence,
                "document_version": chunk.document_version,
            },
        )
