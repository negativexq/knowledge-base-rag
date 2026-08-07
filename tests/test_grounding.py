from app.llm.grounding import check_grounding
from app.retrieval.hybrid_search import SearchResult


def _result(
    page: int, paragraph: int, text: str, source_type: str = "pdf", source_id: str = "doc"
) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_type": source_type,
            "source_id": source_id,
        },
    )


def _markdown_result(
    heading_path: tuple[str, ...],
    text: str,
    source_type: str = "markdown",
    source_id: str = "readme",
) -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": 0,
            "paragraph_index": 0,
            "heading_path": list(heading_path),
            "text": text,
            "source_type": source_type,
            "source_id": source_id,
        },
    )


def test_grounding_passes_when_all_citations_match_context():
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    answer = "Refunds take 30 days [s.pdf:doc/2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is True
    assert result.citations_found == [("pdf", "doc", "2/0")]
    assert result.ungrounded_citations == []


def test_grounding_fails_on_a_deliberately_fabricated_citation():
    """Concrete proof the check actually catches hallucination: context only
    has (page=2, paragraph=0), but the answer cites a page/paragraph
    (99, 0) that was never in the context — a fabricated reference.
    """
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    fabricated_answer = "Refunds take 30 days [s.pdf:doc/99/0]."

    result = check_grounding(fabricated_answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("pdf", "doc", "99/0")]


def test_grounding_reports_only_the_fabricated_citation_when_mixed():
    chunks = [_result(2, 0, "Refunds are processed within 30 days."), _result(5, 1, "Other text.")]
    answer = (
        "Refunds take 30 days [s.pdf:doc/2/0], and something else [s.pdf:doc/5/1], "
        "plus [s.pdf:doc/7/3]."
    )

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.citations_found == [
        ("pdf", "doc", "2/0"),
        ("pdf", "doc", "5/1"),
        ("pdf", "doc", "7/3"),
    ]
    assert result.ungrounded_citations == [("pdf", "doc", "7/3")]


def test_grounding_with_no_citations_at_all_is_not_grounded():
    """A citation-free answer is the most dangerous hallucination shape —
    no citation tag at all for a reader to even question. `grounded` must
    be False, distinguishable from "has citations but they're invalid" via
    `has_citations`. See docs/sprint-12-plan.md.
    """
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]

    result = check_grounding("I could not find this in the document.", chunks)

    assert result.grounded is False
    assert result.has_citations is False
    assert result.citations_valid is True  # vacuously — nothing to invalidate
    assert result.citations_found == []
    assert result.ungrounded_citations == []


def test_grounding_has_citations_true_and_valid_when_all_match():
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    answer = "Refunds take 30 days [s.pdf:doc/2/0]."

    result = check_grounding(answer, chunks)

    assert result.has_citations is True
    assert result.citations_valid is True
    assert result.grounded is True


def test_grounding_has_citations_true_but_invalid_when_fabricated():
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    answer = "Refunds take 30 days [s.pdf:doc/99/0]."

    result = check_grounding(answer, chunks)

    assert result.has_citations is True
    assert result.citations_valid is False
    assert result.grounded is False


def test_grounding_rejects_citation_whose_page_paragraph_matches_a_different_source():
    """Regression test: a two-document collection (a CV and an unrelated
    handbook) can share the same (page, paragraph) coordinates. A citation
    must be validated against the SAME source it claims, not just against
    any chunk with matching page/paragraph anywhere in context.
    """
    chunks = [
        _result(1, 0, "CV text about Python and SQL.", source_type="pdf", source_id="cv"),
        _result(2, 0, "Unrelated handbook text.", source_type="pdf", source_id="handbook"),
    ]
    # cites handbook's coordinates (2, 0) but tags it as coming from the cv
    answer = "Knows Python and SQL [s.pdf:cv/2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("pdf", "cv", "2/0")]


def test_grounding_rejects_citation_whose_source_type_differs_even_with_same_source_id():
    """A markdown doc and a PDF could coincidentally share a source_id
    (e.g. both derived from "readme") — the source_type must also match.
    """
    chunks = [_result(2, 0, "PDF content.", source_type="pdf", source_id="readme")]
    answer = "Some claim [s.markdown:readme/2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("markdown", "readme", "2/0")]


def test_grounding_passes_for_a_markdown_heading_path_citation():
    chunks = [_markdown_result(("Kurulum", "Adım 1"), "Do this first.")]
    answer = "Do this first [s.markdown:readme/Kurulum/Adım 1]."

    result = check_grounding(answer, chunks)

    assert result.grounded is True
    assert result.citations_found == [("markdown", "readme", "Kurulum/Adım 1")]


def test_grounding_fails_on_a_fabricated_markdown_heading_citation():
    chunks = [_markdown_result(("Kurulum",), "Install steps.")]
    fabricated_answer = "Install steps [s.markdown:readme/Sorun Giderme]."

    result = check_grounding(fabricated_answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("markdown", "readme", "Sorun Giderme")]


def test_grounding_distinguishes_pdf_and_markdown_locations_for_the_same_source_id():
    """A PDF and a markdown doc sharing a source_id (e.g. both "readme")
    must not have their locations cross-validate — "2/0" as a PDF page/
    paragraph is a different claim than "2/0" as a markdown heading path.
    """
    chunks = [_result(2, 0, "PDF content.", source_type="pdf", source_id="readme")]
    answer = "Some claim [s.pdf:readme/3/0]."  # never in context

    result = check_grounding(answer, chunks)

    assert result.grounded is False
