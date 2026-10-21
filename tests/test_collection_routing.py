"""Typed dispatch and recovery preserve evidence without certifying failed drafts."""

import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.research_state import (
    EvidenceNeedSpec,
    NeedConstraint,
    NumericPresentation,
    ResearchState,
    TaskSpec,
)
from tests.test_adaptive import answer, block, deps, payload, reply
from tests.test_quantities import text_arithmetic


def numeric_sort_state(dependencies):
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="ready")
    state.add_need(EvidenceNeedSpec(
        description="Read the scores and present them in the requested numeric order",
        operation="sort",
        acquisition="text",
        constraints=[NeedConstraint(dimension="metric", value="scores", question_quote="scores")],
        presentation=NumericPresentation(
            decimals=1, order="descending", question_quote="descending order with one decimal place"
        ),
    ))
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["lookup", "compare", "sort"])
async def test_planned_numeric_presentation_dispatches_without_speculative_answer(operation):
    dependencies = deps(
        "Alpha 10.14\nBeta 8.26",
        question="List the scores in descending order with one decimal place.",
        derived_answers=True,
    )
    state = numeric_sort_state(dependencies)
    need = next(iter(state.evidence_needs.values()))
    state.evidence_needs[need.id] = need.model_copy(
        update={"spec": need.spec.model_copy(update={"operation": operation})}
    )
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "missing" not in props, "Executable numeric presentation needs no answer attempt"
        if "available" in props:
            roles.append("selector")
            assert payload(messages)["need"]["presentation"]["decimals"] == 1
            return reply(info, dict(
                available=True, operation_kind="read", support_ids=["E1.S1"], context_support_ids=[]
            ))
        if "operands" in props:
            roles.append("collector")
            return reply(info, dict(mode="read", complete=True, operands=[
                dict(name=name.lower(), label=name, value=value, unit="score", source_ranges=[
                    dict(support_id="E1.S1", start_line=line, end_line=line)
                ]) for name, value, line in [("Alpha", "10.14", 1), ("Beta", "8.26", 2)]
            ]))
        assert "inputs" in props
        roles.append("checker")
        return reply(info, dict(inputs="supported", coverage="complete", operation="supported"))

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert result.failure_code is None, state.needs
    assert roles == ["selector", "collector", "checker"]
    assert json.loads(result.raw)["answer_parts"][0]["text"] == '["10.1", "8.3"]'
    record = next(iter(state.quantities.values()))
    assert [o.value for o in record.draft.operands] == ["10.14", "8.26"]
    assert record.draft.output_order == "descending" and record.draft.output_decimals == 1


@pytest.mark.asyncio
async def test_direct_numeric_presentation_unavailable_source_keeps_research_and_finalization():
    dependencies = deps(
        "Partial source", derived_answers=True,
        question="List the scores in descending order with one decimal place.",
    )
    state = numeric_sort_state(dependencies)
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "missing" not in props
        if "available" in props:
            roles.append("selector")
            return reply(info, dict(available=False, support_ids=[], context_support_ids=[]))
        if "action" in props:
            roles.append("research")
            assert payload(messages)["collection_outcomes"][-1]["status"] == "not_found"
            return reply(info, dict(action="stop"))
        roles.append("finalizer")
        return reply(info, dict(abstain=True))

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert roles == ["selector", "research", "finalizer"]
    assert result.failure_code is None and json.loads(result.raw)["abstain"]
    assert not state.quantities


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    "text_sort", "lookup", "composite", "no_tools", "no_derived", "unready", "satisfied",
    "no_collection_requests",
])
async def test_direct_numeric_dispatch_does_not_displace_existing_fast_answers(monkeypatch, case):
    dependencies = deps(
        "Alpha 10.14\nBeta 8.26", derived_answers=case != "no_derived",
        question="List the scores in descending order with one decimal place.",
    )
    state = numeric_sort_state(dependencies)
    need = next(iter(state.evidence_needs.values()))
    changes = {}
    if case == "text_sort":
        changes["presentation"] = need.spec.presentation.model_copy(update={"decimals": None})
    if case == "lookup":
        changes["operation"] = "lookup"
        changes["presentation"] = need.spec.presentation.model_copy(update={"order": "source"})
    if changes:
        state.evidence_needs[need.id] = need.model_copy(
            update={"spec": need.spec.model_copy(update=changes)}
        )
    if case == "composite":
        state.add_need(EvidenceNeedSpec(
            description="Identify the scoring metric", operation="lookup",
            constraints=[NeedConstraint(
                dimension="metric", value="scores", question_quote="scores"
            )],
        ))
    if case == "unready":
        state.need_planning = "failed"
    if case == "satisfied":
        state.evidence_needs[need.id] = need.model_copy(update={"status": "satisfied"})

    async def forbidden(*args, **kwargs):
        pytest.fail("Existing direct-answer capability must be preserved")

    monkeypatch.setattr("app.llm.adaptive.collect_quantities", forbidden)
    calls = []

    def model(messages, info):
        assert "missing" in info.output_tools[0].parameters_json_schema["properties"]
        calls.append("fast")
        return reply(info, dict(answer=dict(answer_parts=[dict(
            text="Alpha 10.14; Beta 8.26", support_ids=["E1.S1"]
        )])))

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True,
        max_tool_calls=0 if case == "no_tools" else 8,
        max_requests=2 if case == "no_collection_requests" else 6,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"]
    assert calls == ["fast"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "planned,hint",
    [(False, "unknown"), (False, "text"), (True, "unknown"), (True, "text"), (True, "calculate")],
)
async def test_prose_research_does_not_enter_numeric_collection(monkeypatch, hint, planned):
    searches = []

    async def retrieve(query):
        searches.append(query)
        return [block("The backup uses SSH.", "backup")]

    dependencies = deps(
        derived_answers=True, retrieve=retrieve, question="What does the backup use?"
    )
    state = ResearchState(task=TaskSpec(question=dependencies.question))
    if planned:
        state.add_need(
            EvidenceNeedSpec(
                description="Backup protocol",
                operation="lookup",
                constraints=[
                    NeedConstraint(dimension="entity", value="backup", question_quote="backup")
                ],
            )
        )
        state.need_planning = "ready"

    async def forbidden(*args, **kwargs):
        pytest.fail("Prose lookup must not invoke numeric source selection or extraction")

    monkeypatch.setattr("app.llm.adaptive.collect_quantities", forbidden)
    calls = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        calls.append(props)
        if "missing" in props:
            return reply(
                info, {"answer": None, "missing": ["Backup protocol"], "evidence_operation": hint}
            )
        assert "action" in props
        if not searches:
            return reply(info, {"action": "search", "query": "backup protocol"})
        return reply(info, {"action": "answer", "answer": answer("The backup uses SSH.", "E2.S1")})

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert not json.loads(result.raw)["abstain"] and result.failure_code is None
    assert len(calls) == 3 and searches == ["backup protocol"]
    assert not state.quantities and not state.collection_outcomes


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_budget", [2, 8])
async def test_rejected_collection_can_recover_with_new_source_and_keeps_checkpoint(tool_budget):
    searches = []

    async def retrieve(query):
        searches.append(query)
        return [block("The complete regional total is 10.", "complete")]

    dependencies = deps(
        "North 3\nSouth 7", question="What is the total?", derived_answers=True, retrieve=retrieve
    )
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="failed")
    calls = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        calls.append(props)
        if "missing" in props:
            return reply(
                info,
                {
                    "answer": None,
                    "missing": ["Complete regional coverage"],
                    "evidence_operation": "calculate",
                },
            )
        if "available" in props:
            return reply(
                info, {"available": True, "support_ids": ["E1.S1"], "context_support_ids": []}
            )
        if "operands" in props:
            return reply(info, text_arithmetic())
        if "inputs" in props:
            return reply(
                info, {"inputs": "supported", "coverage": "unknown", "operation": "supported"}
            )
        if "action" not in props:
            assert tool_budget == 2 and searches
            return reply(info, answer("10", "E2.S1"))
        receipt = payload(messages)["collection_outcomes"][-1]
        assert receipt["status"] == "review_unresolved"
        if not searches:
            return reply(info, {"action": "search", "query": "complete regional total"})
        return reply(info, {"action": "answer", "answer": answer("10", "E2.S1")})

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        fast_path=True,
        max_requests=12,
        max_tool_calls=tool_budget,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"], state.needs
    assert json.loads(result.raw)["answer_parts"][0]["text"] == "10"
    assert len(searches) == 1 and len(calls) == 7
    restored = ResearchState.model_validate_json(state.model_dump_json())
    failed = restored.quantities[restored.collection_outcomes[-1].record_ids[0]]
    assert failed.provisional_values == ["10"] and not failed.values and not failed.check.accepted


@pytest.mark.asyncio
async def test_numeric_lookup_retains_need_constraints_and_unavailable_tool_resumes_search():
    dependencies = deps("Partial table", question="What is the rate?", derived_answers=True)
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="ready")
    need = state.add_need(
        EvidenceNeedSpec(
            description="Rate lookup",
            operation="lookup",
            constraints=[NeedConstraint(dimension="metric", value="rate", question_quote="rate")],
        )
    )
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "missing" in props:
            roles.append("fast")
            return reply(
                info,
                {
                    "answer": None,
                    "missing": ["Full rate table"],
                    "evidence_operation": "numeric_lookup",
                },
            )
        if "available" in props:
            roles.append("selector")
            assert payload(messages)["need"]["constraints"][0]["value"] == "rate"
            return reply(info, {"available": False, "support_ids": [], "context_support_ids": []})
        if "action" in props:
            roles.append("reader")
            assert payload(messages)["collection_outcomes"][-1]["status"] == "not_found"
            return reply(info, {"action": "stop"})
        roles.append("finalizer")
        return reply(info, {"abstain": True, "answer_parts": []})

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert result.failure_code is None and json.loads(result.raw)["abstain"]
    assert roles == ["fast", "selector", "reader", "finalizer"]
    assert state.collection_outcomes[-1].need_id == need.id


@pytest.mark.asyncio
async def test_failed_quantity_does_not_hide_independently_checked_fact_at_finalization():
    from app.llm.adaptive import finalize_research
    from app.llm.quantity_state import QuantityAssessment, QuantityRecord
    from app.llm.research_state import DataExtraction, EvidenceRef, ObservedValue
    from tests.test_adaptive import session
    from tests.test_quantities import arithmetic

    dependencies = deps("North 3\nSouth 7", question="What is North?", derived_answers=True)
    active = session(dependencies)
    active.state.need_planning = "failed"
    active.state.quantities["failed"] = QuantityRecord(
        id="failed",
        pages=[],
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual",
        document_version="v1",
        draft=arithmetic(),
        modality="text",
        assessments=[
            QuantityAssessment(inputs="supported", coverage="unknown", operation="supported")
        ],
    )
    active.state.add_facts(
        DataExtraction(values=[ObservedValue(category="North", value="3", witness="North 3")]),
        EvidenceRef(support_id="E1.S1", source_id="manual", document_version="v1"),
        "text_witness",
    )
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        assert role == "finalizer" and data["facts"]
        return output_type.model_validate(answer("3"))

    active.call = call
    result, _ = await finalize_research(active)
    assert not result.abstain and result.answer_parts[0].text == "3"
    assert calls == ["finalizer"]
