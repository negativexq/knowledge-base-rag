"""End-to-end evaluation test against real, locally running services:
native Ollama (embedding, generation, and the DeepEval judge) and
docker-compose Qdrant. Skipped automatically if either service isn't
reachable. Deliberately small (2 questions, one PDF one Markdown) — the
full golden set (tests/fixtures/golden_set.json) was run manually for the
Sprint 9 closing note; a 12-question x 7B-judge run is too slow for every
test invocation.
"""

import pytest
from qdrant_client import QdrantClient

from app.connectors.filesystem import LocalFilesystemConnector
from app.evaluation.cli import evaluation_callables
from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.harness import GoldenQuestion, build_report, run_evaluation
from app.ingestion.ingest import ingest_connector
from app.ingestion.qdrant_store import QdrantStore
from app.llm.embedding_models import active_embedding_config
from app.llm.ollama_client import OllamaClient
from app.registry.store import DocumentRegistry
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings
from app.wiring import build_chat_dependencies
from tests.fixtures.golden_markdown_source import build_golden_markdown_source
from tests.fixtures.golden_source import build_golden_source_pdf
from tests.live_services import ollama_has, production_embed_fn, production_embed_model, qdrant_up

pytestmark = pytest.mark.ollama_e2e

COLLECTION = "test_evaluation_e2e"

_services_up = qdrant_up() and ollama_has(
    production_embed_model(), settings.ollama_model, settings.eval_judge_model
)


@pytest.mark.skipif(
    not _services_up,
    reason=(
        "requires Qdrant and the production embedding, generation and judge "
        "models in native Ollama"
    ),
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
    store = QdrantStore(
        client=qdrant_client,
        collection_name=COLLECTION,
        dense_dimension=active_embedding_config(settings).dimension,
    )
    registry = DocumentRegistry(tmp_path / "registry.db")
    ollama = OllamaClient(base_url=settings.ollama_base_url)
    sparse_encoder = SparseEncoder()

    embed_fn = production_embed_fn(ollama)
    deps, chat_provider = build_chat_dependencies(
        settings, qdrant_client, ollama, sparse_encoder, COLLECTION
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

        search_fn, generate_fn = evaluation_callables(deps)

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
        await chat_provider.aclose()
        registry.close()
        qdrant_client.delete_collection(COLLECTION)
