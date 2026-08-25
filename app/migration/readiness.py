"""Sprint 22 section 23: cheap, reliable readiness semantics for
GET /health/ready — no real embedding inference call on every probe,
just the structural checks that actually predict whether a search would
work: active collection/alias exists, its dense dimension matches what's
configured, Qdrant is reachable, the embedding backend is reachable, and
the configured model is present in its model list.
"""

from qdrant_client import QdrantClient

from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient, OllamaUnreachableError
from app.migration.aliasing import resolve_active_collection_name
from app.shared.config import Settings


async def check_readiness(
    qdrant_client: QdrantClient, ollama: OllamaClient, settings: Settings
) -> dict:
    checks: dict[str, bool] = {}
    detail: dict[str, str] = {}

    embed_config = active_embedding_config(settings)
    collection_name = resolve_active_collection_name(qdrant_client, settings)

    try:
        exists = qdrant_client.collection_exists(collection_name)
    except Exception as exc:  # noqa: BLE001 - any failure here means Qdrant is unreachable
        checks["qdrant_reachable"] = False
        detail["qdrant_reachable"] = str(exc)
        exists = False
    else:
        checks["qdrant_reachable"] = True

    checks["active_collection_exists"] = exists
    if not exists:
        detail["active_collection_exists"] = f"{collection_name!r} does not exist yet"

    dimension_ok = False
    if exists:
        info = qdrant_client.get_collection(collection_name)
        dense_vectors = info.config.params.vectors or {}
        has_dense = isinstance(dense_vectors, dict) and "dense" in dense_vectors
        actual_dimension = dense_vectors["dense"].size if has_dense else None
        dimension_ok = actual_dimension == embed_config.dimension
        if not dimension_ok:
            detail["expected_dense_dimension"] = (
                f"configured={embed_config.dimension} actual={actual_dimension}"
            )
    checks["expected_dense_dimension"] = dimension_ok

    try:
        models = await ollama.list_models()
        checks["embedding_backend_reachable"] = True
    except OllamaUnreachableError as exc:
        checks["embedding_backend_reachable"] = False
        detail["embedding_backend_reachable"] = str(exc)
        models = []

    model_available = embed_config.ollama_model in models
    checks["configured_model_available"] = model_available
    if not model_available and checks["embedding_backend_reachable"]:
        detail["configured_model_available"] = (
            f"{embed_config.ollama_model!r} not found in Ollama's model list"
        )

    ready = all(checks.values())
    return {
        "ready": ready,
        "checks": checks,
        "detail": detail,
        "active_collection": collection_name,
        "active_alias": settings.qdrant_active_alias,
        "configured_model": embed_config.ollama_model,
        "configured_dimension": embed_config.dimension,
    }
