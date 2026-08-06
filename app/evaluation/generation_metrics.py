from typing import Protocol

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase

# qwen2.5:3b-instruct produced an internally inconsistent verdict/reason
# pair as a judge in production-rag-platform's real testing; 7B fixed it
# on the same test. Ported unchanged — see docs/sprint-09-plan.md.
DEFAULT_JUDGE_MODEL = "qwen2.5:7b-instruct"


class MetricProtocol(Protocol):
    score: float

    def measure(self, test_case: LLMTestCase) -> None: ...


def compute_generation_metrics(
    question: str,
    answer: str,
    retrieved_contexts: list[str],
    metrics: dict[str, MetricProtocol],
) -> dict[str, float]:
    test_case = LLMTestCase(
        input=question, actual_output=answer, retrieval_context=retrieved_contexts
    )
    results = {}
    for name, metric in metrics.items():
        metric.measure(test_case)
        results[name] = metric.score
    return results


def build_default_metrics(
    judge_model_name: str = DEFAULT_JUDGE_MODEL, base_url: str = "http://localhost:11434"
) -> dict[str, MetricProtocol]:
    """No explicit HTTP timeout override: DeepEval's OllamaModel uses the
    official `ollama` package, whose client defaults to `timeout=None` —
    verified (docs/sprint-09-plan.md) that httpx treats that as "no
    timeout," not "fall back to a short default." That's the opposite of
    production-rag-platform's Sprint 9 timeout bug, which was specific to
    this project's own httpx-based OllamaClient (already fixed in Sprint
    0) and never applied to this code path.
    """
    judge = OllamaModel(model=judge_model_name, base_url=base_url)
    return {
        "faithfulness": FaithfulnessMetric(model=judge),
        "answer_relevancy": AnswerRelevancyMetric(model=judge),
    }
