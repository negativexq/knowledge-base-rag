import argparse
import asyncio
import json

from qdrant_client import QdrantClient

from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.harness import build_report, load_golden_set, run_evaluation
from app.llm.generate import stream_answer
from app.llm.ollama_client import OllamaClient
from app.retrieval.hybrid_search import SearchResult
from app.retrieval.search import search
from app.retrieval.sparse import SparseEncoder
from app.shared.config import settings


async def run_golden_set(
    golden_set_path: str, generation_model: str, collection_name: str | None = None
) -> dict:
    """Real-component wiring for a golden-set run: real Ollama (embedding +
    generation), real Qdrant, real sparse encoder, real DeepEval judge.
    `generation_model` is independent of `settings.eval_judge_model` on
    purpose — the two-phase harness's payoff (avoiding Ollama's
    model-swap-per-call cost) only shows up when generation and judging use
    different models, so the CLI defaults them differently.
    """
    questions = load_golden_set(golden_set_path)
    collection_name = collection_name or settings.qdrant_collection_name

    ollama = OllamaClient(base_url=settings.ollama_base_url)
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    sparse_encoder = SparseEncoder()
    metrics = build_default_metrics(
        judge_model_name=settings.eval_judge_model, base_url=settings.ollama_base_url
    )

    async def search_fn(question: str) -> list[SearchResult]:
        return await search(
            question,
            ollama,
            sparse_encoder,
            qdrant_client,
            collection_name,
            settings.ollama_embed_model,
        )

    async def generate_fn(question: str, chunks: list[SearchResult]) -> str:
        answer_parts = []
        async for event in stream_answer(
            question, chunks, ollama, generation_model, settings.active_prompt_version
        ):
            if event["type"] == "token":
                answer_parts.append(event["content"])
        return "".join(answer_parts)

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

    return build_report(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a golden-set evaluation")
    parser.add_argument("--golden-set", required=True, help="Path to the golden set JSON file")
    parser.add_argument(
        "--generation-model",
        default="qwen2.5:3b-instruct",
        help="Ollama model used for RAG generation (kept distinct from the judge model)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Qdrant collection to search (defaults to settings.qdrant_collection_name)",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_golden_set(args.golden_set, args.generation_model, collection_name=args.collection)
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
