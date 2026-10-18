"""Bound research without bypassing evidence or final scope validation."""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.llm.research_budget import ResearchPolicy
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings


def deps(**kwargs):
    ledger = EvidenceLedger(lambda text: len(text.split()), 5000)
    ledger.add(
        [
            SearchResult(
                id="initial",
                score=1,
                payload={
                    "text": "The service uses TLS.\n\nThe backup uses SSH.",
                    "source_id": "manual",
                },
            )
        ]
    )
    return AgentDependencies("Protocol?", ledger, **kwargs)


def returned(messages):
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def refuse(info):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"abstain": True})])


@pytest.mark.asyncio
async def test_identical_unproductive_search_runs_once_then_finalizes():
    searches = []

    async def retrieve(query):
        searches.append(query)
        return []

    def model(messages, info):
        if len(returned(messages)) < 2:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "missing"})])
        assert info.function_tools == []
        assert returned(messages)[-1].content["reason"] == "REPEATED_TOOL_CALL"
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps(retrieve=retrieve))
    assert result.failure_code is None
    assert searches == ["missing"]
    assert result.telemetry["requests"] == 3
    assert result.telemetry["budget"]["research"]["stop_reason"] == "REPEATED_TOOL_CALL"
    assert json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_two_distinct_empty_operations_close_research_before_hard_limit():
    calls = 0

    async def retrieve(query):
        nonlocal calls
        calls += 1
        return []

    def model(messages, info):
        if not returned(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("search", {"query": "one"}),
                    ToolCallPart("search", {"query": "two"}),
                ]
            )
        assert info.function_tools == []
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps(retrieve=retrieve))
    assert result.failure_code is None
    assert calls == 2 and result.telemetry["requests"] == 2
    assert result.telemetry["budget"]["research"]["stop_reason"] == "NO_RESEARCH_PROGRESS"


@pytest.mark.asyncio
async def test_identical_search_can_continue_after_new_evidence_changes_exclusion_set():
    calls = 0

    async def retrieve(query):
        nonlocal calls
        calls += 1
        return [
            SearchResult(
                id=f"new{calls}",
                score=1,
                payload={"text": f"New fact {calls}.", "source_id": "manual"},
            )
        ]

    def model(messages, info):
        if len(returned(messages)) < 2:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "more"})])
        assert info.function_tools == []
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps(retrieve=retrieve))
    assert result.failure_code is None
    assert calls == 2 and len(result.blocks) == 3


@pytest.mark.asyncio
async def test_execution_limit_is_enforced_inside_one_tool_batch():
    def model(messages, info):
        if not returned(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("read_document_section", {"support_id": "E1.S1"}),
                    ToolCallPart("read_document_section", {"support_id": "E1.S2"}),
                    ToolCallPart("read_document_section", {"support_id": "E1.S1"}),
                    ToolCallPart("read_document_section", {"support_id": "E1.S2"}),
                ]
            )
        assert info.function_tools == []
        assert (
            sum(
                isinstance(p.content, dict) and p.content.get("research_closed", False)
                for p in returned(messages)
            )
            == 2
        )
        return refuse(info)

    result = await run_agent(
        FunctionModel(model), deps(), research_policy=ResearchPolicy(max_tool_attempts=2)
    )
    assert result.failure_code is None
    policy = result.telemetry["budget"]["research"]
    assert policy["tool_attempts"] == 2 and policy["blocked_tool_calls"] == 2
    assert len([t for t in result.telemetry["tools"] if t["tool"] == "read_document_section"]) == 2


@pytest.mark.asyncio
async def test_tool_timeout_closes_research_but_leaves_a_final_response():
    cancelled = False

    async def retrieve(query):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    def model(messages, info):
        if not returned(messages):
            return ModelResponse(parts=[ToolCallPart("search", {"query": "slow"})])
        assert info.function_tools == []
        assert returned(messages)[0].content["reason"] == "TOOL_TIMEOUT"
        return refuse(info)

    result = await run_agent(
        FunctionModel(model),
        deps(retrieve=retrieve),
        research_policy=ResearchPolicy(tool_timeout_seconds=0.01),
    )
    assert result.failure_code is None and cancelled
    assert result.telemetry["requests"] == 2


@pytest.mark.asyncio
async def test_model_timeout_is_recorded_without_research_retry():
    calls = 0

    async def model(messages, info):
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()

    result = await run_agent(
        FunctionModel(model), deps(), research_policy=ResearchPolicy(model_timeout_seconds=0.01)
    )
    assert result.failure_code == "AGENT_TIMEOUT"
    assert calls == 1
    assert result.telemetry["budget"]["research"]["stop_reason"] == "MODEL_TIMEOUT"


def test_policy_is_server_configurable_and_validated(monkeypatch):
    monkeypatch.setenv("AGENTIC_RESEARCH_POLICY", '{"max_tool_attempts":2,"max_no_progress":1}')
    policy = Settings(_env_file=None).agentic_research_policy
    assert policy.max_tool_attempts == 2 and policy.max_no_progress == 1
    with pytest.raises(ValueError):
        ResearchPolicy(max_research_requests=0)


@pytest.mark.asyncio
async def test_soft_close_still_requires_and_obtains_scope_receipt():
    def model(messages, info):
        assert info.function_tools == []
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "abstain": False,
                        "answer_parts": [
                            {"text": "The service uses TLS.", "support_ids": ["E1.S1"]}
                        ],
                    },
                )
            ]
        )

    def verifier(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "checks": [
                            {
                                "claim_index": 0,
                                "verdict": "supported",
                                "reason": "NONE",
                                "witnesses": [
                                    {"support_id": "E1.S1", "quote": "The service uses TLS."}
                                ],
                            }
                        ]
                    },
                )
            ]
        )

    result = await run_agent(
        FunctionModel(model),
        deps(scope_validation_enabled=True),
        scope_model=FunctionModel(verifier),
        research_policy=ResearchPolicy(max_research_requests=1),
    )
    assert result.failure_code is None
    assert result.scope_receipt is not None and not result.scope_receipt.failure_codes
    assert result.telemetry["requests"] == 2
    assert result.telemetry["budget"]["research"]["stop_reason"] == "RESEARCH_TURN_LIMIT"


@pytest.mark.asyncio
async def test_rejected_scope_has_one_repair_and_cannot_be_released():
    calls = 0
    checks = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "abstain": False,
                        "answer_parts": [
                            {"text": "The service uses TLS.", "support_ids": ["E1.S1"]}
                        ],
                    },
                )
            ]
        )

    def verifier(messages, info):
        nonlocal checks
        checks += 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "checks": [
                            {
                                "claim_index": 0,
                                "verdict": "insufficient",
                                "reason": "SCOPE_NOT_ESTABLISHED",
                                "witnesses": [],
                            }
                        ]
                    },
                )
            ]
        )

    result = await run_agent(
        FunctionModel(model),
        deps(scope_validation_enabled=True),
        scope_model=FunctionModel(verifier),
    )
    assert result.failure_code == "AGENT_BUDGET_EXCEEDED"
    assert json.loads(result.raw)["abstain"] and result.scope_receipt is None
    assert calls == 2 and checks == 1  # identical rejected candidate uses cached receipt
    assert result.telemetry["budget"]["research"]["terminal_reason"] == "VALIDATION_REPAIR_LIMIT"


@pytest.mark.asyncio
async def test_final_candidate_has_one_tools_closed_repair_inside_shared_limit():
    calls = 0
    checks = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        assert info.function_tools == []
        claim = "The service uses TLS." if calls == 1 else "The backup uses SSH."
        support = "E1.S1" if calls == 1 else "E1.S2"
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"abstain": False, "answer_parts": [{"text": claim, "support_ids": [support]}]},
                )
            ]
        )

    def verifier(messages, info):
        nonlocal checks
        checks += 1
        judgment = {
            "claim_index": 0,
            "verdict": "insufficient",
            "reason": "SCOPE_NOT_ESTABLISHED",
            "witnesses": [],
        }
        if checks == 2:
            judgment = {
                "claim_index": 0,
                "verdict": "supported",
                "reason": "NONE",
                "witnesses": [{"support_id": "E1.S2", "quote": "The backup uses SSH."}],
            }
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"checks": [judgment]})]
        )

    result = await run_agent(
        FunctionModel(model),
        deps(scope_validation_enabled=True),
        scope_model=FunctionModel(verifier),
        max_requests=4,
        research_policy=ResearchPolicy(max_research_requests=1),
    )
    assert result.failure_code is None
    assert calls == 2 and checks == 2 and result.telemetry["requests"] == 4
    assert result.telemetry["budget"]["research"]["research_requests"] == 1
    assert result.telemetry["budget"]["research"]["repair_requests"] == 1
    assert result.scope_receipt is not None and not result.scope_receipt.failure_codes
    assert "SSH" in result.raw
