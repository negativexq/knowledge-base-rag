"""Exercise the actual PydanticAI loop without network calls or model credentials."""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.retrieval.hybrid_search import SearchResult


def block(text="The service uses TLS.", *, id="c1", **payload):
    return SearchResult(
        id=id,
        score=1.0,
        payload={
            "text": text,
            "source_id": "manual",
            "tenant_id": "tenant-a",
            **payload,
        },
    )


def dependencies(blocks=None, **kwargs):
    ledger = EvidenceLedger(lambda text: len(text.split()), 1000)
    ledger.add([block()] if blocks is None else blocks)
    return AgentDependencies("What does the service use?", ledger, **kwargs)


def answer(info, text="The service uses TLS.", support_id="E1.S1", **kwargs):
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name,
                {
                    "answer_parts": [{"text": text, "support_ids": [support_id], **kwargs}],
                    "abstain": False,
                },
            )
        ]
    )


def refusal(info):
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name,
                {
                    "answer_parts": [],
                    "abstain": True,
                },
            )
        ]
    )


def returns(messages):
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


@pytest.mark.asyncio
async def test_sufficient_initial_evidence_needs_no_tools():
    def model(messages, info):
        return answer(info)

    result = await run_agent(FunctionModel(model), dependencies())
    assert not json.loads(result.raw)["abstain"]
    assert result.failure_code is None
    assert result.telemetry["requests"] == 1
    assert result.telemetry["tool_calls"] == 0


@pytest.mark.asyncio
async def test_missing_fact_is_searched_and_new_ids_stay_stable():
    seen = []

    async def retrieve(query):
        seen.append(query)
        return [block(), block("The backup service uses SSH.", id="c2", evidence_id="E1")]

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup protocol"})])
        assert "E2.S1" in returns(messages)[0].content
        return answer(info, "The backup service uses SSH.", "E2.S1")

    deps = dependencies(retrieve=retrieve)
    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None
    assert seen == ["backup protocol"]
    assert [u.support_unit_id for u in deps.ledger.units] == ["E1.S1", "E2.S1"]
    assert result.telemetry["tools"][0]["added_blocks"] == 1
    assert not json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_unknown_citations_trigger_validation_retry_before_release():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return answer(info, support_id="E99.S1")
        assert any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts)
        return answer(info)

    result = await run_agent(FunctionModel(model), dependencies())
    assert result.failure_code is None
    assert calls == 2
    assert result.telemetry["tools"][0]["tool"] == "validation_retry"
    assert "UNKNOWN_SUPPORT_ID" in result.telemetry["tools"][0]["failure_codes"]


@pytest.mark.asyncio
async def test_calculate_uses_existing_verifier():
    deps = dependencies([block("59% use the internet.")], derived_answers=True)
    deps.question = "What percentage do not use the internet?"

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "calculate",
                        {
                            "expression": "100 - 59",
                            "support_ids": ["E1.S1"],
                            "decimals": 0,
                        },
                    )
                ]
            )
        calculation = returns(messages)[0].content
        assert calculation["result"] == "41"
        return answer(
            info,
            "41% do not use the internet.",
            calculation={
                "expression": calculation["expression"],
                "result": calculation["result"],
            },
        )

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None
    assert not json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_unprinted_operands_are_rejected():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "calculate",
                        {
                            "expression": "123 + 456",
                            "support_ids": ["E1.S1"],
                        },
                    )
                ]
            )
        assert any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts)
        return refusal(info)

    result = await run_agent(FunctionModel(model), dependencies(derived_answers=True))
    assert json.loads(result.raw)["abstain"]
    assert result.failure_code is None


@pytest.mark.asyncio
async def test_request_limit_fails_closed_without_partial_answer():
    def model(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "read_document_section",
                    {
                        "support_id": "E1.S1",
                    },
                )
            ]
        )

    result = await run_agent(FunctionModel(model), dependencies(), max_requests=2)
    assert result.failure_code == "AGENT_BUDGET_EXCEEDED"
    assert json.loads(result.raw) == {"answer_parts": [], "abstain": True}
    assert result.telemetry["requests"] == 2


@pytest.mark.asyncio
async def test_timeout_fails_closed():
    async def model(messages, info):
        await asyncio.sleep(1)
        return answer(info)

    result = await run_agent(FunctionModel(model), dependencies(), timeout_seconds=0.01)
    assert result.failure_code == "AGENT_TIMEOUT"
    assert json.loads(result.raw)["abstain"]


def test_ledger_drops_hidden_unauthorized_and_over_budget_blocks():
    ledger = EvidenceLedger(lambda text: len(text.split()), 50)
    added = ledger.add(
        [
            block(authorized=False),
            block(model_visible=False),
            block("long " * 60),
            block(),
        ]
    )
    assert len(added) == 1
    assert ledger.units[0].support_unit_id == "E1.S1"
    assert ledger.add([block()]) == []


@pytest.mark.asyncio
async def test_fabricated_visual_reading_cannot_bypass_validation():
    def model(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "answer_parts": [],
                        "abstain": False,
                        "visual_reading_id": "V1",
                    },
                )
            ]
        )

    result = await run_agent(FunctionModel(model), dependencies(), retries=0)
    assert result.failure_code == "AGENT_RUN_FAILED"
    assert result.visual is None
    assert json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_unsupported_year_cannot_be_answered_from_nearby_evidence():
    deps = dependencies()
    deps.question = "What protocol did the service use in 1999?"

    def model(messages, info):
        if any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts):
            return refusal(info)
        return answer(info)

    result = await run_agent(FunctionModel(model), deps)
    assert json.loads(result.raw)["abstain"]
    assert result.failure_code is None
