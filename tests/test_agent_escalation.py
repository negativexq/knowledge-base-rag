"""The fixed answer path runs first; the agent is an escalation, never a regression."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.llm.escalation import classic_first
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings


def block(text="The service uses TLS.", id="c1"):
    return SearchResult(
        id=id,
        score=1.0,
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": "manual",
            "tenant_id": "tenant-a",
            "page_number": 1,
            "paragraph_index": 0,
        },
    )


def verdict(*, abstain, codes=(), visual=False):
    return {
        "type": "security_validation",
        "passed": not abstain,
        "abstain": abstain,
        "visual_answer": visual,
        "validator_failure_codes": list(codes),
        "application_forced_abstention": abstain and bool(codes),
    }


def answered(content="TLS [E1.S1]"):
    return [
        {"type": "metadata", "pipeline_version": "pipeline_support_ids"},
        {"type": "token", "content": content},
        verdict(abstain=False),
    ]


def withheld(*codes):
    return [
        {"type": "metadata", "pipeline_version": "pipeline_support_ids"},
        {"type": "token", "content": "I could not verify an answer."},
        verdict(abstain=True, codes=codes),
    ]


def streams(classic_runs, agent_events=None):
    calls = {"classic": [], "agent": []}

    async def classic(blocks):
        calls["classic"].append(blocks)
        for event in classic_runs[len(calls["classic"]) - 1]:
            yield event

    async def agent(outcome):
        calls["agent"].append(outcome)
        for event in agent_events or []:
            yield event

    return classic, agent, calls


async def collect(events):
    return [e async for e in events]


@pytest.mark.asyncio
async def test_classic_answer_is_released_without_running_the_agent():
    classic, agent, calls = streams([answered()])
    events = await collect(classic_first([block()], classic, agent))
    assert calls["agent"] == []
    assert [e["type"] for e in events] == ["metadata", "token", "security_validation"]
    assert events[0]["escalation"] == {
        "mode": "escalate",
        "escalated": False,
        "classic_outcome": "answered",
        "classic_failure_codes": [],
    }


@pytest.mark.asyncio
async def test_visual_classic_answer_counts_as_answered():
    classic, agent, calls = streams([[verdict(abstain=False, visual=True)]])
    await collect(classic_first([block()], classic, agent))
    assert calls["agent"] == []


@pytest.mark.asyncio
async def test_withheld_classic_answer_escalates_with_code_generated_reasons():
    agent_events = [
        {"type": "research_progress", "operation": "search", "status": "running"},
        {"type": "metadata", "pipeline_version": "pipeline_agentic_v1"},
        {"type": "token", "content": "SSH [E2.S1]"},
        verdict(abstain=False),
    ]
    classic, agent, calls = streams([withheld("VERSION_NOT_IN_SUPPORT")], agent_events)
    events = await collect(classic_first([block()], classic, agent))
    assert calls["agent"][0].failure_codes == ("VERSION_NOT_IN_SUPPORT",)
    # The withheld classic events are discarded; only the agent's answer is released.
    assert [e.get("content") for e in events if e["type"] == "token"] == ["SSH [E2.S1]"]
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["escalation"]["escalated"] is True
    assert metadata["escalation"]["classic_outcome"] == "withheld"


@pytest.mark.asyncio
async def test_progress_streams_live_while_the_agent_answer_is_held_for_release():
    agent_events = [
        {"type": "metadata"},
        {"type": "research_progress", "operation": "search", "status": "running"},
        {"type": "token", "content": "SSH"},
        verdict(abstain=False),
    ]
    classic, agent, _ = streams([withheld()], agent_events)
    events = await collect(classic_first([block()], classic, agent))
    assert events[0]["type"] == "research_progress"


@pytest.mark.asyncio
async def test_direct_requests_skip_the_classic_attempt():
    classic, agent, calls = streams([], answered())
    await collect(classic_first([block()], classic, agent, direct=True))
    assert calls["classic"] == [] and calls["agent"] == [None]


@pytest.mark.asyncio
async def test_exhausted_agent_answers_once_from_the_evidence_it_gathered():
    gathered = [block(), block("The backup service uses SSH.", id="c2")]
    agent_events = [
        {"type": "metadata"},
        {"type": "evidence_update", "blocks": gathered},
        {"type": "token", "content": "I could not verify an answer."},
        verdict(abstain=True, codes=["AGENT_BUDGET_EXCEEDED"]),
    ]
    classic, agent, calls = streams([withheld(), answered("SSH [E2.S1]")], agent_events)
    events = await collect(classic_first([block()], classic, agent))
    assert calls["classic"][1] == gathered
    assert [e["type"] for e in events][:2] == ["evidence_update", "metadata"]
    assert [e.get("content") for e in events if e["type"] == "token"] == ["SSH [E2.S1]"]
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["escalation"]["fallback"] == "classic_over_gathered_evidence"


@pytest.mark.asyncio
async def test_gathered_evidence_is_reauthorized_before_the_fallback_answer():
    gathered = [block(), block("Revoked text.", id="revoked")]
    agent_events = [
        {"type": "evidence_update", "blocks": gathered},
        verdict(abstain=True, codes=["AGENT_TIMEOUT"]),
    ]
    classic, agent, calls = streams([withheld(), answered()], agent_events)
    await collect(
        classic_first(
            [block()],
            classic,
            agent,
            authorize=lambda blocks: [b for b in blocks if b.id != "revoked"],
        )
    )
    # Only the initial block survives, so nothing new was gathered: no fallback.
    assert len(calls["classic"]) == 1


@pytest.mark.asyncio
async def test_validator_rejection_does_not_trigger_the_fallback():
    gathered = [block(), block("The backup service uses SSH.", id="c2")]
    agent_events = [
        {"type": "evidence_update", "blocks": gathered},
        verdict(abstain=True, codes=["SCOPE_RELEASE_UNVERIFIED"]),
    ]
    classic, agent, calls = streams([withheld(), answered()], agent_events)
    await collect(classic_first([block()], classic, agent))
    assert len(calls["classic"]) == 1


class ClassicProvider:
    supports_structured = True

    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    async def chat_json(self, *args, **kwargs):
        self.calls += 1
        return self.raw


def wired(monkeypatch, provider, agent_calls, **settings):
    import app.llm.agentic as agentic
    import app.wiring as wiring

    def model(messages, info):
        agent_calls.append(info)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "answer_parts": [
                            {"text": "The service uses TLS.", "support_ids": ["E1.S1"]}
                        ],
                        "abstain": False,
                    },
                )
            ]
        )

    @asynccontextmanager
    async def model_context(settings):
        yield FunctionModel(model)

    monkeypatch.setattr(wiring, "build_reranker", lambda _: None)
    monkeypatch.setattr(wiring, "get_chat_provider", lambda _: provider)
    monkeypatch.setattr(wiring, "count_prompt_tokens", lambda text: len(text.split()))
    monkeypatch.setattr(wiring, "active_embedding_config", lambda _: SimpleNamespace())
    monkeypatch.setattr(agentic, "agent_model", model_context)
    deps, _ = wiring.build_chat_dependencies(
        Settings(
            _env_file=None,
            agentic_rag_enabled=True,
            agentic_scope_validation_enabled=False,
            **settings,
        ),
        object(),
        object(),
        object(),
        "test",
    )
    return deps


@pytest.mark.asyncio
async def test_wiring_answers_classically_when_the_fixed_path_succeeds(monkeypatch):
    provider = ClassicProvider(
        '{"answer_parts":[{"text":"The service uses TLS.","support_ids":["E1.S1"]}],'
        '"abstain":false}'
    )
    agent_calls = []
    deps = wired(monkeypatch, provider, agent_calls)
    events = [e async for e in deps.stream_fn("What does the service use?", [block()])]
    assert provider.calls == 1 and agent_calls == []
    assert next(e for e in events if e["type"] == "security_validation")["passed"]
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["escalation"]["escalated"] is False


@pytest.mark.asyncio
async def test_wiring_escalates_to_the_agent_when_the_fixed_path_withholds(monkeypatch):
    provider = ClassicProvider('{"answer_parts":[],"abstain":true}')
    agent_calls = []
    deps = wired(monkeypatch, provider, agent_calls)
    events = [e async for e in deps.stream_fn("What does the service use?", [block()])]
    assert provider.calls == 1 and len(agent_calls) == 1
    assert next(e for e in events if e["type"] == "security_validation")["passed"]
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["pipeline_version"] == "pipeline_agentic_v1"
    assert metadata["escalation"]["escalated"] is True


@pytest.mark.asyncio
async def test_always_mode_keeps_the_agent_first(monkeypatch):
    provider = ClassicProvider('{"answer_parts":[],"abstain":true}')
    agent_calls = []
    deps = wired(monkeypatch, provider, agent_calls, agentic_mode="always")
    [e async for e in deps.stream_fn("What does the service use?", [block()])]
    assert provider.calls == 0 and len(agent_calls) == 1


def test_mode_is_validated():
    with pytest.raises(ValueError):
        Settings(_env_file=None, agentic_mode="sometimes")
