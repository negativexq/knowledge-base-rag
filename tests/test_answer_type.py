"""206, 219, 225 ask how many people; luna answered with the survey's
percentages ("36% of adults rated ... as poor"), and the validator passed them:
every number is in a cited unit. A question that asks for a count of things,
and not for a share, is not answered by a percentage. A part that states one
with no count and no calculation is rejected."""

import json

from app.evidence.support_units import build_support_units
from app.llm.premise import asks_count_answers_percent
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

POOR = "How many adults rated Trump's government ethical standards as poor?"


def test_a_count_question_answered_by_a_percentage():
    assert asks_count_answers_percent(POOR, "36% of adults rated them poor.")
    assert asks_count_answers_percent(
        "How many 65+ people go online 3-5 times per week?", "11% go online 3–5 times per week."
    )
    assert asks_count_answers_percent("What is the number of users?", "It is 42 percent.")


def test_counts_shares_and_other_questions_are_left_alone():
    assert not asks_count_answers_percent(POOR, "About 541 adults rated them poor.")
    assert not asks_count_answers_percent(
        "How many percent of adults rated them poor?", "36% rated them poor."
    )
    assert not asks_count_answers_percent(
        "What share of adults rated them poor?", "36% rated them poor."
    )
    assert not asks_count_answers_percent("How many appendices are there?", "There are 5.")


def _validate(answer_part: dict):
    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="c",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "b",
                    "source_id": "survey",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Ethics"],
                    "contributing_chunk_ids": ["c"],
                    "text": "Of the 1,503 adults surveyed, 36% rated the standards as poor.",
                },
            )
        ]
    )
    part = {**answer_part, "support_ids": [unit.support_unit_id for unit in units]}
    parsed = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))
    return validate_support_unit_answer(parsed, units, question=POOR)


def test_a_percentage_answer_to_a_count_question_is_blocked():
    validation = _validate({"text": "36% of adults rated the standards as poor."})

    assert "ANSWER_TYPE_MISMATCH" in validation.failure_codes
    assert validation.application_abstain is True


def test_a_count_computed_from_the_percentage_passes():
    validation = _validate(
        {
            "text": "About 541 adults (36% of 1,503) rated the standards as poor.",
            "calculation": {"expression": "36 / 100 * 1503", "result": "541"},
        }
    )

    assert validation.failure_codes == []
