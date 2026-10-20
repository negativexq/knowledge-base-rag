"""Derived answers: an answer part may carry the calculation behind a number
that is not printed in the evidence ("41% do not go online" from "59% go
online"). The calculation is checked deterministically, never by a model:
the expression is parsed safely, every number in it must appear in the
part's cited support units (100 is allowed for percentage remainders), the
result is recomputed and must match, and the answer text must state it.
A verified calculation counts as evidence for the critical-value check; a
wrong one rejects the part."""

import json

import pytest

from app.evidence.support_units import build_support_units
from app.llm.calculation import Calculation, evaluate_expression, verify_calculation
from app.llm.structured_output import (
    parse_support_unit_answer,
    render_support_unit_answer,
    stream_support_unit_answer,
    support_unit_output_schema,
    validate_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult


def evidence(text: str) -> SearchResult:
    return SearchResult(
        score=1.0,
        id="chunk-1",
        payload={
            "evidence_id": "E1",
            "evidence_block_id": "block-1",
            "source_id": "survey",
            "document_version": "v1",
            "tenant_id": "tenant-a",
            "heading_path": ["Internet use"],
            "contributing_chunk_ids": ["chunk-1"],
            "text": text,
        },
    )


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("100 - 59", 41),
        ("(8873.49 - 913.01)", 7960.48),
        ("59 / 2", 29.5),
        ("-3 + 5 * 2", 7),
        ("abs(-3)", 3),
        ("min(3,7)", 3),
        ("max(3,7)", 7),
        ("mean(3,7)", 5),
    ],
)
def test_arithmetic_expressions_are_evaluated(expression, value):
    assert evaluate_expression(expression) == pytest.approx(value)


@pytest.mark.parametrize(
    "expression", ["__import__('os').system('x')", "2 ** 10", "abs(-3,2)", "1 / 0", "x + 1", ""]
)
def test_unsupported_arithmetic_is_refused(expression):
    with pytest.raises(ValueError):
        evaluate_expression(expression)


SUPPORT = ["59% of seniors go online, compared with 86% of all U.S. adults."]


def test_a_correct_calculation_from_cited_numbers_is_verified():
    calculation = Calculation(expression="100 - 59", result="41")

    assert verify_calculation(calculation, SUPPORT, "41% of seniors do not go online.") == []


@pytest.mark.parametrize(
    ("calculation", "text", "code"),
    [
        (Calculation("100 - 60", "40"), "40% do not go online.", "CALCULATION_OPERAND_UNSUPPORTED"),
        (Calculation("100 - 59", "45"), "45% do not go online.", "CALCULATION_RESULT_MISMATCH"),
        (
            Calculation("100 - 59", "41"),
            "Most seniors go online.",
            "CALCULATION_RESULT_NOT_IN_ANSWER",
        ),
        (Calculation("59 ** 2", "3481"), "3481", "CALCULATION_UNPARSEABLE"),
    ],
)
def test_a_wrong_calculation_is_rejected(calculation, text, code):
    assert code in verify_calculation(calculation, SUPPORT, text)


def test_numbers_with_thousands_separators_and_rounding_match():
    support = ["Respondents: 6,010 adults, of whom 1,526 were 65 or older."]
    calculation = Calculation(expression="1526 / 6010 * 100", result="25.4")

    assert verify_calculation(calculation, support, "About 25.4% were 65 or older.") == []


def _answer(part: dict) -> str:
    return json.dumps({"answer_parts": [part], "abstain": False})


def test_a_verified_calculation_lets_a_derived_number_through_validation():
    units = build_support_units([evidence(SUPPORT[0])])
    part = {
        "text": "41% of seniors do not go online.",
        "support_ids": ["E1.S1"],
        "calculation": {"expression": "100 - 59", "result": "41"},
    }

    validation = validate_support_unit_answer(parse_support_unit_answer(_answer(part)), units)

    assert [p.text for p in validation.valid_parts] == ["41% of seniors do not go online."]


def test_the_same_number_without_a_calculation_is_still_rejected():
    units = build_support_units([evidence(SUPPORT[0])])
    part = {"text": "41% of seniors do not go online.", "support_ids": ["E1.S1"]}

    validation = validate_support_unit_answer(parse_support_unit_answer(_answer(part)), units)

    assert validation.valid_parts == []


def test_a_wrong_calculation_rejects_the_part():
    units = build_support_units([evidence(SUPPORT[0])])
    part = {
        "text": "45% of seniors do not go online.",
        "support_ids": ["E1.S1"],
        "calculation": {"expression": "100 - 59", "result": "45"},
    }

    validation = validate_support_unit_answer(parse_support_unit_answer(_answer(part)), units)

    assert validation.valid_parts == []
    assert "CALCULATION_RESULT_MISMATCH" in validation.failure_codes


def test_a_null_calculation_is_an_ordinary_part():
    answer = parse_support_unit_answer(
        _answer({"text": "59% go online.", "support_ids": ["E1.S1"], "calculation": None})
    )

    assert answer.answer_parts[0].calculation is None


def test_the_answer_shows_the_calculation():
    answer = parse_support_unit_answer(
        _answer(
            {
                "text": "41% of seniors do not go online.",
                "support_ids": ["E1.S1"],
                "calculation": {"expression": "100 - 59", "result": "41"},
            }
        )
    )

    assert render_support_unit_answer(answer.answer_parts) == (
        "41% of seniors do not go online. (calculation: 100 - 59 = 41) [E1.S1]"
    )


def test_the_schema_offers_a_calculation_only_when_derived_answers_are_on():
    units = build_support_units([evidence(SUPPORT[0])])
    part_without = support_unit_output_schema(units)["properties"]["answer_parts"]["items"]
    part_with = support_unit_output_schema(units, derived_answers=True)["properties"][
        "answer_parts"
    ]["items"]

    assert "calculation" not in part_without["properties"]
    assert "calculation" in part_with["properties"]
    assert "calculation" in part_with["required"]


@pytest.mark.parametrize(
    ("text", "fact"),
    [
        ("41% of seniors do not go online.", "100 - 59 = 41%"),
        ("The gap is 41 percent.", "100 - 59 = 41 percent"),
        ("Net profit was 41 crore.", "100 - 59 = 41 crore"),
        ("The answer is 41.", "100 - 59 = 41"),
    ],
)
def test_the_evidence_line_keeps_the_unit_the_answer_states(text, fact):
    assert Calculation("100 - 59", "41").fact(text) == fact


# --- the stream: off by default, on with derived_answers -------------------


def _block() -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "text": SUPPORT[0],
            "source_type": "filesystem",
            "source_id": "survey",
            "page_number": 5,
            "paragraph_index": 0,
            "tenant_id": "tenant-a",
            "authorized": True,
            "model_visible": True,
        },
    )


class _Provider:
    def __init__(self):
        self.messages, self.kwargs = [], {}

    async def chat_json(self, messages, **kwargs):
        self.messages, self.kwargs = messages, kwargs
        part = {
            "text": "41% of seniors do not go online.",
            "support_ids": ["E1.S1"],
            "calculation": {"expression": "100 - 59", "result": "41"},
        }
        return json.dumps({"answer_parts": [part], "abstain": False})


async def _ask(provider, **options) -> str:
    answer = ""
    async for event in stream_support_unit_answer(
        "What share of seniors do not go online?", [_block()], provider, model="m", **options
    ):
        if event["type"] == "token":
            answer += event["content"]
    return answer


@pytest.mark.asyncio
async def test_derived_answers_send_the_calculation_contract_and_release_verified_numbers():
    provider = _Provider()

    answer = await _ask(provider, derived_answers=True)

    system = provider.messages[0]["content"]
    assert '"calculation"' in system
    part = provider.kwargs["schema"]["properties"]["answer_parts"]["items"]
    assert "calculation" in part["properties"]
    assert "41% of seniors do not go online. (calculation: 100 - 59 = 41)" in answer


@pytest.mark.asyncio
async def test_without_derived_answers_the_contract_is_unchanged():
    provider = _Provider()

    await _ask(provider)

    assert '"calculation"' not in provider.messages[0]["content"]
    part = provider.kwargs["schema"]["properties"]["answer_parts"]["items"]
    assert "calculation" not in part["properties"]


# MMLongBench V2 row 380: Godfrey Phillips prints its accounts "Rupees in
# lacs"; "how much less ... in rupees" is (109,638.91 - 25,966.14) lakh, times
# 100,000 = 8,367,277,000 rupees. A stated scale is evidence for its factor.


def test_a_stated_scale_supports_its_factor():
    calculation = Calculation("(109638.91 - 25966.14) * 100000", "8,367,277,000")
    texts = ["Rupees in lacs", "Total income | 109638.91", "Shareholders' funds | 25966.14"]
    text = "Shareholders' funds were 8,367,277,000 rupees less than income."

    assert verify_calculation(calculation, texts, text) == []
    assert verify_calculation(calculation, texts[1:], text) == ["CALCULATION_OPERAND_UNSUPPORTED"]


def test_a_factor_needs_the_scale_the_units_state():
    calculation = Calculation("(109638.91 - 25966.14) * 1000", "83,672,770")
    texts = ["Rupees in lacs", "Total income | 109638.91", "Shareholders' funds | 25966.14"]

    assert verify_calculation(calculation, texts, "83,672,770") == [
        "CALCULATION_OPERAND_UNSUPPORTED"
    ]


# MMLongBench V2 row 1070: "the change of Best Buy's gross margins from FY2022
# to FY2021 ... round to 2 decimal places" was answered 22.5 - 22.4 = 0.10 from
# the rates the table prints to one decimal; the gold, 0.12, is computed from
# gross profit and revenue (11,640 / 51,761 - 10,573 / 47,262). A sum or
# difference of rates cannot carry more decimals than the rates.

MARGINS = (
    "Table: Consolidated Performance Summary | 2022 | | 2021 |\n"
    "Consolidated Performance Summary: Revenue | 2022: $ 51,761 | 2021: $ 47,262\n"
    "Consolidated Performance Summary: Gross profit | 2022: $ 11,640 | 2021: $ 10,573\n"
    "Consolidated Performance Summary: Gross profit as a % of revenue(1) | "
    "2022: 22.5 | % | 2021: 22.4 | %"
)
MARGIN_QUESTION = (
    "what is the change of Best Buy's gross margins change from FY2022 to FY2021? "
    "Answer in percentage terms, round to 2 decimal places."
)


def _margin_validation(expression, result, text, question=MARGIN_QUESTION):
    units = build_support_units([evidence(MARGINS)])
    ids = [unit.support_unit_id for unit in units]
    answer = parse_support_unit_answer(
        json.dumps(
            {
                "answer_parts": [
                    {
                        "text": text,
                        "support_ids": ids,
                        "calculation": {"expression": expression, "result": result},
                        "counts": None,
                    }
                ],
                "abstain": False,
            }
        )
    )
    return validate_support_unit_answer(answer, units, question=question)


def test_a_difference_of_rounded_rates_cannot_answer_more_decimals():
    validation = _margin_validation(
        "22.5 - 22.4", "0.10", "Gross margin rose by 0.10 percentage points."
    )

    assert "CALCULATION_PRECISION_BELOW_ASKED" in validation.failure_codes


def test_rates_computed_from_their_figures_carry_the_asked_decimals():
    validation = _margin_validation(
        "(11640 / 51761 - 10573 / 47262) * 100",
        "0.12",
        "Gross margin rose by 0.12 percentage points.",
    )

    assert "CALCULATION_PRECISION_BELOW_ASKED" not in validation.failure_codes


def test_rounded_rates_stand_when_no_more_decimals_are_asked():
    validation = _margin_validation(
        "22.5 - 22.4",
        "0.1",
        "Gross margin rose by 0.1 percentage points.",
        question="How did Best Buy's gross margin change from FY2021 to FY2022?",
    )

    assert "CALCULATION_PRECISION_BELOW_ASKED" not in validation.failure_codes


def test_whole_counts_are_exact_at_any_asked_precision():
    validation = _margin_validation(
        "11640 - 10573",
        "1067",
        "Gross profit rose by $1,067 million.",
        question="By how much did gross profit grow? Round to 2 decimal places.",
    )

    assert "CALCULATION_PRECISION_BELOW_ASKED" not in validation.failure_codes
