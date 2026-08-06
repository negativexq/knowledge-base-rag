import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.evaluation.retrieval_metrics import Location, RetrievalMetrics, compute_retrieval_metrics
from app.llm.prompt import NOT_FOUND_PHRASE
from app.retrieval.hybrid_search import SearchResult

SearchFn = Callable[[str], Awaitable[list[SearchResult]]]
GenerateFn = Callable[[str, list[SearchResult]], Awaitable[str]]
GenerationMetricsFn = Callable[[str, str, list[str]], dict[str, float]]
ProgressCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    question: str
    # "pdf" / "markdown" — which content format this question targets, used
    # for the per-format metric breakdown (see docs/sprint-09-plan.md for
    # why this is content_type, not source_type).
    content_type: str
    expected_locations: list[Location] = field(default_factory=list)
    reference_answer: str | None = None
    expect_not_found: bool = False


@dataclass
class QuestionResult:
    id: str
    question: str
    content_type: str
    answer: str
    retrieval: RetrievalMetrics | None
    generation: dict[str, float] | None
    expect_not_found: bool
    not_found_actual: bool


class MetricsProtocol(Protocol):
    def measure(self, test_case) -> None: ...


def load_golden_set(path: str) -> list[GoldenQuestion]:
    with open(path) as f:
        data = json.load(f)

    return [
        GoldenQuestion(
            id=item["id"],
            question=item["question"],
            content_type=item["content_type"],
            expected_locations=[tuple(loc) for loc in item.get("expected_locations", [])],
            reference_answer=item.get("reference_answer"),
            expect_not_found=item.get("expect_not_found", False),
        )
        for item in data
    ]


async def run_evaluation(
    questions: list[GoldenQuestion],
    search_fn: SearchFn,
    generate_fn: GenerateFn,
    generation_metrics_fn: GenerationMetricsFn | None,
    progress_callback: ProgressCallback | None = None,
) -> list[QuestionResult]:
    """Two-phase execution — ALL retrieval+generation first, THEN all judge
    scoring. Ported from production-rag-platform's harness: interleaving
    the two forces Ollama to reload the model on almost every call when
    generation and judging use different models (measured there to turn a
    ~11-minute run into 40+ minutes). See docs/sprint-09-plan.md.
    """
    total = len(questions)
    pending = []

    for index, question in enumerate(questions, start=1):
        retrieved = await search_fn(question.question)
        answer = await generate_fn(question.question, retrieved)
        not_found_actual = NOT_FOUND_PHRASE in answer

        retrieval_metrics = compute_retrieval_metrics(retrieved, question.expected_locations)

        if progress_callback:
            progress_callback("generate", index, total, question.id)

        pending.append((question, retrieved, answer, not_found_actual, retrieval_metrics))

    results = []
    for index, (question, retrieved, answer, not_found_actual, retrieval_metrics) in enumerate(
        pending, start=1
    ):
        generation_metrics = None
        if not not_found_actual and generation_metrics_fn is not None:
            contexts = [r.payload["text"] for r in retrieved]
            generation_metrics = generation_metrics_fn(question.question, answer, contexts)

        if progress_callback:
            progress_callback("judge", index, total, question.id)

        results.append(
            QuestionResult(
                id=question.id,
                question=question.question,
                content_type=question.content_type,
                answer=answer,
                retrieval=retrieval_metrics,
                generation=generation_metrics,
                expect_not_found=question.expect_not_found,
                not_found_actual=not_found_actual,
            )
        )

    return results


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _metrics_report(results: list[QuestionResult]) -> dict:
    precisions = [r.retrieval.precision for r in results if r.retrieval is not None]
    recalls = [r.retrieval.recall for r in results if r.retrieval is not None]
    faithfulness = [r.generation["faithfulness"] for r in results if r.generation]
    answer_relevancy = [r.generation["answer_relevancy"] for r in results if r.generation]

    not_found_questions = [r for r in results if r.expect_not_found]
    not_found_correct = sum(1 for r in not_found_questions if r.not_found_actual)

    return {
        "question_count": len(results),
        "mean_precision": _mean(precisions),
        "mean_recall": _mean(recalls),
        "mean_faithfulness": _mean(faithfulness),
        "mean_answer_relevancy": _mean(answer_relevancy),
        "not_found_question_count": len(not_found_questions),
        "not_found_accuracy": (
            not_found_correct / len(not_found_questions) if not_found_questions else None
        ),
    }


def build_report(results: list[QuestionResult]) -> dict:
    report = _metrics_report(results)

    content_types = sorted({r.content_type for r in results})
    report["by_content_type"] = {
        content_type: _metrics_report([r for r in results if r.content_type == content_type])
        for content_type in content_types
    }

    return report
