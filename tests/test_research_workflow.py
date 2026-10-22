import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.llm.research_events import publish, with_progress
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult


def deps():
    ledger = EvidenceLedger(lambda text: len(text.split()), 1000)
    ledger.add(
        [
            SearchResult(
                id=str(i),
                score=1,
                payload={
                    "text": text,
                    "source_id": source,
                    "source_type": "filesystem",
                    "document_version": "v1",
                    "page_number": 1,
                },
            )
            for i, (source, text) in enumerate(
                [("linux", "Linux uses TLS."), ("windows", "Windows uses SSH.")]
            )
        ]
    )
    return AgentDependencies("Compare these protocols", ledger)


@pytest.mark.asyncio
async def test_clarification_is_a_separate_outcome_without_unverified_answer():
    def model(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "abstain": True,
                        "answer_parts": [],
                        "clarification": {
                            "question": "Which platform?",
                            "options": ["Linux", "Windows"],
                        },
                    },
                )
            ]
        )

    d = deps()

    async def generator(query, blocks):
        return await run_agent(FunctionModel(model), d)

    events = [
        e
        async for e in stream_support_unit_answer(
            d.question,
            d.ledger.blocks,
            None,
            model="fake",
            candidate_generator=generator,
        )
    ]
    assert next(e for e in events if e["type"] == "clarification")["question"] == "Which platform?"
    assert not any(e["type"] in {"token", "security_validation"} for e in events)


@pytest.mark.asyncio
async def test_comparison_cells_are_validated_against_their_own_sources():
    def model(messages, info):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "abstain": False,
                        "answer_parts": [],
                        "comparison": [
                            {
                                "aspect": "Protocol",
                                "cells": [
                                    {
                                        "source_id": "linux",
                                        "text": "Linux uses TLS.",
                                        "support_ids": ["E1.S1"],
                                    },
                                    {
                                        "source_id": "windows",
                                        "text": "Windows uses SSH.",
                                        "support_ids": ["E2.S1"],
                                    },
                                ],
                            }
                        ],
                    },
                )
            ]
        )

    result = await run_agent(FunctionModel(model), deps())
    assert result.failure_code is None
    assert len(result.comparison) == 1
    assert len(json.loads(result.raw)["answer_parts"]) == 2

    def wrong_model(messages, info):
        data = model(messages, info).parts[0].args
        data["comparison"][0]["cells"][1]["support_ids"] = ["E1.S1"]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])

    bad = await run_agent(FunctionModel(wrong_model), deps(), retries=0)
    assert bad.failure_code is not None
    assert not bad.comparison


@pytest.mark.asyncio
async def test_progress_arrives_before_candidate_and_contains_no_drafts():
    def model(messages, info):
        if not any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
            return ModelResponse(
                parts=[ToolCallPart("compare_evidence", {"support_ids": ["E1.S1", "E2.S1"]})]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "abstain": True,
                        "answer_parts": [],
                    },
                )
            ]
        )

    events = [e async for e in with_progress(run_agent(FunctionModel(model), deps()))]
    progress = [e for e in events if e["type"] == "research_progress"]
    assert [e["status"] for e in progress[:2]] == ["running", "completed"]
    assert all(set(e) <= {"type", "id", "operation", "status"} for e in progress)
    assert events[-1]["type"] == "candidate"


@pytest.mark.asyncio
async def test_closing_progress_stream_cancels_underlying_work():
    cancelled = asyncio.Event()

    async def work():
        try:
            publish({"id": "test", "operation": "search", "status": "running"})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    stream = with_progress(work())
    assert (await anext(stream))["status"] == "running"
    await stream.aclose()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_closing_answer_stream_cancels_agent_and_resets_request_context():
    from app.api.chat import ChatDependencies, _sse_event_stream
    from app.evaluation.forensic_capture import current_capture
    from app.security.models import RetrievalContext

    stopped = asyncio.Event()

    async def generator(query, blocks):
        try:
            publish({"id": "search", "operation": "search", "status": "running"})
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def search(*args, **kwargs):
        return deps().ledger.blocks

    async def stream(query, blocks, **kwargs):
        from contextlib import aclosing

        async with aclosing(
            stream_support_unit_answer(
                query,
                blocks,
                None,
                model="fake",
                candidate_generator=generator,
            )
        ) as events:
            async for event in events:
                yield event

    chat = ChatDependencies(
        search_fn=search, stream_fn=stream, agentic_rag_enabled=True, forensic_capture_enabled=True
    )
    previous = current_capture()
    events = _sse_event_stream("Question", chat, RetrievalContext("a"))
    # The retrieval stage arrives first; wait for the agent's own operation.
    while '"operation": "search"' not in await anext(events):
        pass
    await events.aclose()
    assert stopped.is_set()
    assert current_capture() is previous
