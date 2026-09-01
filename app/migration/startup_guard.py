"""Sprint 22 section 22: fail-fast protection against serving with a
configured embedding dimension that doesn't match what's actually in the
active Qdrant collection — e.g. EMBEDDING_MODEL_KEY/EMBEDDING_OUTPUT_
DIMENSION in .env say qwen3-4b@1024 but the alias/collection actually in
use is still 768-dimensional nomic data (a migration was never run, or
.env was edited without running one). Silently serving that would mean
every query embeds at 1024 dims against a 768-dim collection — Qdrant
itself would reject the search outright, but with a confusing low-level
error instead of a clear operator-facing one.
"""

from qdrant_client import QdrantClient

from app.llm.embedding_models import active_embedding_config
from app.migration.aliasing import resolve_active_collection_name
from app.shared.config import Settings


class EmbeddingSchemaMismatchError(Exception):
    """Raised at startup when the configured embedding dimension doesn't
    match the active Qdrant collection's real dense vector dimension.
    Fix: run the Sprint 22 migration CLI (`python -m
    scripts.operations.migrate_embedding_index plan`) before serving traffic, or
    correct EMBEDDING_MODEL_KEY/EMBEDDING_OUTPUT_DIMENSION back to match
    what's actually indexed.
    """


def ensure_embedding_schema_match(qdrant_client: QdrantClient, settings: Settings) -> None:
    active_collection = resolve_active_collection_name(qdrant_client, settings)
    if not qdrant_client.collection_exists(active_collection):
        # Fresh install, nothing indexed yet — nothing to mismatch against.
        return

    info = qdrant_client.get_collection(active_collection)
    dense_vectors = info.config.params.vectors or {}
    if not isinstance(dense_vectors, dict) or "dense" not in dense_vectors:
        return  # QdrantStore.ensure_collection's own schema checks own this failure mode

    active_dimension = dense_vectors["dense"].size
    configured_dimension = active_embedding_config(settings).dimension

    if active_dimension != configured_dimension:
        raise EmbeddingSchemaMismatchError(
            f"Configured embedding dimension {configured_dimension} does not match active "
            f"collection {active_collection!r} dimension {active_dimension}. "
            "Run embedding migration before serving traffic: "
            "`python -m scripts.operations.migrate_embedding_index plan`."
        )
