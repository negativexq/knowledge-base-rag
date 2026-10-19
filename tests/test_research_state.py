"""Source-bound arithmetic and strict, application-owned research records."""

import pytest
from pydantic import ValidationError

from app.llm.research_state import (
    CalculationInput,
    ComputationPlan,
    DataExtraction,
    EvidenceRef,
    ObservedValue,
    ResearchState,
    TaskSpec,
    decimal_value,
    text_observation_supported,
)


def observation(category="A", value="120", unit="cm", **kwargs):
    return ObservedValue(
        category=category,
        value=value,
        unit=unit,
        witness=f"{category} {value} {unit}",
        status="readable",
        **kwargs,
    )


def prepared(expression="a+b", output_unit="m", values=None):
    state = ResearchState(task=TaskSpec(question="Total length?"))
    facts = state.add_facts(
        DataExtraction(values=values or [observation(), observation("B", "2", "m")]),
        EvidenceRef(support_id="E1.S1", source_id="manual", document_version="v1"),
        "text_witness",
    )
    plan = ComputationPlan(
        expression=expression,
        inputs=[CalculationInput(name=chr(97 + i), fact_id=f.id) for i, f in enumerate(facts)],
        output_unit=output_unit,
        decimals=2,
    )
    return state, plan


def test_state_is_typed_and_observations_are_immutable():
    state, plan = prepared()
    assert ResearchState.model_validate_json(state.model_dump_json()) == state
    with pytest.raises(ValidationError):
        state.finalization = "whatever"
    with pytest.raises(ValidationError):
        state.facts[plan.inputs[0].fact_id].observation.value = "999"
    with pytest.raises(ValidationError):
        TaskSpec(question="x", model_summary="invented")


@pytest.mark.parametrize("status", ["unreadable", "ambiguous"])
def test_uncertain_values_cannot_carry_a_guessed_number(status):
    with pytest.raises(ValidationError):
        ObservedValue(category="A", value="5", status=status)
    state, _ = prepared()
    before = state.revision
    assert not state.add_facts(
        DataExtraction(values=[ObservedValue(category="A", status=status)]),
        EvidenceRef(support_id="E1.S1", source_id="manual"),
        "image_checked",
    )
    assert state.revision == before


def test_prepared_arithmetic_converts_units_without_a_model_and_deduplicates():
    state, plan = prepared()
    result = state.calculate(plan)
    assert result.value == "3.20"
    assert result.support_ids == ["E1.S1"]
    revision = state.revision
    assert state.calculate(plan) is result
    assert state.revision == revision


@pytest.mark.parametrize(
    "expression,result", [("mean(a,b)", "1.60"), ("min(a,b)", "1.20"), ("max(a,b)", "2.00")]
)
def test_aggregates_derive_their_own_constants(expression, result):
    state, plan = prepared(expression)
    assert state.calculate(plan).value == result


def test_percentages_are_scaled_and_currency_is_not_exchanged():
    state, plan = prepared("a/b", "", [observation("A", "20", "%"), observation("B", "40", "%")])
    assert state.calculate(plan).value == "0.50"
    state, plan = prepared(values=[observation("A", "5", "USD"), observation("B", "6", "EUR")])
    with pytest.raises(ValueError, match="dimensions"):
        state.calculate(plan)


@pytest.mark.parametrize(
    "expression",
    ["a+100", "__import__('os')", "a.__class__", "a**b", "sum(a,b)", "mean()", "mean(a,2)"],
)
def test_unsupported_or_unsourced_computations_are_rejected(expression):
    state, plan = prepared(expression)
    with pytest.raises(ValueError):
        state.calculate(plan)
    assert not state.computations


@pytest.mark.parametrize(
    "value,witness,valid",
    [
        ("120", "A 120 cm", True),
        ("120.0", "A 120 cm", True),
        ("999", "A 120 cm", False),
        ("120", "A 1120 cm", False),
        ("120", "A -120 cm", False),
        ("120", "A 120,000 cm", False),
        ("1.2", "A 1,2 cm", False),
        ("120", "B 120 cm", False),
    ],
)
def test_text_witness_checks_values_labels_signs_and_locale(value, witness, valid):
    obs = observation(value=value).model_copy(update={"witness": witness})
    assert text_observation_supported(obs, witness) is valid


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e100", "1,000"])
def test_noncanonical_or_unbounded_numbers_are_rejected(value):
    with pytest.raises(ValueError):
        decimal_value(value)


@pytest.mark.parametrize(
    "data,status",
    [
        ({"category": "A", "value": "12", "witness": "A 12"}, "readable"),
        ({"category": "A", "value": None}, "ambiguous"),
        ({"category": "A", "value": None, "status": "unreadable"}, "unreadable"),
    ],
)
def test_omitted_observation_status_is_normalized_without_guessing_values(data, status):
    from app.llm.research_state import ObservedValue

    observation = ObservedValue.model_validate(data)
    assert observation.status == status and observation.value == data["value"]


@pytest.mark.parametrize(
    "data",
    [
        {"category": "A", "value": "12"},
        {"category": "A", "value": "12", "witness": "A 12", "status": "ambiguous"},
        {"category": "A", "value": "12", "witness": "A 12", "status": "unreadable"},
    ],
)
def test_observation_status_normalization_never_overrides_uncertainty(data):
    from app.llm.research_state import ObservedValue

    with pytest.raises(ValueError):
        ObservedValue.model_validate(data)


@pytest.mark.parametrize("scale", ["percent", "million", "uninterpreted printed scale"])
def test_display_rounding_preserves_printed_magnitude_without_interpreting_scale(scale):
    state, _ = prepared()
    fact = next(iter(state.facts.values()))
    obs = fact.observation.model_copy(update={"value": "12.35", "unit": "F1", "scale": scale})
    state.facts[fact.id] = fact.model_copy(update={"observation": obs})
    from app.llm.research_state import CalculationInput, ComputationPlan

    plan = ComputationPlan(
        mode="display",
        expression="a",
        output_unit="F1",
        decimals=1,
        inputs=[CalculationInput(name="a", fact_id=fact.id)],
    )
    assert state.calculate(plan).value == "12.4"
    with pytest.raises(ValueError, match="cannot change units"):
        state.calculate(plan.model_copy(update={"output_unit": "%"}))
    with pytest.raises(ValueError, match="one sourced operand"):
        state.calculate(plan.model_copy(update={"expression": "a+a"}))
