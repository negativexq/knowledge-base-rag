from app.evaluation.generation_metrics import compute_generation_metrics


class _FakeMetric:
    def __init__(self, score: float):
        self.score = score
        self.measured_with = None

    def measure(self, test_case) -> None:
        self.measured_with = test_case


def test_compute_generation_metrics_returns_score_per_metric():
    faithfulness = _FakeMetric(0.8)
    relevancy = _FakeMetric(0.6)

    results = compute_generation_metrics(
        question="How long is the refund window?",
        answer="30 days.",
        retrieved_contexts=["Refunds are available within 30 days."],
        metrics={"faithfulness": faithfulness, "answer_relevancy": relevancy},
    )

    assert results == {"faithfulness": 0.8, "answer_relevancy": 0.6}


def test_compute_generation_metrics_builds_test_case_with_given_fields():
    metric = _FakeMetric(1.0)

    compute_generation_metrics(
        question="q",
        answer="a",
        retrieved_contexts=["c1", "c2"],
        metrics={"m": metric},
    )

    test_case = metric.measured_with
    assert test_case.input == "q"
    assert test_case.actual_output == "a"
    assert test_case.retrieval_context == ["c1", "c2"]


def test_compute_generation_metrics_with_no_metrics_returns_empty_dict():
    assert compute_generation_metrics("q", "a", ["c"], metrics={}) == {}
