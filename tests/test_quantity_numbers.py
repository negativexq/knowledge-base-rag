"""Numeric displays, absence, reviewed presentation and execution checkpoints."""

from decimal import Decimal, InvalidOperation

import pytest
from pydantic import ValidationError

from app.llm.adaptive import finalize_research
from app.llm.quantities import candidate, collect, execute
from app.llm.quantity_contracts import bind_collection, collection_contract
from app.llm.quantity_numbers import normalize_inputs, source_decimal
from app.llm.quantity_state import QuantityAssessment, QuantityDraft, QuantitySource
from app.llm.research_state import decimal_value
from tests.test_quantities import active_session, arithmetic


@pytest.mark.parametrize(
    "display,notation,expected",
    [
        ("(2,467)", "decimal_point", "-2467"),
        ("(725.50)", "decimal_point", "-725.50"),
        ("2.467,50", "decimal_comma", "2467.50"),
        ("−18", "decimal_point", "-18"),
        ("2\u202f467.50", "space_grouped", "2467.50"),
        ("0", "canonical", "0"),
        ("(725)", "canonical", "-725"),
        ("−18", "canonical", "-18"),
    ],
)
def test_source_notation_preserves_sign_without_guessing_locale(display, notation, expected):
    assert source_decimal(display, notation) == Decimal(expected)


@pytest.mark.parametrize(
    "display,notation",
    [
        ("(2,467)", "canonical"),
        ("2,46", "decimal_point"),
        ("2.46", "decimal_comma"),
        ("(-18)", "decimal_point"),
        ("Not found", "canonical"),
        ("NaN", "canonical"),
        ("Infinity", "canonical"),
        ("1e50", "canonical"),
        ("2 46", "space_grouped"),
        ("", "canonical"),
    ],
)
def test_malformed_or_unspecified_numeric_notation_is_rejected(display, notation):
    with pytest.raises(ValueError):
        source_decimal(display, notation)


@pytest.mark.parametrize("value", ["Not mentioned", "", "sNaN", "(25)"])
def test_decimal_conversion_never_leaks_decimal_exceptions(value):
    with pytest.raises(ValueError):
        decimal_value(value)


def read_draft(value="(2,467)", **changes):
    operand = dict(
        name="repurchases",
        label="Share repurchases",
        value=value,
        value_status="readable",
        number_format="decimal_point",
        source_scale="1000",
        unit="thousand shares",
        output_unit="shares",
        output_scale="1",
        sign_convention="magnitude",
        witness="Repurchases (2,467)",
    )
    operand.update(changes)
    return QuantityDraft(mode="read", complete=True, operands=[operand])


def test_source_display_canonical_number_and_presented_magnitude_are_separate():
    draft = read_draft()
    receipt = normalize_inputs(draft)[0]
    assert receipt.source_value == "(2,467)" and receipt.canonical_value == "-2467"
    assert receipt.output_value == "2467000" and receipt.output_unit == "shares"
    assert execute(draft) == (["2467000"], "")
    assert draft.operands[0].value == "(2,467)"
    assert execute(read_draft(sign_convention="signed"))[0] == ["-2467000"]


def test_scaling_is_checked_and_not_silently_reinterpreted():
    receipt = normalize_inputs(read_draft(source_scale="1"))[0]
    assert receipt.value_status == "invalid" and "NUMERIC_SOURCE_SCALE_MISMATCH" in receipt.errors
    with pytest.raises(ValueError, match="UNRESOLVED"):
        execute(read_draft(output_unit="million shares", output_scale="1"))


def test_zero_is_a_value_and_absence_is_a_distinct_typed_state():
    assert execute(read_draft(value="0"))[0] == ["0"]
    absent = read_draft(value=None, value_status="not_found")
    assert normalize_inputs(absent)[0].canonical_value is None
    assert execute(absent) == ([], "")
    for state in ["unreadable", "ambiguous"]:
        with pytest.raises(ValueError, match="UNRESOLVED"):
            execute(read_draft(value=None, value_status=state))


def test_native_numeric_schema_rejects_explanations_and_incoherent_statuses():
    schema = collection_contract("read", [], ["E1.S1"])
    operand = dict(
        name="n",
        label="Value",
        value="0",
        unit="items",
        output_unit="items",
        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
    )
    for changes in [dict(value="Not stated"), dict(value=None), dict(value_status="not_found")]:
        with pytest.raises(ValidationError):
            schema.model_validate(dict(mode="read", complete=True, operands=[operand | changes]))
    valid = operand | dict(value=None, value_status="not_found")
    active, _ = active_session()
    result = bind_collection(
        schema.model_validate(dict(mode="read", complete=True, operands=[valid])),
        [],
        active.units(),
    )
    assert normalize_inputs(result)[0].value_status == "not_found"


@pytest.mark.asyncio
async def test_checked_absence_is_persisted_and_finalizes_without_an_answer_model():
    active, need = active_session("Legend: green, white and amber.")
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, operation_kind="read", support_ids=["E1.S1"])
        if role == "quantity_collector":
            return output_type.model_validate(
                dict(
                    mode="read",
                    complete=True,
                    operands=[
                        dict(
                            name="requested",
                            label="Requested legend entry",
                            value=None,
                            value_status="not_found",
                            unit="",
                            output_unit="",
                            source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                        )
                    ],
                )
            )
        assert data["numeric_inputs"][0]["value_status"] == "not_found"
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    answer = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert answer.abstain and record.absence_confirmed and record.has_result
    assert record.numeric_inputs[0].source_value is None
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert restored.quantities[record.id].absence_confirmed
    assert candidate(record).abstain

    async def verify(answer):
        assert answer.abstain
        return answer, None

    active.verify = verify
    active.state.research_stop = "REQUEST_LIMIT"
    final, _ = await finalize_research(active)
    assert final.abstain and len(calls) == 3


@pytest.mark.asyncio
async def test_returned_review_survives_a_decimal_execution_failure(monkeypatch):
    active, need = active_session()

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return arithmetic()
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    def fail_execution(draft):
        record = next(iter(active.state.quantities.values()))
        assert record.assessments and record.check.accepted
        raise InvalidOperation("Injected Decimal failure")

    active.call = call
    monkeypatch.setattr("app.llm.quantities.execute", fail_execution)
    assert await collect(active, need, repairs_left=0) is None
    record = next(iter(active.state.quantities.values()))
    assert record.check.accepted and record.assessments
    assert record.execution_status == "failed"
    assert "Injected Decimal failure" in record.diagnostic_errors


@pytest.mark.parametrize(
    "unit", ["shares (000s)", "shares (000’s)", "shares (000's)", "shares (000)"]
)
def test_explicit_thousand_unit_variants_preserve_scaling(unit):
    receipt = normalize_inputs(read_draft(unit=unit))[0]
    assert receipt.value_status == "readable"
    assert receipt.output_value == "2467000"


def test_unchanged_explicit_unit_resolves_default_scales_without_conversion():
    receipt = normalize_inputs(read_draft(
        value="(725)", number_format="canonical", unit="USD millions",
        output_unit="USD millions", source_scale="1", output_scale="1",
    ))[0]
    assert receipt.value_status == "readable"
    assert receipt.source_scale == receipt.output_scale == "1000000"
    assert receipt.canonical_value == "-725" and receipt.output_value == "725"
    # A contradictory nondefault declaration is still invalid.
    invalid = normalize_inputs(read_draft(
        unit="million shares", source_scale="1000",
        output_unit="million shares", output_scale="1000",
    ))[0]
    assert invalid.value_status == "invalid"
