"""Two losses in the luna derived-answer rerun of the 39 blocked rows:

- The scorer reads the first number an answer states, but a computed answer
  states its operands first ("10 of the 24 tweets, or 41.7%"), so four correct
  derived answers (214, 371, 509, 741) scored wrong. An answer that carries a
  verified calculation is scored by the calculation's result.
- 373: "lower by 155.98 lacs" with the calculation "1767.80 - 1923.78 =
  -155.98" was a CALCULATION_RESULT_MISMATCH: the result's minus sign was
  dropped when it was read. A negative result may be stated as its magnitude
  when the answer says it is a decrease."""

import pytest

from app.evaluation.mmlongbench import answer_matches
from app.llm.calculation import Calculation, verify_calculation

SHARE = (
    "English tweets were 10 of the 24 Germanwings tweets, or 41.7%. "
    "(calculation: 10 / 24 * 100 = 41.7%) [E1.S124]"
)


def test_a_computed_answer_is_scored_by_its_calculation_result():
    assert answer_matches(SHARE, "41.67", "Float")
    assert answer_matches(
        "Mr. Shah holds 14, Mr. Shanbhag 5 and Mr. Maniar 11, for 30 in all. "
        "(calculation: 14 + 5 + 11 = 30)",
        "30",
        "Int",
    )


def test_a_computed_answer_with_the_wrong_result_still_scores_wrong():
    assert not answer_matches(SHARE, "10", "Int")


def test_an_answer_without_a_calculation_is_scored_as_before():
    assert not answer_matches("10 of the 24 tweets were English, or 41.7%.", "41.67", "Float")


DIVIDEND = ["Proposed dividend | 1,767.80 | 1,923.78"]
DROP = Calculation("1767.80 - 1923.78", "-155.98")


def test_a_decrease_may_be_stated_as_its_magnitude():
    text = "The proposed dividend was lower by 155.98 lacs in 2002 than in 2001."

    assert verify_calculation(DROP, DIVIDEND, text) == []
    assert DROP.fact(text) == "1767.80 - 1923.78 = -155.98"


@pytest.mark.parametrize(
    "text", ["The proposed dividend rose by 155.98 lacs.", "The dividend was 155.98 lacs."]
)
def test_a_magnitude_without_a_decrease_word_is_not_the_result(text):
    assert verify_calculation(DROP, DIVIDEND, text) == ["CALCULATION_RESULT_NOT_IN_ANSWER"]


def test_a_result_with_the_wrong_sign_is_a_mismatch():
    assert verify_calculation(Calculation("1767.80 - 1923.78", "155.98"), DIVIDEND, "x") == [
        "CALCULATION_RESULT_MISMATCH"
    ]


def test_the_373_answer_passes_validation_end_to_end():
    import json

    from app.evidence.support_units import build_support_units
    from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
    from app.retrieval.hybrid_search import SearchResult

    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="c",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "b",
                    "source_id": "annual-report",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Accounts"],
                    "contributing_chunk_ids": ["c"],
                    "text": f"Profit and loss account | 2002 | 2001\n\n{DIVIDEND[0]}",
                },
            )
        ]
    )
    row = next(unit.support_unit_id for unit in units if unit.text == DIVIDEND[0])
    part = {
        "text": "The proposed dividend was not higher in 2002; it was lower by 155.98 lacs "
        "(1,767.80 lacs in 2002 versus 1,923.78 lacs in 2001).",
        "support_ids": [row],
        "calculation": {"expression": DROP.expression, "result": DROP.result},
    }
    answer = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))

    validation = validate_support_unit_answer(
        answer,
        units,
        question="How much higher was the proposed dividend paid (Rupees in lacs) in 2002 "
        "compared to 2001?",
    )

    assert validation.failure_codes == []
    assert validation.application_abstain is False


def test_a_calculation_with_parentheses_is_scored_by_its_result():
    # luna 741: "10 / (10 + 14) * 100 = 41.7" was missed and the first number
    # (24) scored instead.
    assert answer_matches(
        "Germanwings posted 24 tweets: 10 in English and 14 in German. English tweets were "
        "41.7% of the total. (calculation: 10 / (10 + 14) * 100 = 41.7) [E1.S124]",
        "41.67",
        "Float",
    )
