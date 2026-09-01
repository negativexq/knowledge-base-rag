from app.evaluation.generation_baseline import (
    build_cache_record,
    deterministic_correctness,
    safe_chunk_payload,
    select_generation_smoke_questions,
)
from app.retrieval.hybrid_search import SearchResult


def _question(question_id: str = "q-1", category: str = "standard_answerable") -> dict:
    return {
        "id": question_id,
        "case_family": question_id,
        "category": category,
        "split": "development",
        "query_language": "en",
        "evidence_language": "en",
        "language_pair": "en->en",
        "question": "What is the answer?",
        "answerability": "answerable",
        "expected_answer": "14 calendar days",
        "expected_source_ids": ["policy"],
        "required_evidence": ["policy"],
    }


def _chunk() -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "source_id": "policy",
            "text": "The return period is 14 calendar days.",
            "tenant_id": "tenant-a",
            "title": "Returns",
            "source_type": "filesystem",
        },
    )


def test_generation_smoke_selection_is_deterministic_and_balanced():
    from scripts.benchmarks.benchmark_generation_smoke import _load_questions

    first = select_generation_smoke_questions(_load_questions())
    second = select_generation_smoke_questions(_load_questions())

    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert len(first) == 36
    assert {row["category"] for row in first} >= {
        "standard_answerable",
        "hard_answerable",
        "cross_lingual",
        "multi_document",
        "version_conflict",
        "injection_bearing",
        "unanswerable",
        "acl_negative",
        "ambiguous",
    }


def test_generation_cache_contains_only_authorized_safe_chunk_fields():
    safe = safe_chunk_payload(_chunk())
    assert safe["chunk_id"] == "chunk-1"
    assert safe["source_id"] == "policy"
    assert safe["content"]
    assert "score" not in safe
    assert "tenant_id" not in safe

    record = build_cache_record(
        _question(),
        [_chunk()],
        pre_acl_candidate_count=3,
        authorized_candidate_count=1,
        retrieval_ms=1.0,
        deterministic_reason=None,
    )
    assert len(record["authorized_top5"]) == 1
    assert "expected_source_ids" not in record["authorized_top5"][0]


def test_deterministic_correctness_counts_all_authored_components():
    question = _question()
    question["expected_answer"] = "14 calendar days; keep the receipt"

    result = deterministic_correctness(question, "The return period is 14 calendar days.")

    assert result["status"] == "FAIL"
    assert result["covered"] == 1
    assert result["total"] == 2


def test_no_evidence_is_not_scored_as_answerable_success():
    question = _question(category="unanswerable")
    question["answerability"] = "unanswerable"
    question["expected_source_ids"] = []
    question["required_evidence"] = []

    record = build_cache_record(
        question,
        [],
        pre_acl_candidate_count=0,
        authorized_candidate_count=0,
        retrieval_ms=1.0,
        deterministic_reason="NO_RETRIEVAL_CANDIDATES",
    )

    assert record["gold_present"] is False
    assert record["all_required_present"] is False
