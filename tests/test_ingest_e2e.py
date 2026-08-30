"""End-to-end ingestion test against the real, locally running services:
native Ollama (embeddings) and docker-compose Qdrant. Skipped automatically
if either service isn't reachable, so it doesn't break CI/offline runs —
but it's the test that actually proves the DoD: a real PDF, ingested twice,
produces no duplicate points.
"""

import shutil
import socket

import pytest
from qdrant_client import QdrantClient

from app.ingestion.chunker import chunk_document
from app.ingestion.ingest import SEARCH_DOCUMENT_PREFIX, ingest_path
from app.ingestion.qdrant_store import QdrantStore
from app.llm.ollama_client import OllamaClient
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings

pytestmark = pytest.mark.ollama_e2e

COLLECTION = "test_ingest_e2e"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


_services_up = _port_open("localhost", 11434) and _port_open("localhost", 6333)


@pytest.mark.skipif(
    not _services_up, reason="requires native Ollama on :11434 and Qdrant on :6333"
)
@pytest.mark.asyncio
async def test_real_pdf_ingest_matches_chunk_count_and_is_idempotent(sample_pdf, tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    shutil.copy(sample_pdf, docs_dir / "sample.pdf")

    expected_chunks = chunk_document(sample_pdf, source_id="sample")

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    store = QdrantStore(client=qdrant_client, collection_name=COLLECTION)
    sparse_encoder = SparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix=SEARCH_DOCUMENT_PREFIX
        )

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
