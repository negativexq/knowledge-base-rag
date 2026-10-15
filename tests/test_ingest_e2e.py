"""End-to-end ingestion test against the real, locally running services:
native Ollama (the production embedding model) and docker-compose Qdrant. Skipped automatically
if either service isn't reachable, so it doesn't break CI/offline runs —
but it's the test that actually proves the DoD: a real PDF, ingested twice,
produces no duplicate points.
"""

import shutil

import pytest
from qdrant_client import QdrantClient

from app.ingestion.chunker import chunk_document
from app.ingestion.ingest import ingest_path
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from tests.live_services import ollama_has, production_embed_fn, production_embed_model, qdrant_up

pytestmark = pytest.mark.ollama_e2e

COLLECTION = "test_ingest_e2e"


_services_up = qdrant_up() and ollama_has(production_embed_model())


@pytest.mark.skipif(
    not _services_up,
    reason="requires Qdrant on :6333 and the production embedding model in native Ollama",
)
@pytest.mark.asyncio
async def test_real_pdf_ingest_matches_chunk_count_and_is_idempotent(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")

    expected_chunks = chunk_document(sample_pdf, source_id="sample")

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(
        client=qdrant_client,
        collection_name=COLLECTION,
        dense_dimension=active_embedding_config(settings).dimension,
    )
    sparse_encoder = SparseEncoder()
    embed_fn = production_embed_fn(ollama)

    try:
        first = await ingest_path(str(docs_dir), store, embed_fn, sparse_encoder)
        assert first.chunks_upserted == len(expected_chunks)
        assert store.count() == len(expected_chunks)

        second = await ingest_path(str(docs_dir), store, embed_fn, sparse_encoder)
        assert second.chunks_upserted == len(expected_chunks)
        assert store.count() == len(expected_chunks)  # no duplicates on re-ingest
    finally:
        await ollama.aclose()
        qdrant_client.delete_collection(COLLECTION)
