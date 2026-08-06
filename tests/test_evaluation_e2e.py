"""End-to-end evaluation test against real, locally running services:
native Ollama (embedding, generation, and the DeepEval judge) and
docker-compose Qdrant. Skipped automatically if either service isn't
reachable. Deliberately small (2 questions, one PDF one Markdown) — the
full golden set (tests/fixtures/golden_set.json) was run manually for the
Sprint 9 closing note; a 12-question x 7B-judge run is too slow for every
test invocation.
"""

import socket

import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.harness import GoldenQuestion, build_report, run_evaluation
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from tests.fixtures.golden_markdown_source import build_golden_markdown_source
from tests.fixtures.golden_source import build_golden_source_pdf

COLLECTION = "test_evaluation_e2e"


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
async def test_real_golden_set_run_reports_metrics_by_content_type(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    build_golden_source_pdf(str(docs_dir / "handbook.pdf"))
    build_golden_markdown_source(str(docs_dir / "cli.md"))

    connector = LocalFilesystemConnector(docs_dir)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    if qdrant_client.collection_exists(COLLECTION):
        qdrant_client.delete_collection(COLLECTION)
    store = QdrantStore(client=qdrant_client, collection_name=COLLECTION)
    registry = DocumentRegistry(tmp_path / "registry.db")
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse_encoder = SparseEncoder()

    async def embed_fn(text: str) -> list[float]:
        return await ollama.embed(
            text, model=settings.ollama_embed_model, prefix="search_document: "
        )

    questions = [
        GoldenQuestion(
            id="pdf-free-storage",
            question="How much storage does a free Nimbus account include?",
            content_type="pdf",
            expected_locations=[("filesystem", "handbook_pdf", "1/0")],
            reference_answer="15GB",
        ),
        GoldenQuestion(
            id="md-token-lifetime",
            question="How many days are Nimbus CLI access tokens valid for?",
            content_type="markdown",
            expected_locations=[("filesystem", "cli_md", "Kimlik Doğrulama/Token Süresi")],
            reference_answer="90 days",
        ),
    ]

    try:
        await ingest_connector(connector, store, registry, embed_fn, sparse_encoder)

        async def search_fn(question: str) -> list[SearchResult]:
            return await search(
                question,
                ollama,
                sparse_encoder,
                qdrant_client,
                COLLECTION,
                settings.ollama_embed_model,
            )

        async def generate_fn(question: str, chunks: list[SearchResult]) -> str:
            parts = []
            async for event in stream_answer(
                question, chunks, ollama, settings.ollama_model, settings.active_prompt_version
            ):
                if event["type"] == "token":
                    parts.append(event["content"])
            return "".join(parts)

        metrics = build_default_metrics(
            judge_model_name=settings.eval_judge_model, base_url=settings.ollama_base_url
        )

        def generation_metrics_fn(question, answer, contexts) -> dict[str, float]:
            return compute_generation_metrics(question, answer, contexts, metrics)

        results = await run_evaluation(questions, search_fn, generate_fn, generation_metrics_fn)
        report = build_report(results)

        assert report["question_count"] == 2
        assert set(report["by_content_type"].keys()) == {"pdf", "markdown"}
        assert report["mean_faithfulness"] is not None
        assert report["mean_answer_relevancy"] is not None
    finally:
        await ollama.aclose()
        registry.close()
        qdrant_client.delete_collection(COLLECTION)
