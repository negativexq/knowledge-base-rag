"""A finished calculation reaches the browser as structured data: formula,
result, unit and every input with its value and citation."""

import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.research_budget import ResearchPolicy
from tests.test_adaptive import answer, deps, payload, reply


def model(messages, info):
    data = payload(messages)
    props = info.output_tools[0].parameters_json_schema["properties"]
    if "action" in props:
        if not data["facts"]:
            return reply(info, {"action": "extract", "need": "Read", "support_ids": ["E1.S1"]})
        return reply(
            info,
            {
                "action": "calculate",
                "need": "Sum",
                "calculation": {
                    "expression": "a+b",
                    "output_unit": "m",
                    "decimals": 2,
                    "inputs": [
                        {"name": chr(97 + i), "fact_id": f["id"]}
                        for i, f in enumerate(data["facts"])
                    ],
                },
            },
        )
    if "values" in props:
        return reply(
            info,
            {
                "values": [
                    {
                        "category": "A",
                        "value": "120",
                        "unit": "cm",
                        "status": "readable",
                        "witness": "A 120 cm",
                    },
                    {
                        "category": "B",
                        "value": "2",
                        "unit": "m",
                        "status": "readable",
                        "witness": "B 2 m",
                    },
                ]
            },
        )
    if "accepted_indexes" in props:
        return reply(info, {"accepted_indexes": [0, 1]})
    return reply(info, answer("The total length is 3.20 m.", "E2.S1"))


@pytest.mark.asyncio
async def test_candidate_carries_the_calculation_with_cited_inputs():
    candidate = await run_adaptive_agent(
        FunctionModel(model),
        deps("A 120 cm; B 2 m.", question="Total length?", derived_answers=True),
        research_policy=ResearchPolicy(max_research_requests=2),
    )
    [calc] = candidate.calculations
    assert calc["expression"] == "a+b"
    assert calc["result"] == "3.20" and calc["unit"] == "m"
    inputs = {i["name"]: i for i in calc["inputs"]}
    assert (inputs["a"]["label"], inputs["a"]["value"], inputs["a"]["unit"]) == ("A", "120", "cm")
    assert inputs["b"]["support_id"] == "E1.S1"
    # The answer cites the application-computed unit, so the card can attach to it.
    assert "E2.S1" in calc["support_ids"]
    assert "witness" not in str(calc)


@pytest.mark.asyncio
async def test_abstained_answers_carry_no_calculation_card():
    def abstain(messages, info):
        return reply(info, {"abstain": True, "answer_parts": []})

    candidate = await run_adaptive_agent(
        FunctionModel(abstain),
        deps("A 120 cm.", question="Total length?"),
        research_policy=ResearchPolicy(max_research_requests=1),
    )
    assert candidate.calculations == []


@pytest.mark.asyncio
async def test_answer_metadata_lists_calculations_beside_support_units():
    from app.llm.agentic import AgentCandidate
    from app.llm.structured_output import stream_support_unit_answer
    from tests.test_adaptive import block

    calc = {
        "id": "c1",
        "expression": "a+b",
        "result": "3",
        "unit": "m",
        "inputs": [],
        "support_ids": ["E1.S1"],
    }

    async def generator(query, blocks):
        return AgentCandidate(
            raw='{"abstain": false, "answer_parts": []}', blocks=[block()], calculations=[calc]
        )

    events = [
        e
        async for e in stream_support_unit_answer(
            "Q", [block()], None, model="fake", candidate_generator=generator
        )
    ]
    final = [e for e in events if e["type"] == "metadata" and "support_units" in e][-1]
    assert final["calculations"] == [calc]
