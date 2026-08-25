import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.migration.startup_guard import EmbeddingSchemaMismatchError, ensure_embedding_schema_match
from app.shared.config import Settings


def _client_with_dense_collection(name: str, dimension: int) -> QdrantClient:
    client = QdrantClient(":memory:")
    client.create_collection(
        name,
        vectors_config={
            "dense": qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE)
        },
    )
    return client


def test_passes_silently_when_no_collection_exists_yet():
    client = QdrantClient(":memory:")
    settings = Settings(embedding_model_key="qwen3-4b", embedding_output_dimension=1024)

    ensure_embedding_schema_match(client, settings)  # must not raise


def test_passes_when_dimension_matches():
    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qdrant_collection_name="kb_chunks",
    )
    client = _client_with_dense_collection("kb_chunks", 1024)

    ensure_embedding_schema_match(client, settings)  # must not raise


def test_raises_clearly_on_dimension_mismatch():
    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qdrant_collection_name="kb_chunks",
    )
    client = _client_with_dense_collection("kb_chunks", 768)

    with pytest.raises(EmbeddingSchemaMismatchError, match="1024.*768"):
        ensure_embedding_schema_match(client, settings)


def test_checks_the_alias_target_dimension_when_an_alias_is_active():
    from app.migration.aliasing import atomic_switch_alias

    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qdrant_active_alias="kb_active",
    )
    client = _client_with_dense_collection("kb_qwen3_4b_1024_x", 1024)
    atomic_switch_alias(client, "kb_active", "kb_qwen3_4b_1024_x")

    ensure_embedding_schema_match(client, settings)  # must not raise
