import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.llm.embedding_models import active_embedding_config
from app.migration.readiness import check_readiness
from app.shared.config import Settings


class _FakeOllama:
    def __init__(self, models=None, unreachable=False):
        self._models = models or []
        self._unreachable = unreachable

    async def list_models(self):
        if self._unreachable:
            from app.llm.ollama_client import OllamaUnreachableError

            raise OllamaUnreachableError("nope")
        return self._models


def _client_with_dense_collection(name: str, dimension: int) -> QdrantClient:
    client = QdrantClient(":memory:")
    client.create_collection(
        name,
        vectors_config={
            "dense": qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE)
        },
    )
    return client


@pytest.mark.asyncio
async def test_ready_when_everything_lines_up():
    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qdrant_collection_name="kb_chunks",
    )
    model_name = active_embedding_config(settings).ollama_model
    client = _client_with_dense_collection("kb_chunks", 1024)
    ollama = _FakeOllama(models=[model_name])

    result = await check_readiness(client, ollama, settings)

    assert result["ready"] is True
    assert result["checks"]["active_collection_exists"] is True
    assert result["checks"]["expected_dense_dimension"] is True
    assert result["checks"]["configured_model_available"] is True


@pytest.mark.asyncio
async def test_not_ready_when_collection_does_not_exist():
    settings = Settings(qdrant_collection_name="kb_chunks")
    client = QdrantClient(":memory:")
    ollama = _FakeOllama(models=["nomic-embed-text"])

    result = await check_readiness(client, ollama, settings)

    assert result["ready"] is False
    assert result["checks"]["active_collection_exists"] is False


@pytest.mark.asyncio
async def test_not_ready_when_dimension_mismatches():
    settings = Settings(
        embedding_model_key="qwen3-4b", embedding_output_dimension=1024,
        qdrant_collection_name="kb_chunks",
    )
    client = _client_with_dense_collection("kb_chunks", 768)
    ollama = _FakeOllama(models=[active_embedding_config(settings).ollama_model])

    result = await check_readiness(client, ollama, settings)

    assert result["ready"] is False
    assert result["checks"]["expected_dense_dimension"] is False


@pytest.mark.asyncio
async def test_not_ready_when_ollama_unreachable():
    settings = Settings(qdrant_collection_name="kb_chunks", embedding_output_dimension=1024)
    client = _client_with_dense_collection("kb_chunks", 1024)
    ollama = _FakeOllama(unreachable=True)

    result = await check_readiness(client, ollama, settings)

    assert result["ready"] is False
    assert result["checks"]["embedding_backend_reachable"] is False


@pytest.mark.asyncio
async def test_not_ready_when_configured_model_missing_from_ollama():
    settings = Settings(qdrant_collection_name="kb_chunks", embedding_output_dimension=1024)
    client = _client_with_dense_collection("kb_chunks", 1024)
    ollama = _FakeOllama(models=["some-other-model"])

    result = await check_readiness(client, ollama, settings)

    assert result["ready"] is False
    assert result["checks"]["configured_model_available"] is False


@pytest.mark.asyncio
async def test_does_not_make_a_real_embedding_inference_call():
    """Section 23's explicit cheap-readiness requirement — check_readiness
    must never invoke ollama.embed(), only list_models()."""
    settings = Settings(qdrant_collection_name="kb_chunks", embedding_output_dimension=1024)
    client = _client_with_dense_collection(
        "kb_chunks", active_embedding_config(settings).dimension
    )

    class _NoEmbedOllama(_FakeOllama):
        async def embed(self, *a, **k):
            raise AssertionError("readiness must never call embed()")

    ollama = _NoEmbedOllama(models=[active_embedding_config(settings).ollama_model])

    await check_readiness(client, ollama, settings)
