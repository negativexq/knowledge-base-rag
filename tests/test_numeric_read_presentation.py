"""Numeric vectors keep source identities and apply display operations locally."""

import pytest
from pydantic import ValidationError

from app.llm.quantities import candidate, collect, execute
from app.llm.quantity_numbers import normalize_inputs, read_order
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityCheck,
    QuantityDraft,
    QuantityRecord,
    QuantitySource,
)
from app.llm.research_state import NumericPresentation
from tests.test_quantities import active_session


def vector(values, **changes):
    return QuantityDraft(
        mode="read", complete=True,
        operands=[dict(
            name=f"n{i}", label=f"Category {99-i}, model 80M", value=value,
            unit="score", output_unit="score", witness=f"Score {value}",
        ) for i, value in enumerate(values)],
        **changes,
    )


def rendered(draft):
    values, expression = execute(draft)
    return candidate(QuantityRecord(
        id="q", need_id="n", source_id="doc", document_version="v1",
        pages=[1], modality="text", support_ids=["E1.S1"], draft=draft,
        values=values, expression=expression,
        check=QuantityCheck(accepted=True, complete=True, reason="supported"),
    )).answer_parts[0].text


def test_numeric_order_ignores_digits_in_labels_and_rounds_only_display():
    draft = vector(["8.26", "10.14", "8.27"], output_order="descending", output_decimals=1)
    original = draft.model_dump()
    assert execute(draft)[0] == ["10.14", "8.27", "8.26"]
    assert rendered(draft) == '["10.1", "8.3", "8.3"]'
    assert draft.model_dump() == original


@pytest.mark.parametrize("order", ["ascending", "descending"])
def test_equal_values_and_equal_rounded_values_keep_every_source_identity(order):
    draft = vector(["2.24", "2.24", "2.23"], output_order=order, output_decimals=1)
    expected = [2, 0, 1] if order == "ascending" else [0, 1, 2]
    assert read_order(draft, normalize_inputs(draft)) == expected
    assert rendered(draft) == '["2.2", "2.2", "2.2"]'


def test_explicit_decimal_comma_is_sorted_numerically():
    draft = vector(["9,25", "12,50"], output_order="descending")
    draft = draft.model_copy(update={"operands": [
        operand.model_copy(update={"number_format": "decimal_comma"})
        for operand in draft.operands
    ]})
    assert execute(draft)[0] == ["12.50", "9.25"]


def test_numeric_order_refuses_incompatible_units_and_unknown_values():
    draft = vector(["2", "3"], output_order="ascending")
    draft.operands[1] = draft.operands[1].model_copy(update={"unit": "USD", "output_unit": "USD"})
    with pytest.raises(ValueError, match="INCOMPATIBLE_UNITS"):
        execute(draft)
    draft = vector(["2", "3"], output_order="ascending")
    draft.operands[1] = draft.operands[1].model_copy(
        update={"value": None, "value_status": "unreadable"}
    )
    with pytest.raises(ValueError, match="UNRESOLVED"):
        execute(draft)


def test_default_scalar_and_source_order_read_still_retain_labels_and_units():
    assert rendered(vector(["3.25"])) == "3.25 score"
    assert rendered(vector(["3.25", "1"])) == (
        "Category 99, model 80M: 3.25 score; Category 98, model 80M: 1 score"
    )


def test_text_list_still_sorts_text_and_cannot_claim_numeric_presentation():
    data = dict(mode="list", complete=True, list_order="ascending", items=[
        dict(text=text, witness=text, page=1, position=i+1)
        for i, text in enumerate(["Zulu 2", "Alpha 10"])
    ])
    assert execute(QuantityDraft(**data))[0] == ["Alpha 10", "Zulu 2"]
    with pytest.raises(ValidationError, match="Numeric output ordering"):
        QuantityDraft(**data, output_order="descending")


@pytest.mark.asyncio
async def test_question_plan_owns_presentation_without_another_collection_call():
    active, need_id = active_session("A 8.26\nB 10.14")
    need = active.state.evidence_needs[need_id]
    active.state.evidence_needs[need_id] = need.model_copy(update={
        "spec": need.spec.model_copy(update={"presentation": NumericPresentation(
            decimals=1, order="descending", question_quote="total",
        )}),
    })
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, operation_kind="read", support_ids=["E1.S1"])
        if role == "quantity_collector":
            return output_type.model_validate(dict(mode="read", complete=True, operands=[
                dict(name=name.lower(), label=name, value=value, unit="score", output_unit="score",
                     source_ranges=[dict(support_id="E1.S1", start_line=line, end_line=line)])
                for name, value, line in [("A", "8.26", 1), ("B", "10.14", 2)]
            ]))
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    answer = await collect(active, need_id)
    assert answer.answer_parts[0].text == '["10.1", "8.3"]'
    record = next(iter(active.state.quantities.values()))
    assert record.draft.operands[0].value == "8.26"
    assert record.draft.output_order == "descending" and record.draft.output_decimals == 1
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
    validation = active.deps.validation(answer)
    assert not validation.failure_codes and not validation.application_abstain
    # The receipt certifies only the app-produced rounding, not arbitrary nearby digits.
    forged = answer.model_copy(update={"answer_parts": [
        answer.answer_parts[0].model_copy(update={"text": '["10.9", "8.3"]'})
    ]})
    assert active.deps.validation(forged).failure_codes
