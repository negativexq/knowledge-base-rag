import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.api.chat import ChatDependencies, _sse_event_stream
from app.llm.agentic import AgentCandidate, AgentDependencies, EvidenceLedger, run_agent
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext
from app.shared.config import Settings


def block(text="The service uses TLS.", id="c1", source_id="manual"):
    return SearchResult(
        id=id,
        score=1.0,
        payload={
            "text": text,
            "source_type": "filesystem",
            "source_id": source_id,
            "tenant_id": "tenant-a",
            "page_number": 1,
            "paragraph_index": 0,
        },
    )


class NoGeneration:
    async def chat_json(self, *args, **kwargs):
        raise AssertionError("The agent candidate must not trigger another generation call")


@pytest.mark.asyncio
async def test_candidate_is_revalidated_even_if_generator_returns_unchecked_claim():
    async def generator(query, blocks):
        return AgentCandidate(
            json.dumps(
                {
                    "answer_parts": [{"text": "The service uses TLS.", "support_ids": ["E99.S1"]}],
                    "abstain": False,
                }
            ),
            blocks,
        )

    events = [
        e
        async for e in stream_support_unit_answer(
            "What does the service use?",
            [block()],
            NoGeneration(),
            model="test",
            candidate_generator=generator,
        )
    ]
    security = next(e for e in events if e["type"] == "security_validation")
    assert security["abstain"]
    assert "UNKNOWN_SUPPORT_ID" in security["validator_failure_codes"]
    assert "The service uses TLS." not in "".join(
        e["content"] for e in events if e["type"] == "token"
    )


@pytest.mark.asyncio
async def test_budget_failure_is_application_abstention_with_reason():
    async def generator(query, blocks):
        return AgentCandidate(
            '{"answer_parts":[],"abstain":true}', blocks, failure_code="AGENT_BUDGET_EXCEEDED"
        )

    events = [
        e
        async for e in stream_support_unit_answer(
            "What does the service use?",
            [block()],
            NoGeneration(),
            model="test",
            candidate_generator=generator,
        )
    ]
    security = next(e for e in events if e["type"] == "security_validation")
    assert not security["passed"]
    assert security["application_forced_abstention"]
    assert security["validator_failure_codes"] == ["AGENT_BUDGET_EXCEEDED"]


@pytest.mark.asyncio
async def test_followup_search_keeps_acl_scope_and_refreshes_sources_before_answer():
    context = RetrievalContext(tenant_id="tenant-a")
    queries = []
    expansions = []

    async def search(query, passed_context, report, **scope):
        assert passed_context is context
        assert scope == {"source_ids": ["manual"]}
        queries.append(query)
        return [block() if len(queries) == 1 else block("The backup uses SSH.", "c2")]

    async def expand(blocks, passed_context):
        assert passed_context is context
        expansions.append(blocks[0].id)
        return blocks

    def model(messages, info):
        if not any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup protocol"})])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "answer_parts": [
                            {"text": "The backup uses SSH.", "support_ids": ["E2.S1"]}
                        ],
                        "abstain": False,
                    },
                )
            ]
        )

    async def stream(question, blocks, retrieve):
        async def generator(query, initial):
            ledger = EvidenceLedger(lambda text: len(text.split()), 1000)
            ledger.add(initial)
            return await run_agent(
                FunctionModel(model),
                AgentDependencies(
                    query,
                    ledger,
                    retrieve=retrieve,
                ),
            )

        async for event in stream_support_unit_answer(
            question,
            blocks,
            NoGeneration(),
            model="test",
            candidate_generator=generator,
        ):
            yield event

    deps = ChatDependencies(
        search_fn=search, stream_fn=stream, evidence_fn=expand, agentic_rag_enabled=True
    )
    events = [
        e
        async for e in _sse_event_stream(
            "What does the backup use?",
            deps,
            context,
            source_ids=["manual"],
        )
    ]
    assert queries == ["What does the backup use?", "backup protocol"]
    assert expansions == ["c1", "c2"]
    sources = [json.loads(e.split("data: ")[1]) for e in events if e.startswith("event: sources")]
    assert len(sources) == 2
    assert len(sources[-1]["sources"]) == 2
    metadata = [e for e in events if e.startswith("event: metadata")][-1]
    assert '"support_id": "E2.S1"' in metadata
    token_index = next(i for i, e in enumerate(events) if '"token"' in e)
    update_index = max(i for i, e in enumerate(events) if e.startswith("event: sources"))
    assert update_index < token_index
    assert "The backup uses SSH. [E2.S1]" in "".join(events)
    assert '"pipeline_version": "pipeline_agentic_v1"' in metadata


def test_agent_requires_support_contract():
    with pytest.raises(ValidationError, match="requires SUPPORT_IDS_ENABLED"):
        Settings(_env_file=None, agentic_rag_enabled=True, support_ids_enabled=False)


@pytest.mark.asyncio
async def test_wiring_selects_agent_without_enabling_operand_resolver(monkeypatch):
    import app.llm.agentic as agentic
    import app.wiring as wiring

    def model(messages, info):
        if "checks" in info.output_tools[0].parameters_json_schema.get("properties", {}):
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
    monkeypatch.setattr(wiring, "get_chat_provider", lambda _: NoGeneration())
    monkeypatch.setattr(wiring, "count_prompt_tokens", lambda text: len(text.split()))
    monkeypatch.setattr(wiring, "active_embedding_config", lambda _: SimpleNamespace())
    monkeypatch.setattr(agentic, "agent_model", model_context)
    deps, _ = wiring.build_chat_dependencies(
        Settings(_env_file=None, agentic_rag_enabled=True),
        object(),
        object(),
        object(),
        "test",
    )
    assert deps.agentic_rag_enabled
    assert not deps.operand_resolver_enabled
    assert deps.pipeline_version == "pipeline_agentic_v1"
    events = [e async for e in deps.stream_fn("What does the service use?", [block()])]
    assert next(e for e in events if e["type"] == "security_validation")["passed"]
    assert next(e for e in events if e["type"] == "metadata")["pipeline_version"] == (
        "pipeline_agentic_v1"
    )


@pytest.mark.asyncio
async def test_empty_initial_retrieval_still_allows_scoped_agent_search():
    context = RetrievalContext(tenant_id="tenant-a")
    called = []

    async def search(query, passed_context, report):
        assert passed_context is context
        called.append(query)
        return [] if len(called) == 1 else [block()]

    async def stream(question, blocks, retrieve):
        assert blocks == []
        assert len(await retrieve("alternate phrasing")) == 1
        yield {"type": "token", "content": "supported result"}

    deps = ChatDependencies(search_fn=search, stream_fn=stream, agentic_rag_enabled=True)
    events = [e async for e in _sse_event_stream("original", deps, context)]
    assert called == ["original", "alternate phrasing"]
    assert "supported result" in "".join(events)
