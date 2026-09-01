from scripts.experiments.compare_ambiguity_versions import (
    _ambiguous_retention,
    _false_clarify_transitions,
)


def _row(query_id: str, target: str, action: str, decision: str, missing=None):
    return {
        "query_id": query_id,
        "case_family": f"family-{query_id}",
        "category": "standard_answerable",
        "language_pair": "en->en",
        "behavioral_target": target,
        "shadow_action": action,
        "ambiguity": {
            "decision": decision,
            "missing_constraints": missing or [],
        },
    }


def test_false_clarify_transition_analysis_is_id_aligned_and_deterministic():
    v1 = [
        _row("answer-1", "SHOULD_ANSWER", "CLARIFY", "AMBIGUOUS"),
        _row("answer-2", "SHOULD_ANSWER", "ANSWER", "CLEAR"),
        _row("ambiguous-1", "SHOULD_CLARIFY", "CLARIFY", "AMBIGUOUS"),
    ]
    v2 = [
        _row("answer-1", "SHOULD_ANSWER", "ANSWER", "CLEAR"),
        _row("answer-2", "SHOULD_ANSWER", "ANSWER", "CLEAR"),
        _row("ambiguous-1", "SHOULD_CLARIFY", "CLARIFY", "AMBIGUOUS"),
    ]

    transitions = _false_clarify_transitions(v1, v2)

    assert [row["query_id"] for row in transitions] == ["answer-1"]
    assert transitions[0]["v1_action"] == "CLARIFY"
    assert transitions[0]["v2_action"] == "ANSWER"


def test_ambiguous_retention_compares_the_same_family_records():
    v1 = [
        _row("ambiguous-1", "SHOULD_CLARIFY", "CLARIFY", "AMBIGUOUS"),
        _row("ambiguous-2", "SHOULD_CLARIFY", "CLARIFY", "AMBIGUOUS"),
    ]
    v2 = [
        _row("ambiguous-1", "SHOULD_CLARIFY", "CLARIFY", "AMBIGUOUS"),
        _row("ambiguous-2", "SHOULD_CLARIFY", "ANSWER", "CLEAR"),
    ]

    result = _ambiguous_retention(v1, v2)

    assert result["n"] == 2
    assert result["v1_retained"] == 2
    assert result["v2_retained"] == 1
    assert result["v2_missed"] == 1
