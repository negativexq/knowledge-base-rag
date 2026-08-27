"""Static/runtime checks for an isolated Evaluation Corpus v2 Qdrant index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.ingestion.qdrant_store import VECTOR_NAME


class EvaluationIndexMismatchError(RuntimeError):
    """Raised before a benchmark can use an unverified Qdrant collection."""


def _scroll_points(client: QdrantClient, collection: str) -> list[Any]:
    points: list[Any] = []
    offset = None
    while True:
        page, offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(page)
        if offset is None:
            return points


def validate_evaluation_index(
    client: QdrantClient,
    collection: str,
    manifest_path: Path,
    validation_path: Path | None,
    expected_corpus_fingerprint: str,
    expected_dimension: int = 1024,
) -> dict[str, Any]:
    """Fail closed unless collection, artifact, payloads, and dimensions agree."""
    if not client.collection_exists(collection):
        raise EvaluationIndexMismatchError(f"evaluation collection does not exist: {collection}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_documents = manifest["documents"]
    expected_sources = {document["source_id"] for document in manifest_documents}
    if validation_path is not None:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        if validation.get("collection") != collection:
            raise EvaluationIndexMismatchError(
                "index validation artifact collection does not match"
            )
        if validation.get("corpus_fingerprint") != expected_corpus_fingerprint:
            raise EvaluationIndexMismatchError(
                "index validation artifact corpus fingerprint does not match canonical corpus"
            )
        if validation.get("source_count") != len(expected_sources):
            raise EvaluationIndexMismatchError("index validation artifact source count is stale")

    info = client.get_collection(collection)
    vectors = info.config.params.vectors or {}
    dense = vectors.get(VECTOR_NAME) if isinstance(vectors, dict) else None
    if dense is None or dense.size != expected_dimension:
        actual = getattr(dense, "size", None)
        raise EvaluationIndexMismatchError(
            f"evaluation collection dense dimension mismatch: expected {expected_dimension}, "
            f"got {actual}"
        )

    points = _scroll_points(client, collection)
    indexed_sources = set()
    indexed_tenants = set()
    for point in points:
        payload = point.payload or {}
        source_id = payload.get("source_id")
        tenant_id = payload.get("tenant_id")
        if not source_id:
            raise EvaluationIndexMismatchError("indexed point is missing source_id metadata")
        if not tenant_id:
            raise EvaluationIndexMismatchError(
                f"indexed source {source_id!r} is missing tenant_id metadata"
            )
        indexed_sources.add(source_id)
        indexed_tenants.add(tenant_id)

    if indexed_sources != expected_sources:
        raise EvaluationIndexMismatchError(
            f"indexed sources do not match manifest: expected {sorted(expected_sources)}, "
            f"got {sorted(indexed_sources)}"
        )

    return {
        "collection": collection,
        "corpus_fingerprint": expected_corpus_fingerprint,
        "source_count": len(indexed_sources),
        "chunk_count": len(points),
        "tenant_ids": sorted(indexed_tenants),
        "dense_dimension": expected_dimension,
    }
