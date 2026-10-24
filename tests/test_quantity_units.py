"""Source scales transform arithmetic, never its source displays or ratio meaning."""

import pytest

from app.llm.quantities import collect, execute
from app.llm.quantity_numbers import normalize_inputs
from app.llm.quantity_state import QuantityAssessment, QuantityDraft, QuantitySource
from app.llm.quantity_units import arithmetic_conversion
from app.llm.research_state import ResearchState
from tests.test_quantities import active_session


def scaled(
    expression="b - a",
    result_unit="rupees",
    values=("3", "7"),
    scales=("100000", "100000"),
    units=("rupees", "rupees"),
):
    return QuantityDraft(
        mode="arithmetic",
        complete=True,
        expression=expression,
        result_unit=result_unit,
        decimals=3,
        operands=[
            dict(
                name=name,
                label=label,
                value=value,
                source_scale=scale,
                unit=unit,
                witness=f"{label} {value}",
                number_format="canonical",
                value_status="readable",
            )
            for name, label, value, scale, unit in zip(
                ["a", "b"], ["North", "South"], values, scales, units, strict=True
            )
        ],
    )


def test_source_displays_are_immutable_and_unit_factors_are_explicit_in_execution():
    draft = scaled()
    before = draft.model_dump_json()
    numbers = normalize_inputs(draft)
    assert [n.canonical_value for n in numbers] == ["3", "7"]
    assert [n.output_value for n in numbers] == ["300000", "700000"]
    assert all(n.output_scale == "1" and n.output_unit == "rupee" for n in numbers)
    values, expression = execute(draft)
    assert values == ["400000.000"] and expression.count("100000") == 2
    assert draft.model_dump_json() == before
    plan = arithmetic_conversion(draft, numbers)
    assert plan.source_formula == "b - a" and plan.source_factors == {"a": "100000", "b": "100000"}


@pytest.mark.parametrize(
    "expression,result_unit,values,scales,units,expected",
    [
        ("a + b", "USD", ("2.5", "1.1"), ("1000000", "1000000"), ("USD", "USD"), "3600000.000"),
        (
            "a + b",
            "million USD",
            ("2.5", "1.1"),
            ("1000000", "1000000"),
            ("million USD", "million USD"),
            "3.600",
        ),
        ("a / b", "", ("2", "500"), ("1000000", "1000"), ("USD", "USD"), "4.000"),
        ("a / b * 100", "%", ("2", "500"), ("1000000", "1000"), ("USD", "USD"), "400.000"),
        (
            "a / b",
            "",
            ("29441", "41190"),
            ("1000000", "1000000"),
            ("million USD", "million USD"),
            "0.715",
        ),
        (
            "b - a",
            "rupees",
            ("(2)", "7"),
            ("100000", "100000"),
            ("lakh rupees", "lakh rupees"),
            "900000.000",
        ),
        (
            "(a + b) / 2",
            "rupees",
            ("3", "7"),
            ("100000", "100000"),
            ("rupees", "rupees"),
            "500000.000",
        ),
        ("b - a", "", ("3", "7"), ("100000", "100000"), ("lakh rupees", "lakh rupees"), "4.000"),
        (
            "a + b",
            "million USD",
            ("1.234567", "2.345678"),
            ("1000", "1000"),
            ("thousand USD", "thousand USD"),
            "0.004",
        ),
    ],
)
def test_addition_ratios_output_scales_sign_and_rounding(
    expression, result_unit, values, scales, units, expected
):
    assert execute(scaled(expression, result_unit, values, scales, units))[0] == [expected]


@pytest.mark.parametrize(
    "draft",
    [
        scaled(units=("USD", "EUR"), result_unit="USD"),
        scaled(result_unit="EUR", units=("USD", "USD")),
        scaled(scales=("100000", "100000"), units=("million rupees", "rupees")),
        scaled(expression="a * b"),
        scaled(expression="a + missing"),
        scaled(expression="a"),
        scaled(result_unit="", scales=("1000", "1000000")),
    ],
)
def test_incompatible_or_ambiguous_units_do_not_execute(draft):
    numbers = normalize_inputs(draft)
    assert any(n.errors for n in numbers)
    with pytest.raises(ValueError):
        execute(draft)


@pytest.mark.asyncio
async def test_conversion_receipt_reaches_independent_review_and_existing_literal_verifier():
    active, need = active_session("Amounts in lacs of rupees\nNorth 3\nSouth 7")
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return scaled()
        assert data["arithmetic_conversion"]["source_factors"] == {"a": "100000", "b": "100000"}
        assert [n["output_value"] for n in data["numeric_inputs"]] == ["300000", "700000"]
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need, repairs_left=0)
    assert result is not None and result.answer_parts[0].text == "400000.000 rupees"
    assert not active.deps.validation(result).failure_codes
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    record = next(iter(active.state.quantities.values()))
    assert record.arithmetic_conversion.expression == record.expression
    restored = ResearchState.model_validate_json(active.state.model_dump_json())
    assert restored.quantities[record.id].arithmetic_conversion == record.arithmetic_conversion
    from app.llm.quantity_scope import semantic_scope_projection
    from app.llm.scope_validation import scope_payload

    payload = scope_payload(
        active.state.task.question, result.raw_answer(), active.deps.ledger.units
    )
    assert semantic_scope_projection(payload, [record])[1] == [record.id]
    changed = record.model_copy(update={"arithmetic_conversion": None})
    assert semantic_scope_projection(payload, [changed]) == (payload, [])


@pytest.mark.asyncio
async def test_review_can_reject_source_scale_even_when_math_is_deterministic():
    active, need = active_session("Amounts in thousands of rupees\nNorth 3\nSouth 7")

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return scaled()
        return QuantityAssessment(
            inputs="mismatch",
            coverage="complete",
            operation="supported",
            issues=[
                dict(
                    kind="wrong_binding",
                    target="operand",
                    index=0,
                    description="Source states thousands, not lakh",
                    source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                )
            ],
        )

    active.call = call
    assert await collect(active, need, repairs_left=0) is None
    record = next(iter(active.state.quantities.values()))
    assert not record.check.accepted and not record.values


@pytest.mark.parametrize(
    "expression,scales,units,result_unit,expected",
    [
        ("abs(a - b)", ("1", "1"), ("%", "%"), "percentage points", "4.000"),
        ("abs(a - b)", ("100000", "100000"), ("rupees", "rupees"), "rupees", "400000.000"),
        ("min(a,b)", ("1", "1"), ("USD", "USD"), "USD", "3.000"),
        ("max(a,b)", ("1000", "1000"), ("USD", "USD"), "USD", "7000.000"),
        ("mean(a,b)", ("1000", "1000"), ("USD", "USD"), "USD", "5000.000"),
        ("abs(mean(a,b) - max(a,b))", ("1", "1"), ("USD", "USD"), "USD", "2.000"),
    ],
)
def test_allowed_functions_use_source_inputs_with_units(
    expression, scales, units, result_unit, expected
):
    assert execute(scaled(expression, result_unit, scales=scales, units=units))[0] == [expected]


@pytest.mark.parametrize(
    "expression",
    [
        "abs(a,b)",
        "mean()",
        "min(a,key=b)",
        "max(*a)",
        "__import__(a)",
        "a.real",
        "pow(a,b)",
        "sum(a,b)",
        "abs(a / (b-b))",
        "abs(a + missing)",
    ],
)
def test_function_arguments_code_execution_and_division_errors_do_not_execute(expression):
    with pytest.raises((ValueError, ArithmeticError)):
        execute(scaled(expression))


def test_function_operands_are_all_checked_even_if_only_one_is_selected():
    from app.llm.calculation import Calculation, verify_calculation

    assert not verify_calculation(Calculation("min(3,7)", "3"), ["North 3 South 7"], "3")
    assert verify_calculation(Calculation("min(3,999)", "3"), ["North 3"], "3") == [
        "CALCULATION_OPERAND_UNSUPPORTED"
    ]
    assert not verify_calculation(Calculation("mean(3,7)", "5"), ["North 3 South 7"], "5")


def test_exact_decimal_literals_and_final_rounding_are_preserved():
    from app.llm.calculation import evaluate_decimal_expression, evaluate_decimal_value

    assert (
        str(evaluate_decimal_value("0.123456789012345678901 + 0.000000000000000000001"))
        == "0.123456789012345678902"
    )
    assert (
        evaluate_decimal_expression("mean(0.123456789012345678901,0.123456789012345678903)", 10)
        == "0.1234567890"
    )


def test_named_fact_calculator_supports_absolute_difference():
    from tests.test_research_state import prepared

    state, plan = prepared(expression="abs(a-b)")
    result = state.calculate(plan)
    assert result.value == "0.80"
    assert result.expanded_expression.startswith("abs(")


def test_unusable_notation_suggestion_preserves_valid_display_and_its_scale():
    from app.llm.quantity_numbers import apply_notation_corrections

    draft = scaled(
        values=("15,803", "1,874"),
        scales=("1000000", "1000000"),
        units=("USD", "USD"),
        result_unit="million USD",
    )
    draft = draft.model_copy(
        update={
            "operands": [
                o.model_copy(update={"number_format": "decimal_point"}) for o in draft.operands
            ]
        }
    )
    review = QuantityAssessment(
        inputs="unknown",
        coverage="complete",
        operation="supported",
        notation_corrections=[dict(index=0, number_format="canonical")],
    )
    corrected = apply_notation_corrections(draft, review)
    assert corrected == draft
    assert execute(corrected)[0] == ["-13929.000"]
    assert review.inputs == "unknown"  # Numeric validity does not approve source binding.


@pytest.mark.asyncio
async def test_a_checked_image_scale_supports_its_factor_without_a_printed_witness(tmp_path):
    # MMLongBench 380: both balance-sheet amounts were read from the page image
    # in lacs and checked, but the factor 100000 had no literal witness and the
    # accepted difference failed as CALCULATION_OPERAND_UNSUPPORTED.
    import hashlib

    import fitz

    from app.llm.visual_answer import PdfPages

    path = tmp_path / "report.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Rupees in lacs\nNorth 3\nSouth 7")
        pdf.save(path)
    active, need = active_session(
        "Report page", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    active.deps.ledger.blocks[0].payload.update(
        source_id="report_pdf", document_version=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    active.deps.ledger.source_ids = frozenset({"report_pdf"})

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                support_ids=["E1.S1"],
                pages=[1],
                modality="image",
                operation_kind="arithmetic",
            )
        if role == "quantity_collector":
            return output_type.model_validate(
                dict(
                    mode="arithmetic",
                    complete=True,
                    expression="b - a",
                    decimals=0,
                    result_unit="rupees",
                    interpretation="South minus North in rupees",
                    operands=[
                        dict(
                            name=name,
                            label=label,
                            value=value,
                            source_scale="100000",
                            unit="rupees in lacs",
                            witness=f"{label} {value}",
                            number_format="canonical",
                            value_status="readable",
                            image_ids=["image_1"],
                        )
                        for name, label, value in [("a", "North", "3"), ("b", "South", "7")]
                    ],
                )
            )
        return QuantityAssessment(
            inputs="supported",
            coverage="complete",
            operation="supported",
            entity_identity="supported",
            supported_operand_indexes=[0, 1],
        )

    active.call = call
    result = await collect(active, need, repairs_left=0)
    record = next(iter(active.state.quantities.values()))
    assert record.diagnostic_errors == []
    assert result is not None and result.answer_parts[0].text.startswith("400000")
    assert record.arithmetic_conversion is not None
