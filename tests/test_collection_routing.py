"""Typed dispatch and recovery preserve evidence without certifying failed drafts."""

import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint, ResearchState, TaskSpec
from tests.test_adaptive import answer, block, deps, payload, reply
from tests.test_quantities import text_arithmetic


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
    from app.llm.agentic import AgentAnswer
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
        return AgentAnswer.model_validate(answer("3"))

    active.call = call
    result, _ = await finalize_research(active)
    assert not result.abstain and result.answer_parts[0].text == "3"
    assert calls == ["finalizer"]
