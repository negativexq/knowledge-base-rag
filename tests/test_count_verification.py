"""Count answers ("13 geographic market names are listed", "Unit 8 lists 10
learning outcomes") state a number no unit prints: the units list the things
counted. The arithmetic check cannot help, since its operands would be
counts too (399: "4 + 3"). With derived answers a part may carry "counts":
each count lists the counted items copied from the cited units, and code
checks every item is there, once. A verified count is evidence for its
number, also as a calculation operand."""

import json

from app.evaluation.mmlongbench import answer_matches
from app.evidence.support_units import build_support_units
from app.llm.counting import Count, verify_count
from app.llm.structured_output import (
    DERIVED_ANSWER_INSTRUCTIONS,
    parse_support_unit_answer,
    render_support_unit_answer,
    support_unit_output_schema,
    validate_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult

MARKETS = "Los Angeles area: CA14 San Fernando Valley (West), CA15 Burbank, CA16 East Los Angeles"


def test_a_count_of_items_the_support_lists_is_verified():
    count = Count(("San Fernando Valley (West)", "Burbank", "east los  angeles"))

    assert verify_count(count, [MARKETS]) == []
    assert count.result == 3
    assert count.fact() == "count of listed items = 3"


def test_an_item_the_support_does_not_list_fails():
    assert verify_count(Count(("Burbank", "Pasadena")), [MARKETS]) == ["COUNT_ITEM_NOT_IN_SUPPORT"]


def test_an_item_counted_twice_fails():
    assert verify_count(Count(("Burbank", "burbank.")), [MARKETS]) == ["COUNT_ITEM_DUPLICATE"]


def test_an_empty_count_fails():
    assert verify_count(Count(()), [MARKETS]) == ["COUNT_EMPTY"]
    assert verify_count(Count(("—",)), [MARKETS]) == ["COUNT_EMPTY"]


def test_the_derived_schema_and_prompt_carry_counts():
    units = build_support_units([_evidence(MARKETS)])
    part = support_unit_output_schema(units, derived_answers=True)["properties"]["answer_parts"]
    assert "counts" in part["items"]["required"]
    assert (
        "counts"
        not in support_unit_output_schema(units)["properties"]["answer_parts"]["items"][
            "properties"
        ]
    )
    assert '"counts"' in DERIVED_ANSWER_INSTRUCTIONS


def _evidence(text: str) -> SearchResult:
    return SearchResult(
        score=1.0,
        id="c",
        payload={
            "evidence_id": "E1",
            "evidence_block_id": "b",
            "source_id": "doc",
            "document_version": "v",
            "tenant_id": "t",
            "heading_path": ["Markets"],
            "contributing_chunk_ids": ["c"],
            "text": text,
        },
    )


def _validate(text: str, **fields):
    units = build_support_units([_evidence(MARKETS)])
    part = {"text": text, "support_ids": [units[0].support_unit_id], **fields}
    answer = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))
    return answer, validate_support_unit_answer(answer, units)


def test_a_verified_count_supports_the_number_the_answer_states():
    items = ["San Fernando Valley (West)", "Burbank", "East Los Angeles"]

    answer, validation = _validate(
        "3 geographic market names are listed under the Los Angeles area.",
        counts=[{"items": items}],
    )

    assert validation.failure_codes == []
    assert validation.validator_telemetry["counts"] == 1
    assert "(count: 3 listed items)" in render_support_unit_answer(answer.answer_parts)


def test_without_a_count_the_number_is_still_blocked():
    _, validation = _validate("3 geographic market names are listed under the Los Angeles area.")

    assert validation.application_abstain is True


def test_a_count_with_an_unlisted_item_rejects_the_part():
    _, validation = _validate(
        "4 geographic market names are listed.",
        counts=[{"items": ["Burbank", "Pasadena", "Glendale", "Long Beach"]}],
    )

    assert "COUNT_ITEM_NOT_IN_SUPPORT" in validation.failure_codes
    assert validation.application_abstain is True


def test_verified_counts_are_operands_of_a_calculation():
    _, validation = _validate(
        "There are 3 markets: 2 in the valley and 1 in the east.",
        counts=[
            {"items": ["San Fernando Valley (West)", "Burbank"]},
            {"items": ["East Los Angeles"]},
        ],
        calculation={"expression": "2 + 1", "result": "3"},
    )

    assert validation.failure_codes == []


def test_a_count_answer_is_scored_by_its_count():
    assert answer_matches(
        "Unit 8 lists 10 learning outcomes to answer. (count: 10 listed items) [E1.S38]",
        "10",
        "Int",
    )


def test_a_calculation_beside_a_verified_count_of_its_result_is_not_needed():
    # luna 835: 10 counted outcomes verified, but the model also wrote "3 + 7",
    # whose operands are not printed; the count already establishes the number.
    items = ["San Fernando Valley (West)", "Burbank", "East Los Angeles"]

    _, validation = _validate(
        "3 geographic market names are listed.",
        counts=[{"items": items}],
        calculation={"expression": "1 + 2", "result": "3"},
    )

    assert validation.failure_codes == []
    assert validation.validator_telemetry["redundant_calculations"] == 1


def test_a_calculation_of_another_number_is_still_checked():
    _, validation = _validate(
        "3 geographic market names are listed, 9 in all.",
        counts=[{"items": ["San Fernando Valley (West)", "Burbank", "East Los Angeles"]}],
        calculation={"expression": "4 + 5", "result": "9"},
    )

    assert "CALCULATION_OPERAND_UNSUPPORTED" in validation.failure_codes


def test_the_prompt_does_not_ask_counted_operands_to_come_as_counts():
    # Asking for every counted number as a count (for 399's "4 + 3") gained
    # nothing in the luna format rerun and cost three correct calculations
    # (371, 741, 1015), where the model abstained instead; it was reverted.
    assert "every number you counted" not in DERIVED_ANSWER_INSTRUCTIONS
    assert "a count may be a number in the calculation" in DERIVED_ANSWER_INSTRUCTIONS
