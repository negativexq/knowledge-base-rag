from scripts.analyze_answerability_failures import (
    _gold_presence,
    _taxonomy_row,
)


def _record(required, retrieved, category="standard_answerable"):
    return {
        "query_id": "q-1",
        "case_family": "family-1",
        "category": category,
        "tenant": "tenant-a",
        "query_language": "en",
        "evidence_language": "en",
        "language_pair": "en->en",
        "answerability_label": "answerable",
        "required_source_ids": required,
        "expected_source_ids": required,
        "top_authorized_source_ids": retrieved,
        "deterministic_reason": "FEATURES_AVAILABLE",
    }


def test_gold_presence_distinguishes_any_and_all_required_sources():
    presence = _gold_presence(_record(["source-a", "source-b"], ["source-a"]))
    assert presence == {
        "any_required_present": True,
        "all_required_present": False,
    }


def test_taxonomy_classifies_retrieval_failure():
    row = _taxonomy_row(_record(["source-a"], ["source-z"]), prediction=1)
    assert row["cause"] == "retrieval_failure"


def test_taxonomy_classifies_gate_failure_with_gold_present():
    row = _taxonomy_row(_record(["source-a"], ["source-a"]), prediction=1)
    assert row["cause"] == "gate_failure_with_gold_present"


def test_taxonomy_classifies_multi_document_partial_evidence():
    row = _taxonomy_row(
        _record(["source-a", "source-b"], ["source-a"], "multi_document"),
        prediction=1,
    )
    assert row["cause"] == "multi_document_partial_evidence"


def test_taxonomy_marks_answer_without_gold_as_unsafe_candidate():
    row = _taxonomy_row(_record(["source-a"], ["source-z"]), prediction=0)
    assert row["cause"] == "unsafe_answer_candidate"
