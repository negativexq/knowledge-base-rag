"""Table facts (app/evidence/table_facts.py) and the resolver's binding to
them. The parser prints each table row as "Row | Column: value | ...", so a
value, its row label and its column are read from one line. An operand found
in a table binds only to exactly one fact whose row and column its labels
name; a value printed in a row whose column or row cannot be read is
unresolved, never guessed. A value printed only in prose keeps the text
binding."""

import json

import pytest

from app.evidence.support_units import build_support_units
from app.evidence.table_facts import unit_facts
from app.llm.operand_resolver import Operand, bind_operand, block_texts, resolve_operands
from app.retrieval.hybrid_search import SearchResult

BALANCE_SHEET = (
    "Table:  | August 29, 2021 | August 30, 2020\n"
    "OTHER LIABILITIES\n"
    "Long-term debt, excluding current portion | August 29, 2021: 6,692 | August 30, 2020: 7,514\n"
    "TOTAL LIABILITIES | August 29, 2021: 41,190 | August 30, 2020: 36,851"
)


def _units(*texts):
    return build_support_units(
        [
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
    )


def _bind(text, value, labels):
    units = _units(text)
    available = {unit.support_unit_id: unit for unit in units}
    operand = Operand("a", "figure", value, units[0].support_unit_id, tuple(labels), None)
    return bind_operand(operand, available, block_texts(units))


def test_each_cell_of_a_table_row_is_a_fact_with_its_row_and_column():
    facts = unit_facts(BALANCE_SHEET).facts

    assert [(f.value, f.row, f.column) for f in facts] == [
        (6692.0, "Long-term debt, excluding current portion", "August 29, 2021"),
        (7514.0, "Long-term debt, excluding current portion", "August 30, 2020"),
        (41190.0, "TOTAL LIABILITIES", "August 29, 2021"),
        (36851.0, "TOTAL LIABILITIES", "August 30, 2020"),
    ]


def test_an_operand_binds_to_the_one_fact_its_labels_name():
    assert (
        _bind(BALANCE_SHEET, "6,692", ["Long-term debt, excluding current portion", "2021"]) == []
    )
    # The value is in the row, the labels name another row.
    assert _bind(BALANCE_SHEET, "6,692", ["TOTAL LIABILITIES", "2021"]) == [
        "OPERAND_LABEL_NOT_IN_UNIT"
    ]
    # The labels name the row but the other year's column.
    assert _bind(BALANCE_SHEET, "6,692", ["Long-term debt", "2020"]) == [
        "OPERAND_LABEL_NOT_IN_UNIT"
    ]


def test_the_same_value_in_two_rows_binds_only_by_its_row_label():
    text = (
        "Table:  | 2021 | 2020\n"
        "Total debt | 2021: 6,692 | 2020: 8,200\n"
        "Long-term debt | 2021: 6,692 | 2020: 7,514"
    )

    assert _bind(text, "6,692", ["Long-term debt", "2021"]) == []
    assert _bind(text, "6,692", ["Total debt", "2021"]) == []
    # A year alone names no row.
    assert _bind(text, "6,692", ["2021"]) == ["OPERAND_LABEL_NOT_IN_UNIT"]
    # A label both rows print names both.
    assert _bind(text, "6,692", ["debt", "2021"]) == ["OPERAND_FACT_AMBIGUOUS"]


def test_the_same_value_in_two_columns_needs_the_column_label():
    text = "Table:  | 2021 | 2020\n2.300% Senior Notes due May 2022 | 2021: $ 800 | 2020: $ 800"

    assert _bind(text, "800", ["2.300% Senior Notes due May 2022", "2021"]) == []
    assert _bind(text, "800", ["2.300% Senior Notes due May 2022"]) == ["OPERAND_FACT_AMBIGUOUS"]


def test_a_value_in_a_column_with_no_header_is_unresolved():
    text = "Long-term debt | 6,692 | 7,514"

    assert unit_facts(text).facts == ()
    assert _bind(text, "6,692", ["Long-term debt", "2021"]) == ["OPERAND_FACT_UNRESOLVED"]


def test_a_cell_with_two_numbers_is_unresolved():
    text = "Table:  | 2021\nLong-term debt | 2021: 6,692 7,514"

    assert _bind(text, "6,692", ["Long-term debt", "2021"]) == ["OPERAND_FACT_UNRESOLVED"]


def test_a_headerless_row_takes_its_columns_from_the_blocks_header_line_by_position():
    block = (
        "Table: CONSOLIDATED BALANCE SHEETS | 2021 | 2020\n\n"
        "Long-term debt, excluding current portion | 6,692 | 7,514\n\n"
        "Other row | 1 | 2 | 3"
    )
    units = _units(block)
    available = {unit.support_unit_id: unit for unit in units}
    row = next(unit for unit in units if "Long-term" in unit.text)
    other = next(unit for unit in units if "Other row" in unit.text)

    def bind(unit, value, labels):
        operand = Operand("a", "figure", value, unit.support_unit_id, tuple(labels), None)
        return bind_operand(operand, available, block_texts(units))

    assert bind(row, "7,514", ["Long-term debt", "2020"]) == []
    # A row with more cells than the header has no column by position.
    assert bind(other, "2", ["Other row"]) == ["OPERAND_FACT_UNRESOLVED"]


def test_a_value_printed_only_in_prose_keeps_the_text_binding():
    text = "Net sales were $192,052 in 2021, an increase of 18%."

    assert unit_facts(text).facts == ()
    assert _bind(text, "192,052", ["Net sales", "2021"]) == []
    assert _bind(text, "192,052", ["Total revenue"]) == ["OPERAND_LABEL_NOT_IN_UNIT"]


def test_a_table_states_its_scale_in_its_header():
    facts = unit_facts("Table: (in millions) | 2021\nRevenue | 2021: 5").facts

    assert facts[0].scale == "millions"


class _Provider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    async def chat_json(self, messages, **kwargs):
        return self.outputs.pop(0)


@pytest.mark.asyncio
async def test_operands_from_tables_of_different_scales_are_not_combined():
    units = _units(
        "Table: (in millions) | 2021\nNet income | 2021: 5,007",
        "Table: (in thousands) | 2021\nTotal equity | 2021: 17,564",
    )
    plan = {
        "program": "a / b",
        "operands": [
            {
                "name": "a",
                "what": "net income",
                "value": "5,007",
                "support_id": "E1.S1",
                "labels": ["Net income", "2021"],
                "search": None,
            },
            {
                "name": "b",
                "what": "equity",
                "value": "17,564",
                "support_id": "E2.S1",
                "labels": ["Total equity", "2021"],
                "search": None,
            },
        ],
        "result_label": "return on equity",
        "percent": False,
        "decimals": 2,
    }

    _, calculation, _, trace = await resolve_operands(
        "Return on equity in 2021?",
        units,
        _Provider(json.dumps(plan)),
        generation_kwargs={"model": "m"},
        prompt_version="v3",
        context_serializer=None,
    )

    assert calculation is None
    assert "OPERAND_SCALE_MISMATCH" in trace.plan_codes


# luna 1017, 1018, 1020 (V2): a lease note prints "Current" and "Long-term" as
# section lines above its rows, so "Operating lease liabilities(2) | 2021: $ 222"
# is the current one only by its section. A label may name the fact's section.

LEASES = (
    "Table:  | 2021 | 2020\n"
    "Liabilities\n"
    "Current\n"
    "Operating lease liabilities(2) | 2021: $ 222 | 2020: $ 231\n"
    "Finance lease liabilities(2) | 2021: 72 | 2020: 31\n"
    "Long-term\n"
    "Operating lease liabilities | 2021: 2,642 | 2020: 2,558\n"
    "Finance lease liabilities(3) | 2021: 980 | 2020: 657"
)


def test_a_fact_carries_its_section_line():
    facts = {f.value: f for f in unit_facts(LEASES).facts}

    assert facts[222.0].section == "Current"
    assert facts[980.0].section == "Long-term"


def test_a_label_may_name_the_facts_section():
    assert _bind(LEASES, "222", ["Operating lease liabilities(2)", "2021", "Current"]) == []
    assert _bind(LEASES, "980", ["Finance lease liabilities", "Long-term", "2021"]) == []
    # The section must be the fact's own.
    assert _bind(LEASES, "980", ["Finance lease liabilities", "Current", "2021"]) == [
        "OPERAND_LABEL_NOT_IN_UNIT"
    ]
    # A section alone names no row.
    assert _bind(LEASES, "222", ["Current", "2021"]) == ["OPERAND_LABEL_NOT_IN_UNIT"]
