"""Offline checks of live-smoke grading; never call a provider."""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.shared.config import Settings
from scripts.experiments.run_agentic_security_smoke import cases, run_case


@pytest.fixture
def smoke_tracer(monkeypatch):
    provider = TracerProvider()
    tracer = provider.get_tracer("test.smoke")
    monkeypatch.setattr("app.llm.agent_observability.get_tracer", lambda _: tracer)
    monkeypatch.setattr("app.llm.structured_output.get_tracer", lambda _: tracer)
    yield tracer
    provider.shutdown()


async def test_unexercised_poisoned_tool_is_inconclusive(smoke_tracer):
    case = next(c for c in cases() if c.id == "tool_result_poison")

    def model(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "answer_parts": [
                            {"text": "The primary service uses TLS.", "support_ids": ["E1.S1"]}
                        ],
                        "abstain": False,
                    },
                )
            ]
        )

    row = await run_case(case, Settings(_env_file=None), FunctionModel(model), smoke_tracer)
    assert row["security_pass"] is None
    assert row["scenario_exercised"] is False
    assert row["quality_pass"] is False


async def test_provider_failure_is_not_a_security_pass(smoke_tracer):
    def model(*_):
        raise RuntimeError("synthetic provider failure")

    row = await run_case(cases()[0], Settings(_env_file=None), FunctionModel(model), smoke_tracer)
    assert row["infrastructure_failure"] == "AGENT_RUN_FAILED"
    assert row["security_pass"] is None
    assert row["quality_pass"] is False


async def test_acl_probe_requires_search_and_keeps_wrong_tenant_out(smoke_tracer):
    case = next(c for c in cases() if c.id == "cross_tenant_result")

    def model(messages, info):
        if not any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
            return ModelResponse(parts=[ToolCallPart("search", {"query": "vault code"})])
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

    row = await run_case(case, Settings(_env_file=None), FunctionModel(model), smoke_tracer)
    assert row["scenario_exercised"] is True
    assert row["admitted_source_ids"] == []
    assert row["security_pass"] is True
    assert row["quality_pass"] is True
