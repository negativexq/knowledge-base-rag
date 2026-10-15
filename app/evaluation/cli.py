import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable

from qdrant_client import QdrantClient

from app.api.chat import ChatDependencies
from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.harness import build_report, load_golden_set, run_evaluation
from app.llm.ollama_client import OllamaClient
from app.migration.aliasing import resolve_active_collection_name
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.report import RetrievalReport
from app.retrieval.sparse import SparseEncoder
from app.security.models import RetrievalContext
from app.shared.config import Settings, settings

SearchFn = Callable[[str], Awaitable[list[SearchResult]]]
GenerateFn = Callable[[str, list[SearchResult]], Awaitable[str]]


def evaluation_settings(
    base: Settings, *, generation_model: str | None, use_reranker: bool
) -> Settings:
    """Production settings with only the CLI's overrides applied. The base
    object is left untouched."""
    updates: dict[str, object] = {}
    if generation_model is not None:
        updates["ollama_model"] = generation_model
    if not use_reranker:
        updates["reranker_enabled"] = False
    return base.model_copy(update=updates)


def evaluation_callables(deps: ChatDependencies) -> tuple[SearchFn, GenerateFn]:
    """The harness's search_fn/generate_fn, built from the same
    ChatDependencies POST /chat uses: production search, then the evidence
    step (when wired), then the production answer stream. Only the tokens a
    user would see make up the answer.

    The golden-set collection sits outside any real tenant boundary, so the
    search runs as the explicit system context, not a fabricated tenant.
    """

    async def search_fn(question: str) -> list[SearchResult]:
        return await deps.search_fn(question, RetrievalContext.system(), RetrievalReport())

    async def generate_fn(question: str, chunks: list[SearchResult]) -> str:
        if deps.evidence_fn is not None:
            chunks = await deps.evidence_fn(chunks, RetrievalContext.system())
        answer_parts = []
        async for event in deps.stream_fn(question, chunks):
            if event["type"] == "token":
                answer_parts.append(event["content"])
        return "".join(answer_parts)

    return search_fn, generate_fn


async def run_golden_set(
    golden_set_path: str,
    generation_model: str | None = None,
    collection_name: str | None = None,
    use_reranker: bool = True,
) -> dict:
    """Real-component golden-set run over the production chat path: the
    embedding model, reranker, evidence builder and support-ID answer
    contract all come from app/wiring.py::build_chat_dependencies, so the
    CLI cannot drift from what POST /chat serves. Real DeepEval judge.

    `generation_model` defaults to the production model; pass another one
    to compare. It stays independent of `settings.eval_judge_model`.
    `use_reranker=False` (`--no-reranker`) measures pre-rerank retrieval
    instead (Sprint 17.5, docs/sprint-17-5-plan.md).
    """
    # Imported here: app.wiring imports the FastAPI app graph, which this
    # module's unit-tested helpers above do not need.
    from app.wiring import build_chat_dependencies

    run_settings = evaluation_settings(
        settings, generation_model=generation_model, use_reranker=use_reranker
    )
    questions = load_golden_set(golden_set_path)

    ollama = OllamaClient(base_url=run_settings.ollama_base_url)
    qdrant_client = QdrantClient(url=run_settings.qdrant_url)
    collection_name = collection_name or resolve_active_collection_name(qdrant_client, run_settings)
    deps, chat_provider = build_chat_dependencies(
        run_settings, qdrant_client, ollama, SparseEncoder(), collection_name
    )
    search_fn, generate_fn = evaluation_callables(deps)
    metrics = build_default_metrics(
        judge_model_name=run_settings.eval_judge_model, base_url=run_settings.ollama_base_url
    )

    def generation_metrics_fn(question: str, answer: str, contexts: list[str]) -> dict[str, float]:
        return compute_generation_metrics(question, answer, contexts, metrics)

    def progress(phase: str, index: int, total: int, question_id: str) -> None:
        print(f"[{phase}] {index}/{total} {question_id}")

    try:
        results = await run_evaluation(
            questions, search_fn, generate_fn, generation_metrics_fn, progress_callback=progress
        )
    finally:
        await ollama.aclose()
        await chat_provider.aclose()
        qdrant_client.close()

    return build_report(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a golden-set evaluation")
    parser.add_argument("--golden-set", required=True, help="Path to the golden set JSON file")
    parser.add_argument(
        "--generation-model",
        default=None,
        help="Ollama model used for RAG generation (defaults to the production model)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Qdrant collection to search (defaults to settings.qdrant_collection_name)",
    )
    parser.add_argument(
        "--no-reranker",
        action="store_true",
        help=(
            "Skip CrossEncoderReranker and measure pre-rerank hybrid retrieval only. "
            "Default (reranker ON) matches the production chat pipeline."
        ),
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_golden_set(
            args.golden_set,
            args.generation_model,
            collection_name=args.collection,
            use_reranker=not args.no_reranker,
        )
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
