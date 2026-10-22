"""The evidence plan reads only the question, so it can start before retrieval
finishes. It must count against the same request budget, be used at most
once, never belong to another question, and keep the failed-plan fallback."""

import asyncio
import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.api.chat import ChatDependencies
from app.llm.adaptive import plan_needs_early, run_adaptive_agent
from app.llm.research_needs import offer_plan
from tests.test_adaptive import answer, deps, payload
from tests.test_chat_no_evidence import _ask, _chunk, _client, _events
from tests.test_research_needs import QUESTION, reply, spec


def planner(calls, plan=None):
    def model(messages, info):
        calls.append(payload(messages))
        return reply(info, {"evidence_needs": [plan or spec().model_dump()]})

    return FunctionModel(model)


def research(roles):
    from tests.test_adaptive import scope

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "evidence_needs" in props:
            roles.append("planner")
            return reply(info, {"evidence_needs": [spec().model_dump()]})
        if "checks" in props:
            roles.append("scope")
            return scope(info, quote="Model-X F1 Small gold 12")
        roles.append("reader")
        if payload(messages).get("evidence_requirements"):
            roles.append("with_needs")
        return reply(info, {"action": "answer", "answer": answer("Model-X F1 Small gold 12")})

    return FunctionModel(model)


@pytest.mark.asyncio
async def test_a_plan_started_early_is_used_once_and_counted_in_the_same_budget():
    planned, roles = [], []
    early = asyncio.create_task(plan_needs_early(planner(planned), deps("", question=QUESTION)))
    offer = offer_plan(QUESTION, early)
    try:
        result = await run_adaptive_agent(
            research(roles),
            deps("Model-X F1 Small gold 12", question=QUESTION),
            evidence_needs_enabled=True,
            max_requests=3,
        )
    finally:
        await offer.close()
    assert planned == [{"question": QUESTION}]
    assert roles == ["reader", "with_needs"]
    assert not json.loads(result.raw)["abstain"]
    assert result.telemetry["requests"] == 2
    assert result.telemetry["observability"]["llm_requests"] == 2


@pytest.mark.asyncio
async def test_a_plan_for_another_question_is_never_used_and_is_cancelled():
    planned, roles = [], []
    started = asyncio.Event()

    async def slow_plan():
        started.set()
        await asyncio.sleep(3600)

    early = asyncio.create_task(slow_plan())
    offer = offer_plan("A different question?", early)
    await started.wait()
    try:
        await run_adaptive_agent(
            research(roles),
            deps("Model-X F1 Small gold 12", question=QUESTION),
            evidence_needs_enabled=True,
            max_requests=3,
        )
    finally:
        await offer.close()
    assert roles[0] == "planner"
    assert early.cancelled()
    assert planned == []


@pytest.mark.asyncio
async def test_an_invalid_early_plan_takes_the_same_fallback_as_a_late_one():
    planned, roles = [], []
    bad = spec().model_dump()
    bad["constraints"][0]["question_quote"] = "invented phrase"
    dependencies = deps(
        "Model-X F1 Small gold 12", question=QUESTION, scope_validation_enabled=True
    )
    early = asyncio.create_task(
        plan_needs_early(planner(planned, bad), deps("", question=QUESTION))
    )
    offer = offer_plan(QUESTION, early)
    try:
        result = await run_adaptive_agent(
            research(roles), dependencies, evidence_needs_enabled=True
        )
    finally:
        await offer.close()
    assert not json.loads(result.raw)["abstain"]
    assert roles == ["reader", "scope"]
    assert result.telemetry["requests"] == 3


class _Research:
    async def __call__(self, question, chunks, **kwargs):
        yield {"type": "metadata", "prompt_version": "v3", "trace_id": "t"}
        yield {"type": "token", "content": "Refunds take 30 days [E1.S1]"}


def test_research_mode_starts_the_plan_before_search_and_cancels_an_unused_one(tmp_path):
    seen = []

    async def early_plan(question):
        seen.append(("plan", question))
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            seen.append(("cancelled", question))
            raise

    async def search(question, context, report, **scope):
        await asyncio.sleep(0)
        seen.append(("search", question))
        return [_chunk()]

    deps = ChatDependencies(
        search_fn=search,
        stream_fn=_Research(),
        agentic_rag_enabled=True,
        plan_prefetch_fn=early_plan,
    )
    events = _events(_ask(_client(tmp_path, deps)))
    assert "sources" in [name for name, _ in events]
    question = "What is the refund window?"
    assert seen == [("plan", question), ("search", question), ("cancelled", question)]


def test_answer_mode_does_not_start_an_evidence_plan(tmp_path):
    seen = []

    async def early_plan(question):
        seen.append(question)

    async def search(question, context, report, **scope):
        return [_chunk()]

    deps = ChatDependencies(search_fn=search, stream_fn=_Research(), plan_prefetch_fn=early_plan)
    _events(_ask(_client(tmp_path, deps)))
    assert seen == []
