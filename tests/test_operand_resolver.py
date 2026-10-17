"""The operand resolver (app/llm/operand_resolver.py): a withheld answer to a
computed question gets a plan over named operands; code binds each operand to
its unit (value and labels printed there), searches once for missing ones,
and computes. Cases from the luna full-run abstentions on 10-K ratios
(1015, 1021, 1024)."""

import json

import pytest

from app.evidence.support_units import build_support_units
from app.llm.operand_resolver import (
    Operand,
    OperandPlan,
    bind_operand,
    compute,
    parse_operand_plan,
    plan_codes,
    render_part_text,
    resolve_operands,
)
from app.retrieval.hybrid_search import SearchResult

BALANCE = (
    "Consolidated Balance Sheets | Total current liabilities | 2021: 29,441 | 2020: 24,844 | "
    "Total liabilities | 2021: 41,190 | 2020: 36,851"
)
CASH = (
    "Consolidated Statements of Cash Flows | Net cash provided by operating activities | "
    "2021: 8,958"
)


def _units(*texts: str, prefix: str = "E"):
    return build_support_units(
        [
            SearchResult(
                score=1.0,
                id=f"c{index}",
                payload={
                    "evidence_id": f"{prefix}{index}",
                    "evidence_block_id": f"b{prefix}{index}",
                    "source_id": "costco",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Statements"],
                    "contributing_chunk_ids": [f"c{index}"],
                    "text": text,
                },
            )
            for index, text in enumerate(texts, 1)
        ]
    )


def _operand(name, value, labels, support_id="E1.S1", what="figure"):
    return Operand(name, what, value, support_id, tuple(labels), None)


def test_an_operand_binds_when_its_unit_prints_the_value_and_labels():
    units = {unit.support_unit_id: unit for unit in _units(BALANCE)}

    assert bind_operand(_operand("a", "29,441", ["Total current liabilities", "2021"]), units) == []
    assert bind_operand(_operand("a", "29,441", ["Total assets", "2021"]), units) == [
        "OPERAND_LABEL_NOT_IN_UNIT"
    ]
    assert bind_operand(_operand("a", "29,442", ["Total current liabilities"]), units) == [
        "OPERAND_VALUE_NOT_IN_UNIT"
    ]
    assert bind_operand(_operand("a", "29,441", []), units) == ["OPERAND_LABELS_MISSING"]
    assert bind_operand(_operand("a", None, ["x"], support_id=None), units) == ["OPERAND_MISSING"]


def test_a_program_uses_only_its_operands_and_allowed_operators():
    operands = (_operand("a", "1", ["x"]), _operand("b", "2", ["y"]))

    assert plan_codes(OperandPlan("a / b", operands, "r", False, None)) == []
    assert plan_codes(OperandPlan("(a - b) / b * 100", operands, "r", True, 2)) == []
    assert plan_codes(OperandPlan("a / c", operands, "r", False, None)) == ["PROGRAM_INVALID"]
    assert plan_codes(OperandPlan("__import__('os')", operands, "r", False, None)) == [
        "PROGRAM_INVALID"
    ]
    assert plan_codes(OperandPlan(None, operands, "r", False, None)) == ["NO_CALCULATION_ASKED"]


def test_the_program_is_computed_by_code_at_the_asked_precision():
    plan = OperandPlan(
        "a / b",
        (_operand("a", "29,441", ["x"]), _operand("b", "41,190", ["y"])),
        "Current liabilities to total liabilities, FY2021",
        False,
        3,
    )
    calculation = compute(plan)

    assert (calculation.expression, calculation.result) == ("29441 / 41190", "0.715")
    assert render_part_text(plan, calculation) == (
        "Current liabilities to total liabilities, FY2021: 0.715 (figure: 29,441; figure: 41,190)."
    )


class _Provider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
        return json.dumps(self.outputs.pop(0))


def _plan_json(operands, program="a / b", decimals=3):
    return {
        "program": program,
        "operands": operands,
        "result_label": "Operating cash flow to current liabilities, FY2021",
        "percent": False,
        "decimals": decimals,
    }


def _op(name, value, support_id, labels, search=None):
    return {
        "name": name,
        "what": name,
        "value": value,
        "support_id": support_id,
        "labels": labels,
        "search": search,
    }


@pytest.mark.asyncio
async def test_operands_in_the_evidence_are_computed_without_a_search():
    units = _units(BALANCE, CASH)
    provider = _Provider(
        _plan_json(
            [
                _op("a", "8,958", "E2.S1", ["Net cash provided by operating activities", "2021"]),
                _op("b", "29,441", "E1.S1", ["Total current liabilities", "2021"]),
            ]
        )
    )

    async def retrieve(query):
        raise AssertionError("no search when every operand is bound")

    plan, calculation, _, trace = await resolve_operands(
        "Operating cash flow to current liabilities for Costco in FY2021?",
        units,
        provider,
        generation_kwargs={"model": "m"},
        prompt_version="v3",
        context_serializer=None,
        retrieve=retrieve,
    )

    assert calculation is not None and calculation.result == "0.304"
    assert trace.searches == [] and provider.calls == 1


@pytest.mark.asyncio
async def test_a_missing_operand_is_searched_once_then_bound():
    units = _units(BALANCE)
    first = _plan_json(
        [
            _op(
                "a", None, None, [], search="Costco net cash provided by operating activities 2021"
            ),
            _op("b", "29,441", "E1.S1", ["Total current liabilities", "2021"]),
        ]
    )
    second = _plan_json(
        [
            _op("a", "8,958", "R1.S1", ["Net cash provided by operating activities", "2021"]),
            _op("b", "29,441", "E1.S1", ["Total current liabilities", "2021"]),
        ]
    )
    provider = _Provider(first, second)
    searched = []

    async def retrieve(query):
        searched.append(query)
        return [
            SearchResult(
                score=1.0,
                id="cash",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "bcash",
                    "source_id": "costco",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Cash"],
                    "contributing_chunk_ids": ["cash"],
                    "text": CASH,
                },
            )
        ]

    plan, calculation, all_units, trace = await resolve_operands(
        "Operating cash flow to current liabilities for Costco in FY2021?",
        units,
        provider,
        generation_kwargs={"model": "m"},
        prompt_version="v3",
        context_serializer=None,
        retrieve=retrieve,
    )

    assert searched == ["Costco net cash provided by operating activities 2021"]
    assert "R1.S1" in {unit.support_unit_id for unit in all_units}
    assert calculation is not None and calculation.result == "0.304"


@pytest.mark.asyncio
async def test_an_operand_whose_labels_are_not_in_its_unit_yields_nothing():
    units = _units(BALANCE)
    provider = _Provider(
        _plan_json(
            [
                _op("a", "29,441", "E1.S1", ["Total current liabilities", "2021"]),
                _op("b", "41,190", "E1.S1", ["Total equity", "2021"]),
            ]
        )
    )

    plan, calculation, _, trace = await resolve_operands(
        "Current liabilities to total equity for Costco in FY2021?",
        units,
        provider,
        generation_kwargs={"model": "m"},
        prompt_version="v3",
        context_serializer=None,
    )

    assert calculation is None
    assert trace.operand_codes["b"] == ["OPERAND_LABEL_NOT_IN_UNIT"]


def test_a_plan_parses_from_the_model_json():
    plan = parse_operand_plan(
        json.dumps(_plan_json([_op("a", "1", "E1.S1", ["x"]), _op("b", "2", "E1.S1", ["y"])]))
    )

    assert plan.program == "a / b" and plan.decimals == 3
    assert [operand.labels for operand in plan.operands] == [("x",), ("y",)]


def _blocks(*texts):
    return [
        SearchResult(
            score=1.0,
            id=f"c{index}",
            payload={
                "evidence_id": f"E{index}",
                "evidence_block_id": f"b{index}",
                "source_id": "costco",
                "document_version": "v",
                "tenant_id": "t",
                "heading_path": ["Statements"],
                "contributing_chunk_ids": [f"c{index}"],
                "text": text,
            },
        )
        for index, text in enumerate(texts, 1)
    ]


async def _run(provider, *, operand_resolver, retrieve=None):
    from app.llm.structured_output import stream_support_unit_answer

    events = [
        event
        async for event in stream_support_unit_answer(
            "What is Costco's operating cash flow to current liabilities ratio in FY2021?",
            _blocks(BALANCE, CASH),
            provider,
            model="m",
            derived_answers=True,
            operand_resolver=operand_resolver,
            retrieve=retrieve,
        )
    ]
    answer = "".join(event["content"] for event in events if event["type"] == "token")
    validation = next(event for event in events if event["type"] == "security_validation")
    return answer, validation


ABSTAIN = {"answer_parts": [], "abstain": True}
RATIO_PLAN = _plan_json(
    [
        _op("a", "8,958", "E2.S1", ["Net cash provided by operating activities", "2021"]),
        _op("b", "29,441", "E1.S1", ["Total current liabilities", "2021"]),
    ]
)


@pytest.mark.asyncio
async def test_a_withheld_answer_is_resolved_and_validated():
    answer, validation = await _run(_Provider(ABSTAIN, RATIO_PLAN), operand_resolver=True)

    assert validation["passed"] is True and validation["abstain"] is False
    assert "0.304" in answer and "(calculation: 8958 / 29441 = 0.304)" in answer


@pytest.mark.asyncio
async def test_without_the_resolver_the_abstention_stands():
    provider = _Provider(ABSTAIN, RATIO_PLAN)
    answer, validation = await _run(provider, operand_resolver=False)

    assert validation["abstain"] is True and provider.calls == 1


@pytest.mark.asyncio
async def test_an_unbound_plan_leaves_the_abstention():
    bad = _plan_json(
        [
            _op("a", "8,958", "E2.S1", ["Net cash provided by operating activities", "2021"]),
            _op("b", "29,441", "E1.S1", ["Total current assets", "2021"]),
        ]
    )
    answer, validation = await _run(_Provider(ABSTAIN, bad), operand_resolver=True)

    assert validation["abstain"] is True


@pytest.mark.asyncio
async def test_a_question_that_asks_no_calculation_keeps_its_abstention():
    none = {**RATIO_PLAN, "program": None}
    answer, validation = await _run(_Provider(ABSTAIN, none), operand_resolver=True)

    assert validation["abstain"] is True


# luna resolver rows: a 10-K table row prints no column header
# ("Long-term debt, excluding current portion | 6,692 | 7,514"); the year is in
# the table's header row, elsewhere in the same block. At least one label must
# be in the operand's unit, the others may be in its block. 1072-1075 and 1084
# returned program null for named ratios, 727 for a difference whose values it
# had not found.

TABLE_BLOCK = (
    "Table: CONSOLIDATED BALANCE SHEETS | 2021 | 2020\n\n"
    "ASSETS: Long-term debt, excluding current portion | 6,692 | 7,514\n\n"
    "ASSETS: TOTAL LIABILITIES | 41,190 | 36,851"
)


def test_a_column_label_may_be_in_the_operands_block():
    from app.llm.operand_resolver import block_texts

    units = _units(TABLE_BLOCK)
    available = {unit.support_unit_id: unit for unit in units}
    row = next(u for u in units if "Long-term debt" in u.text)
    op = _operand(
        "a", "6,692", ["Long-term debt, excluding current portion", "2021"], row.support_unit_id
    )

    # Without its block the row has no column, so the value is unresolved.
    assert bind_operand(op, available) == ["OPERAND_FACT_UNRESOLVED"]
    assert bind_operand(op, available, block_texts(units)) == []
    # A label found nowhere, or labels only in the block, still fail.
    assert bind_operand(
        _operand("a", "6,692", ["Total equity", "2021"], row.support_unit_id),
        available,
        block_texts(units),
    ) == ["OPERAND_LABEL_NOT_IN_UNIT"]
    assert bind_operand(
        _operand("a", "6,692", ["2021", "2020"], row.support_unit_id),
        available,
        block_texts(units),
    ) == ["OPERAND_LABEL_NOT_IN_UNIT"]


def test_the_instructions_ask_for_named_ratios_and_programs_with_missing_values():
    from app.llm.operand_resolver import RESOLVER_INSTRUCTIONS

    assert "standard definition" in RESOLVER_INSTRUCTIONS
    assert "even when some operand values are missing" in RESOLVER_INSTRUCTIONS


# luna V2 rows 206, 216, 219, 225: a survey report prints the share of a group
# ("36% rate them as poor") and, in its methodology, the group's sample size
# ("Total sample | 1,503"); "how many adults" is the share times the size.
# The first answers stated the percentage and the type check blocked them;
# the resolver returned program null.

SURVEY_QUESTION = (
    "Among the adults conducted the survey on April 25 - May 1 2018, how many adults "
    "rated Trump's government ethical standards as poor?"
)
ETHICS = "Ratings of the ethical standards of top Trump administration officials: 36% poor."
SAMPLE = (
    "Table: Group | Unweighted sample size | Plus or minus\n"
    "Survey conducted April 25-May 1, 2018\n"
    "Total sample | 1,503 | 2.9 percentage points\n"
    "Dem/Lean Dem | 710 | 4.3 percentage points"
)


def _share_plan(percent=False, decimals=None, program="a / 100 * b"):
    return {
        "program": program,
        "operands": [
            _op("a", "36%", "E1.S1", ["poor"]),
            _op("b", "1,503", "E2.S1", ["Total sample"]),
        ],
        "result_label": "Adults who rated the ethical standards as poor",
        "percent": percent,
        "decimals": decimals,
    }


async def _resolve(question, plan):
    return await resolve_operands(
        question,
        _units(ETHICS, SAMPLE),
        _Provider(plan),
        generation_kwargs={"model": "m"},
        prompt_version="v3",
        context_serializer=None,
    )


@pytest.mark.asyncio
async def test_a_count_from_a_share_of_a_sample_is_a_whole_number():
    plan, calculation, _, trace = await _resolve(SURVEY_QUESTION, _share_plan())

    assert calculation is not None
    assert (calculation.expression, calculation.result) == ("36 / 100 * 1503", "541")


@pytest.mark.asyncio
async def test_a_count_question_is_not_answered_with_a_percentage():
    plan, calculation, _, trace = await _resolve(
        SURVEY_QUESTION, _share_plan(percent=True, program="a")
    )

    assert calculation is None
    assert trace.plan_codes == ["PERCENT_PLAN_FOR_COUNT_QUESTION"]


@pytest.mark.asyncio
async def test_how_many_times_keeps_the_default_decimals():
    plan, calculation, _, trace = await _resolve(
        "How many times the share rating poor is the total sample?",
        _share_plan(program="b / a"),
    )

    assert calculation is not None and calculation.result == "41.75"


@pytest.mark.asyncio
async def test_a_blocked_percentage_for_a_count_is_resolved_from_the_sample_size():
    from app.llm.structured_output import stream_support_unit_answer

    first = {
        "answer_parts": [
            {
                "text": "36% of adults rated the ethical standards as poor.",
                "support_ids": ["E1.S1"],
                "calculation": None,
                "counts": None,
            }
        ],
        "abstain": False,
    }
    events = [
        event
        async for event in stream_support_unit_answer(
            SURVEY_QUESTION,
            _blocks(ETHICS, SAMPLE),
            _Provider(first, _share_plan()),
            model="m",
            derived_answers=True,
            operand_resolver=True,
        )
    ]
    answer = "".join(event["content"] for event in events if event["type"] == "token")
    validation = next(event for event in events if event["type"] == "security_validation")

    assert validation["passed"] is True and validation["abstain"] is False
    assert "(calculation: 36 / 100 * 1503 = 541)" in answer


def test_the_instructions_ask_for_counts_from_shares_of_a_sample():
    from app.llm.operand_resolver import RESOLVER_INSTRUCTIONS

    assert "sample size" in RESOLVER_INSTRUCTIONS
