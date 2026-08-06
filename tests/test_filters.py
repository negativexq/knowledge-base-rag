from qdrant_client.http import models as qmodels

from app.retrieval.filters import build_filter


def test_returns_none_when_nothing_given():
    assert build_filter() is None


def test_builds_match_any_condition_for_doc_ids():
    result = build_filter(doc_ids=["a", "b"])

    assert result == qmodels.Filter(
        must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchAny(any=["a", "b"]))]
    )


def test_builds_match_any_condition_for_source_types():
    result = build_filter(source_types=["pdf", "markdown"])

    assert result == qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="source_type", match=qmodels.MatchAny(any=["pdf", "markdown"])
            )
        ]
    )


def test_builds_match_any_condition_for_source_ids():
    result = build_filter(source_ids=["handbook"])

    assert result == qmodels.Filter(
        must=[qmodels.FieldCondition(key="source_id", match=qmodels.MatchAny(any=["handbook"]))]
    )


def test_ands_multiple_fields_together():
    result = build_filter(source_types=["pdf"], page_numbers=[1, 2])

    assert result == qmodels.Filter(
        must=[
            qmodels.FieldCondition(key="source_type", match=qmodels.MatchAny(any=["pdf"])),
            qmodels.FieldCondition(key="page_number", match=qmodels.MatchAny(any=[1, 2])),
        ]
    )
