from app.evaluation.terminal_outcomes import terminal_result


def test_clarification_is_exported_without_inventing_answer_tokens():
    result = terminal_result(
        [
            {"type": "metadata", "agentic": {"finalization": "abstained"}},
            {"type": "clarification", "question": "Which market?", "options": ["A", "B"]},
        ]
    )
    assert result == {
        "answer": "",
        "terminal_kind": "needs_clarification",
        "clarification": {"question": "Which market?", "options": ["A", "B"]},
    }


def test_rendered_insufficiency_text_is_not_scored_as_a_positive_answer():
    result = terminal_result(
        [
            {"type": "token", "content": "Insufficient evidence."},
            {"type": "security_validation", "abstain": True, "passed": True},
        ]
    )
    assert result["terminal_kind"] == "insufficient_evidence"


def test_failed_finalization_remains_distinct_from_safe_insufficiency():
    result = terminal_result(
        [
            {"type": "metadata", "agentic": {"finalization": "failed"}},
            {"type": "security_validation", "abstain": True, "passed": False},
        ]
    )
    assert result["terminal_kind"] == "failed"


def test_terminal_export_requires_release_validation_for_a_positive_answer():
    events = [{"type": "token", "content": "42"}]
    assert terminal_result(events)["terminal_kind"] == "unknown"
    events.append({"type": "security_validation", "passed": True, "abstain": False})
    assert terminal_result(events)["terminal_kind"] == "answer"
