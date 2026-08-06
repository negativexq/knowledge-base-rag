import json

import pytest

from app.evaluation.harness import (
    GoldenQuestion,
    QuestionResult,
    build_report,
    load_golden_set,
    run_evaluation,
)
from app.evaluation.retrieval_metrics import RetrievalMetrics
from app.llm.prompt import NOT_FOUND_PHRASE
from app.retrieval.hybrid_search import SearchResult


def _chunk(source_id: str, page: int, paragraph: int, text: str = "text") -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "source_type": "filesystem",
            "source_id": source_id,
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
        },
    )


def test_load_golden_set_parses_questions(tmp_path):
    data = [
        {
            "id": "q1",
            "question": "How long?",
            "content_type": "pdf",
            "expected_locations": [["filesystem", "handbook", "1/0"]],
            "reference_answer": "30 days",
        },
        {
            "id": "q2",
            "question": "Unrelated?",
            "content_type": "markdown",
            "expected_locations": [],
            "reference_answer": None,
            "expect_not_found": True,
        },
    ]
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(data))

    questions = load_golden_set(str(path))

    assert len(questions) == 2
    assert questions[0] == GoldenQuestion(
        id="q1",
        question="How long?",
        content_type="pdf",
        expected_locations=[("filesystem", "handbook", "1/0")],
        reference_answer="30 days",
    )
    assert questions[1].expect_not_found is True
    assert questions[1].expected_locations == []


@pytest.mark.asyncio
async def test_run_evaluation_computes_retrieval_and_generation_metrics():
    questions = [
        GoldenQuestion(
            id="q1",
            question="How long?",
            content_type="pdf",
            expected_locations=[("filesystem", "handbook", "1/0")],
            reference_answer="30 days",
        )
    ]

    async def fake_search(question: str) -> list[SearchResult]:
        return [_chunk("handbook", 1, 0, "Refunds within 30 days.")]

    async def fake_generate(question: str, chunks: list[SearchResult]) -> str:
        return "30 days [s.filesystem:handbook/1/0]."

    def fake_generation_metrics(question, answer, contexts) -> dict[str, float]:
        return {"faithfulness": 1.0, "answer_relevancy": 0.9}

    results = await run_evaluation(questions, fake_search, fake_generate, fake_generation_metrics)

    assert len(results) == 1
    result = results[0]
    assert result.id == "q1"
    assert result.content_type == "pdf"
    assert result.retrieval.precision == 1.0
    assert result.retrieval.recall == 1.0
    assert result.generation == {"faithfulness": 1.0, "answer_relevancy": 0.9}
    assert result.not_found_actual is False


@pytest.mark.asyncio
async def test_run_evaluation_skips_generation_metrics_for_not_found_questions():
    questions = [
        GoldenQuestion(
            id="q2",
            question="Unrelated?",
            content_type="pdf",
            expected_locations=[],
            expect_not_found=True,
        )
    ]

    async def fake_search(question: str) -> list[SearchResult]:
        return [_chunk("handbook", 3, 0, "Something else entirely.")]

    async def fake_generate(question: str, chunks: list[SearchResult]) -> str:
        return NOT_FOUND_PHRASE

    called = []

    def fake_generation_metrics(question, answer, contexts) -> dict[str, float]:
        called.append(True)
        return {}

    results = await run_evaluation(questions, fake_search, fake_generate, fake_generation_metrics)

    assert results[0].not_found_actual is True
    assert results[0].generation is None
    assert not called  # generation metrics shouldn't run for not-found cases


@pytest.mark.asyncio
async def test_run_evaluation_detects_not_found_expected_but_answer_given():
    questions = [
        GoldenQuestion(
            id="q3",
            question="Unrelated?",
            content_type="pdf",
            expected_locations=[],
            expect_not_found=True,
        )
    ]

    async def fake_search(question: str) -> list[SearchResult]:
        return []

    async def fake_generate(question: str, chunks: list[SearchResult]) -> str:
        return "Here is a made-up answer."  # hallucination: should have said not-found

    results = await run_evaluation(questions, fake_search, fake_generate, None)

    assert results[0].not_found_actual is False
    assert results[0].expect_not_found is True


@pytest.mark.asyncio
async def test_run_evaluation_reports_progress_for_both_phases():
    questions = [
        GoldenQuestion(
            id="q1",
            question="Q1",
            content_type="pdf",
            expected_locations=[("filesystem", "handbook", "1/0")],
        ),
        GoldenQuestion(
            id="q2",
            question="Q2",
            content_type="markdown",
            expected_locations=[("filesystem", "cli_docs", "Kurulum")],
        ),
    ]

    async def fake_search(question: str) -> list[SearchResult]:
        return [_chunk("handbook", 1, 0)]

    async def fake_generate(question: str, chunks: list[SearchResult]) -> str:
        return "answer [s.filesystem:handbook/1/0]."

    def fake_generation_metrics(question, answer, contexts) -> dict[str, float]:
        return {"faithfulness": 1.0, "answer_relevancy": 1.0}

    events = []

    def progress_callback(phase: str, index: int, total: int, question_id: str) -> None:
        events.append((phase, index, total, question_id))

    await run_evaluation(
        questions,
        fake_search,
        fake_generate,
        fake_generation_metrics,
        progress_callback=progress_callback,
    )

    assert ("generate", 1, 2, "q1") in events
    assert ("generate", 2, 2, "q2") in events
    assert ("judge", 1, 2, "q1") in events
    assert ("judge", 2, 2, "q2") in events


def _result(id_, content_type, precision, recall, faithfulness, relevancy):
    return QuestionResult(
        id=id_,
        question=id_,
        content_type=content_type,
        answer="a",
        retrieval=RetrievalMetrics(precision, recall, [], []),
        generation={"faithfulness": faithfulness, "answer_relevancy": relevancy},
        expect_not_found=False,
        not_found_actual=False,
    )


def test_build_report_averages_retrieval_and_generation_metrics():
    results = [
        _result("q1", "pdf", 1.0, 1.0, 1.0, 0.8),
        _result("q2", "pdf", 0.5, 0.5, 0.6, 0.4),
    ]

    report = build_report(results)

    assert report["mean_precision"] == pytest.approx(0.75)
    assert report["mean_recall"] == pytest.approx(0.75)
    assert report["mean_faithfulness"] == pytest.approx(0.8)
    assert report["mean_answer_relevancy"] == pytest.approx(0.6)
    assert report["question_count"] == 2


def test_build_report_computes_not_found_accuracy():
    results = [
        QuestionResult(
            id="q1",
            question="q1",
            content_type="pdf",
            answer="I could not find this in the document.",
            retrieval=None,
            generation=None,
            expect_not_found=True,
            not_found_actual=True,
        ),
        QuestionResult(
            id="q2",
            question="q2",
            content_type="pdf",
            answer="Made up answer.",
            retrieval=None,
            generation=None,
            expect_not_found=True,
            not_found_actual=False,
        ),
    ]

    report = build_report(results)

    assert report["not_found_accuracy"] == 0.5
    assert report["not_found_question_count"] == 2


def test_build_report_handles_no_retrieval_or_generation_gracefully():
    results = [
        QuestionResult(
            id="q1",
            question="q1",
            content_type="pdf",
            answer="a",
            retrieval=None,
            generation=None,
            expect_not_found=False,
            not_found_actual=False,
        )
    ]

    report = build_report(results)

    assert report["mean_precision"] is None
    assert report["mean_faithfulness"] is None
    assert report["not_found_accuracy"] is None


def test_build_report_breaks_down_metrics_by_content_type():
    results = [
        _result("q1", "pdf", 1.0, 1.0, 1.0, 1.0),
        _result("q2", "pdf", 0.5, 0.5, 0.5, 0.5),
        _result("q3", "markdown", 0.0, 0.0, 0.2, 0.2),
    ]

    report = build_report(results)

    by_type = report["by_content_type"]
    assert by_type["pdf"]["question_count"] == 2
    assert by_type["pdf"]["mean_precision"] == pytest.approx(0.75)
    assert by_type["pdf"]["mean_faithfulness"] == pytest.approx(0.75)
    assert by_type["markdown"]["question_count"] == 1
    assert by_type["markdown"]["mean_precision"] == pytest.approx(0.0)
    assert by_type["markdown"]["mean_faithfulness"] == pytest.approx(0.2)
