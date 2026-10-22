"""Aggregate arithmetic and source limitations retain distinct release contracts."""

import json

import pytest
from pydantic import ValidationError
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.agentic import AgentAnswer, AgentAnswerPart
from app.llm.quantity_contracts import bind_collection, collection_contract
from app.llm.quantity_scope import semantic_scope_projection
from app.llm.quantity_state import PopulationQuantitySelection
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint, ResearchState, TaskSpec
from app.llm.scope_validation import scope_payload
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
from tests.test_adaptive import deps, payload, reply, session
from tests.test_quantities import active_session


@pytest.mark.parametrize("operation", ["count", "calculate", "lookup"])
@pytest.mark.asyncio
async def test_aggregate_population_dispatch_uses_arithmetic_not_person_inventory(operation):
    dependencies = deps(
        "Survey: 2,000 adults. Segment A accounts for 12.5% of all surveyed adults.",
        question="How many surveyed adults are in Segment A?", derived_answers=True,
    )
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="ready")
    state.add_need(EvidenceNeedSpec(
        description="Estimate the aggregate subgroup headcount from the survey",
        quantity_basis="aggregate_population", operation=operation,
        constraints=[NeedConstraint(dimension="population", value="Segment A",
                                    question_quote="Segment A")],
    ))
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "missing" not in props, "No speculative answer for an aggregate source operation"
        if "available" in props:
            roles.append("select")
            assert set(props["operation_kind"]["enum"]) == {"read", "arithmetic"}
            return reply(info, dict(available=True, operation_kind="arithmetic",
                                   support_ids=["E1.S1"], context_support_ids=[]))
        if "operands" in props:
            roles.append("collect")
            return reply(info, dict(
                mode="arithmetic", complete=True, result_kind="approximate",
                expression="n * share / 100", decimals=0, result_unit="adults",
                interpretation="Sample-equivalent estimate using the published survey share.",
                operands=[dict(
                    name=name, label=label, value=value, unit=unit, population=population,
                    denominator_population=base, period="survey",
                    source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                ) for name, label, value, unit, population, base in [
                    ("n", "Survey adults", "2000", "adults", "all surveyed adults", ""),
                    ("share", "Segment A share", "12.5", "%", "Segment A",
                     "all surveyed adults"),
                ]],
            ))
        roles.append("check")
        assert payload(messages)["draft"]["result_kind"] == "approximate"
        return reply(info, dict(inputs="supported", coverage="complete", operation="supported",
                                entity_identity="supported"))

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True, evidence_needs_enabled=True
    )
    answer = json.loads(result.raw)["answer_parts"][0]
    assert answer["text"].startswith("Approximately 250 adults")
    assert answer["calculation"]["result"] == "250"
    assert roles == ["select", "collect", "check"]
    record = next(iter(state.quantities.values()))
    assert record.draft.operands[1].denominator_population == "all surveyed adults"
    projection, ids = semantic_scope_projection(
        scope_payload(dependencies.question, result.raw, dependencies.ledger.units), [record]
    )
    assert ids == [record.id]
    assert projection["verified_operations"][0]["result_kind"] == "approximate"
    assert projection["claims"][0]["claim"]["text"].startswith("Approximately 250")


def test_population_selection_cannot_request_person_inventory():
    with pytest.raises(ValidationError):
        PopulationQuantitySelection(operation_kind="count", context_support_ids=[])


def test_approximation_and_population_provenance_survive_native_arithmetic_contract():
    schema = collection_contract("arithmetic", [], ["E1.S1"])
    wire = schema.model_validate(dict(
        mode="arithmetic", result_kind="approximate", complete=True,
        expression="n * rate / 100", decimals=0, result_unit="people", interpretation="Estimate",
        operands=[dict(name="n", label="N", value="200", unit="people", population="A+B",
                       source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)]),
                  dict(name="rate", label="Rate", value="20", unit="%", population="A",
                       denominator_population="A",
                       source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)])],
    ))
    active, _ = active_session()
    draft = bind_collection(wire, [], active.units())
    assert draft.result_kind == "approximate"
    assert draft.operands[0].population == "A+B"
    assert draft.operands[1].denominator_population == "A"
    # Approximate status describes the result; it cannot certify the A versus
    # A+B relationship. The same source/checking contract still sees that defect.
    assert draft.operands[0].population != draft.operands[1].denominator_population


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [True, False])
async def test_numeric_source_limitation_requires_independent_positive_scope(supported):
    text = "Group A reports 20%. The only sample base provided is for Group A and B combined."
    active = session(deps(text, question="How many people in Group A gave this response?",
                          scope_validation_enabled=True))
    active.compact_context = True
    answer = AgentAnswer(abstain=False, answer_parts=[AgentAnswerPart(
        answer_kind="source_limitation", support_ids=["E1.S1"],
        text="Group A reports 20%, but the supplied table gives only the combined A and B "
             "sample base, so it does not establish the number of Group A respondents.",
    )])
    parsed = parse_support_unit_answer(answer.raw_answer())
    strict = validate_support_unit_answer(parsed, active.deps.ledger.units,
                                          question=active.deps.question)
    assert "SOURCE_LIMITATION_REQUIRES_SCOPE_VALIDATION" in strict.failure_codes
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        assert data["claims"][0]["claim"]["answer_kind"] == "source_limitation"
        return output_type.model_validate(dict(checks=[dict(
            claim_index=0, verdict="supported" if supported else "mismatch",
            reason="NONE" if supported else "POPULATION_MISMATCH",
            witnesses=[dict(support_id="E1.S1", start_line=1, end_line=1)],
        )]))

    active.call = call
    if supported:
        result, receipt = await active.verify(answer)
        assert receipt.accepts(active.deps.question, result.raw_answer(), active.deps.ledger.units)
        changed = result.model_copy(deep=True)
        changed.answer_parts[0].answer_kind = "answer"
        assert not receipt.accepts(
            active.deps.question, changed.raw_answer(), active.deps.ledger.units
        )
    else:
        with pytest.raises(ValueError, match="POPULATION_MISMATCH"):
            await active.verify(answer)
    assert calls == ["scope_validator"]


@pytest.mark.asyncio
async def test_normal_percentage_still_cannot_substitute_for_a_requested_headcount():
    active = session(deps("Group A: 20%", question="How many people in Group A?",
                          scope_validation_enabled=True))
    answer = AgentAnswer(abstain=False, answer_parts=[AgentAnswerPart(
        text="20%", support_ids=["E1.S1"],
    )])
    assert "ANSWER_TYPE_MISMATCH" in active.deps.validation(answer).failure_codes


def test_partial_inputs_keep_the_grounded_remaining_binding_for_next_stage():
    from tests.test_quantity_repair_handoff import parent_record

    active, _ = active_session()
    record = parent_record().model_copy(update={"supported_operand_indexes": [0]})
    active.state.quantities[record.id] = record
    partial = active.context(finalizing=True)["checked_partial_inputs"][0]
    assert partial["inputs"][0]["name"] == "a"
    assert partial["unresolved_bindings"][0]["index"] == 1
    assert partial["unresolved_bindings"][0]["description"] == (
        "Recheck second input against original source."
    )
    active.state.quantities[record.id] = record.model_copy(
        update={"diagnostic_errors": ["ISSUE_SOURCE_NOT_GROUNDED"]}
    )
    assert not active.context(finalizing=True)["checked_partial_inputs"][0]["unresolved_bindings"]


@pytest.mark.parametrize("kind,primary,verdict,accepted", [
    ("source_limitation", "supported", "mismatch", True),
    ("answer", "supported", "mismatch", False),
    ("source_limitation", "supported", "unknown", False),
    ("source_limitation", "insufficient", "mismatch", False),
])
def test_a_checked_source_contrast_is_not_a_positive_target_binding(
    kind, primary, verdict, accepted
):
    from app.llm.scope_requirements import validate_requirements
    from tests.test_inventory_scope import binding_payload, judgment

    data = binding_payload()
    data["claims"][0]["claim"]["answer_kind"] = kind
    check = judgment(verdict=verdict)
    check.checks[0].verdict = primary
    check.checks[0].reason = "NONE" if primary == "supported" else "SCOPE_NOT_ESTABLISHED"
    errors = validate_requirements(
        data, [dict(dimension="entity", question_quote="Unreported entity")], check, set()
    )
    assert (not errors) is accepted


def test_a_bounded_qualification_does_not_erase_an_executable_population_plan():
    from app.llm.quantities import execute
    from app.llm.quantity_state import QuantityDraft

    explanation = "This is an approximate sample equivalent under the published rate. " * 6
    schema = collection_contract("arithmetic", [], ["E1.S1"])
    wire = schema.model_validate(dict(
        mode="arithmetic", complete=True, result_kind="approximate", expression="n * rate / 100",
        decimals=0, result_unit="people", interpretation=explanation,
        operands=[dict(name="n", label="N", value="200", unit="people",
                       source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)]),
                  dict(name="rate", label="Share", value="25", unit="%",
                       source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)])],
    ))
    active, _ = active_session()
    draft = bind_collection(wire, [], active.units())
    assert draft.interpretation == explanation
    assert execute(draft)[0] == ["50"]
    with pytest.raises(ValidationError):
        QuantityDraft.model_validate(draft.model_dump() | {"interpretation": "x" * 801})


@pytest.mark.asyncio
async def test_unverified_final_limitation_is_safe_insufficiency_not_verified_absence():
    from app.llm.adaptive import finalize_research

    active = session(deps("A limited source view.", scope_validation_enabled=True))
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        return AgentAnswer(abstain=False, answer_parts=[AgentAnswerPart(
            text="The whole document has no such value.", support_ids=["E1.S1"],
            answer_kind="source_limitation",
        )])

    async def reject(*args, **kwargs):
        raise ValueError("SCOPE_NOT_ESTABLISHED")

    active.call = call
    active.verify = reject
    result, receipt = await finalize_research(active)
    assert result.abstain and receipt is None
    assessment = active.state.terminal_assessments[-1]
    assert assessment.outcome == "insufficient_evidence" and not assessment.disposition_id
    assert assessment.diagnostic_errors == ["SOURCE_LIMITATION_UNVERIFIED"]
    assert calls == ["finalizer"]


def test_partial_value_candidates_are_bounded_to_visible_same_snapshot_pages():
    from dataclasses import replace

    from app.llm.quantity_sources import partial_value_sources
    from tests.test_quantity_repair_handoff import parent_record

    active, _ = active_session(text="Survey sample heading.")
    heading = active.units()["E1.S1"]
    record = parent_record().model_copy(update={
        "source_id": heading.source_id, "document_version": heading.document_version,
        "pages": [1], "supported_operand_indexes": [1],
    })
    value = replace(heading, support_unit_id="value", text="Combined subgroup sample: 7.")
    units = {"E1.S1": heading, "value": value}
    units.update({name: replace(value, support_unit_id=name, **changes) for name, changes in [
        ("foreign", dict(source_id="another_source")),
        ("stale", dict(document_version="another_snapshot")),
        ("hidden", dict(model_visible=False)),
        ("unauthorized", dict(authorized=False)),
        ("outside", dict(page_number=9, page_end=9)),
    ]})
    assert partial_value_sources(record, units) == {1: ["value"]}
    assert not partial_value_sources(
        record.model_copy(update={"diagnostic_errors": ["BAD"]}), units
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", [None, "ungrounded", "answer_available", "diagnostic"])
async def test_material_intent_clarification_dispatches_without_recollecting_inputs(defect):
    from app.llm.quantities import collect
    from app.llm.quantity_state import QuantityAssessment
    from app.llm.research_dispositions import (
        DispositionJudgment,
        DispositionProposal,
        ReviewedDisposition,
    )
    from tests.test_quantities import fake_calls, text_arithmetic

    active, need = active_session()
    proposal = DispositionProposal(
        kind="needs_clarification", question_quote="total", requested="total",
        source_object="North and South table", scope="inspected_material",
        witnesses=[dict(support_id="E1.S1", quote="North 3" if defect != "ungrounded"
                        else "invented label", page=1)],
        clarification_question="Should the total include North and South, or just North?",
    )
    review = QuantityAssessment(
        inputs="supported", coverage="complete", operation="ambiguous",
        issues=[dict(kind="operation", target="operation", index=None,
                     description="The source has separate North and South categories.",
                     source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=2)],
                     question_start=9 if defect == "diagnostic" else 1, question_end=9
                     if defect == "diagnostic" else 1)],
        source_disposition=ReviewedDisposition(proposal=proposal, judgment=DispositionJudgment(
            question_binding="supported", object_identity="supported",
            material_answer_available=defect == "answer_available",
        )),
    )
    roles = fake_calls(active, draft=text_arithmetic(), check=review)
    # The real collector contract binds source ranges in application code.
    original = active.call

    async def call(role, output_type, instructions, data, **kwargs):
        result = await original(role, output_type, instructions, data, **kwargs)
        return output_type.model_validate(result) if isinstance(result, dict) else result

    active.call = call
    answer = await collect(active, need, repairs_left=0)
    if defect is None:
        assert answer.abstain
        assert answer.clarification.question == proposal.clarification_question
        assert active.current_disposition().verified
    else:
        assert answer is None
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    record = next(iter(active.state.quantities.values()))
    assert not record.values
    assert record.supported_operand_indexes == ([] if defect == "diagnostic" else [0, 1])


def test_rate_context_candidates_are_literal_same_snapshot_hints():
    from dataclasses import replace

    from app.llm.quantity_sources import rate_binding_sources
    from app.llm.quantity_state import QuantityDraft

    active, _ = active_session()
    anchor = active.units()["E1.S1"]
    draft = QuantityDraft(mode="arithmetic", complete=True, expression="r", decimals=0,
                          operands=[dict(name="r", label="Connected group", value="28",
                                         unit="%", population="connected group",
                                         denominator_population="all survey adults")])
    related = replace(anchor, support_unit_id="context",
                      text="In this survey, 28% of all adults are connected to the network.")
    units = {"context": related,
             "different_value": replace(related, text="29% of adults are connected."),
             "foreign": replace(related, source_id="other"),
             "stale": replace(related, document_version="old"),
             "hidden": replace(related, model_visible=False),
             "denied": replace(related, authorized=False),
             "large": replace(related, text=related.text + "x" * 1500)}
    assert list(rate_binding_sources(draft, anchor, units)[0]) == ["context"]
    assert not rate_binding_sources(draft, replace(anchor, document_version=None), units)
    assert not rate_binding_sources(draft.model_copy(update={"mode": "read"}), anchor, units)


@pytest.mark.asyncio
@pytest.mark.parametrize("compatible", [True, False])
async def test_rate_context_reaches_existing_checker_without_certifying_its_binding(compatible):
    from app.llm.quantities import collect
    from app.llm.quantity_state import QuantityAssessment, QuantitySource
    from tests.test_adaptive import block

    active, need = active_session("Survey base 2000 adults\nConnected group 28%")
    active.admit([block("Connected adults: 28% of survey adults use network access.",
                        id="definition", page_number=2)])
    context = next(k for k, u in active.units().items()
                   if u.parent_evidence_block_id == "definition")
    roles = []

    async def call(role, output_type, instructions, data, **kwargs):
        roles.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return output_type.model_validate(dict(
                mode="arithmetic", complete=True, expression="n * rate / 100", decimals=0,
                result_kind="approximate", result_unit="adults", interpretation="Sample estimate",
                operands=[dict(name="n", label="Survey adults", value="2000", unit="adults",
                               source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)]),
                          dict(name="rate", label="Connected adults", value="28", unit="%",
                               population="connected adults",
                               denominator_population="survey adults",
                               source_ranges=[dict(support_id="E1.S1", start_line=2, end_line=2)])],
            ))
        assert context in [c["support_id"] for c in data["context_sources"]]
        if compatible:
            return QuantityAssessment(
                inputs="supported", coverage="complete", operation="supported"
            )
        return QuantityAssessment(inputs="mismatch", coverage="complete", operation="supported",
            issues=[dict(kind="wrong_binding", target="operand", index=1,
                         description="A value match does not establish the intended population.",
                         source_ranges=[dict(support_id=context, start_line=1, end_line=1)])])

    active.call = call
    answer = await collect(active, need, repairs_left=0)
    record = next(iter(active.state.quantities.values()))
    assert context in record.context_support_ids
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    if compatible:
        assert answer.answer_parts[0].calculation.result == "560"
    else:
        assert answer is None and not record.values and not record.check.accepted
