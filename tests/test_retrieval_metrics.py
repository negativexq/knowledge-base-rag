from app.evaluation.retrieval_metrics import compute_retrieval_metrics
from app.retrieval.hybrid_search import SearchResult


def _pdf_result(source_id: str, page: int, paragraph: int) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "source_type": "filesystem",
            "source_id": source_id,
            "page_number": page,
            "paragraph_index": paragraph,
        },
    )


def _md_result(source_id: str, *heading_path: str) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "source_type": "filesystem",
            "source_id": source_id,
            "heading_path": list(heading_path),
        },
    )


def test_perfect_retrieval_gives_precision_and_recall_of_one():
    retrieved = [_pdf_result("handbook", 1, 0), _pdf_result("handbook", 2, 1)]
    expected = [("filesystem", "handbook", "1/0"), ("filesystem", "handbook", "2/1")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_extra_irrelevant_chunk_lowers_precision_but_not_recall():
    retrieved = [_pdf_result("handbook", 1, 0), _pdf_result("handbook", 9, 9)]
    expected = [("filesystem", "handbook", "1/0")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.precision == 0.5
    assert metrics.recall == 1.0


def test_missing_expected_chunk_lowers_recall_but_not_precision():
    retrieved = [_pdf_result("handbook", 1, 0)]
    expected = [("filesystem", "handbook", "1/0"), ("filesystem", "handbook", "2/1")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.precision == 1.0
    assert metrics.recall == 0.5


def test_no_retrieved_results_gives_zero_precision():
    metrics = compute_retrieval_metrics([], expected_locations=[("filesystem", "handbook", "1/0")])

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0


def test_markdown_heading_path_location_used_for_matching():
    retrieved = [_md_result("cli_docs", "Kurulum", "Adım 1")]
    expected = [("filesystem", "cli_docs", "Kurulum/Adım 1")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_same_location_string_from_different_source_id_does_not_match():
    # Two different documents that happen to share a location string
    # ("1/0") must not be treated as a match — this is exactly the
    # cross-source citation leak class from Sprint 5/6, and retrieval
    # metrics must key on the full (source_type, source_id, location)
    # triple, not location alone.
    retrieved = [_pdf_result("other_doc", 1, 0)]
    expected = [("filesystem", "handbook", "1/0")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0


def test_records_retrieved_and_expected_locations():
    retrieved = [_pdf_result("handbook", 1, 0)]
    expected = [("filesystem", "handbook", "1/0")]

    metrics = compute_retrieval_metrics(retrieved, expected_locations=expected)

    assert metrics.retrieved_locations == [("filesystem", "handbook", "1/0")]
    assert metrics.expected_locations == [("filesystem", "handbook", "1/0")]
