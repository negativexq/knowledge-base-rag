"""Code chooses which tools are visible, rejected claims are dropped rather than
retried, and admitted evidence is carried once per model request."""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.retrieval.hybrid_search import SearchResult

BACKUP = "The backup service uses SSH."


def block(text="The service uses TLS.", *, id="c1", source_id="manual"):
    return SearchResult(
        id=id,
        score=1.0,
        payload={"text": text, "source_id": source_id, "tenant_id": "tenant-a"},
    )


def deps(question="What does the service use?", blocks=None, **kwargs):
    ledger = EvidenceLedger(lambda text: len(text.split()), 5000)
    ledger.add([block()] if blocks is None else blocks)
    return AgentDependencies(question, ledger, **kwargs)


def final(info, *parts):
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name,
                {
                    "answer_parts": [{"text": t, "support_ids": [s]} for t, s in parts],
                    "abstain": not parts,
                },
            )
        ]
    )


def tools_seen(seen):
    def model(messages, info):
        seen.append(sorted(t.name for t in info.function_tools))
        return final(info)

    return model


class VisualProvider:
    supports_images = True

    async def chat_json(self, *args, **kwargs):
        raise AssertionError("not called")


async def no_retrieve(query):
    return []


# Partial release ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rejected_part_is_dropped_and_the_valid_part_released_without_retry():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        return final(info, ("The service uses TLS.", "E1.S1"), ("It also uses IPsec.", "E9.S1"))

    result = await run_agent(FunctionModel(model), deps())
    assert calls == 1 and result.failure_code is None
    assert [p["text"] for p in json.loads(result.raw)["answer_parts"]] == ["The service uses TLS."]
    event = next(e for e in result.telemetry["tools"] if e["tool"] == "partial_release")
    assert event["dropped_parts"] == 1 and "UNKNOWN_SUPPORT_ID" in event["failure_codes"]
    assert result.telemetry["budget"]["research"]["validation_rejections"] == 0


@pytest.mark.asyncio
async def test_all_parts_rejected_still_uses_the_repair_allowance():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return final(info, ("It uses IPsec.", "E9.S1"))
        return final(info, ("The service uses TLS.", "E1.S1"))

    result = await run_agent(FunctionModel(model), deps())
    assert calls == 2 and result.failure_code is None


@pytest.mark.asyncio
async def test_a_scope_rejected_claim_is_dropped_and_the_rest_keeps_a_release_receipt():
    checks = 0

    def model(messages, info):
        return final(info, ("The service uses TLS.", "E1.S1"), (BACKUP, "E1.S2"))

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
                                "verdict": "supported",
                                "reason": "NONE",
                                "witnesses": [
                                    {"support_id": "E1.S1", "quote": "The service uses TLS."}
                                ],
                            },
                            {
                                "claim_index": 1,
                                "verdict": "mismatch",
                                "reason": "ENTITY_MISMATCH",
                                "witnesses": [],
                            },
                        ]
                    },
                )
            ]
        )

    agent_deps = deps(
        blocks=[block("The service uses TLS.\n\n" + BACKUP)], scope_validation_enabled=True
    )
    result = await run_agent(FunctionModel(model), agent_deps, scope_model=FunctionModel(verifier))
    assert result.failure_code is None and checks == 1
    assert [p["text"] for p in json.loads(result.raw)["answer_parts"]] == ["The service uses TLS."]
    assert result.scope_receipt is not None
    assert result.scope_receipt.accepts(agent_deps.question, result.raw, agent_deps.ledger.units)


# Tool routing ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_available_research_tools_are_exposed():
    seen = []
    await run_agent(FunctionModel(tools_seen(seen)), deps())
    assert seen == [[]]
    seen.clear()
    await run_agent(FunctionModel(tools_seen(seen)), deps(retrieve=no_retrieve))
    assert seen == [["search"]]


@pytest.mark.asyncio
async def test_visual_tools_are_exposed_only_for_visual_questions():
    def visual_deps(question):
        return deps(
            question,
            retrieve=no_retrieve,
            visual_answers=True,
            render_page=lambda *args: None,
            provider=VisualProvider(),
        )

    seen = []
    await run_agent(FunctionModel(tools_seen(seen)), visual_deps("What does the service use?"))
    assert "read_pages" not in seen[0]
    seen.clear()
    await run_agent(
        FunctionModel(tools_seen(seen)), visual_deps("What color is the logo on the cover?")
    )
    assert "read_pages" in seen[0]


@pytest.mark.asyncio
async def test_operation_the_fixed_path_already_ran_waits_for_new_evidence():
    seen = []

    async def retrieve(query):
        return [block(BACKUP, id="c2")]

    def model(messages, info):
        seen.append(sorted(t.name for t in info.function_tools))
        if len(seen) == 1:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup"})])
        return final(info)

    agent_deps = deps(
        "What color is the chart bar?",
        retrieve=retrieve,
        visual_answers=True,
        render_page=lambda *args: None,
        provider=VisualProvider(),
        classic_tried=frozenset({"read_pages"}),
    )
    await run_agent(FunctionModel(model), agent_deps)
    assert "read_pages" not in seen[0]
    assert "read_pages" in seen[1]


@pytest.mark.asyncio
async def test_document_discovery_is_hidden_when_the_source_scope_is_fixed():
    def scoped(source_ids):
        return deps(documents=SimpleNamespace(source_ids=source_ids))

    seen = []
    await run_agent(FunctionModel(tools_seen(seen)), scoped(frozenset({"a", "b"})))
    await run_agent(FunctionModel(tools_seen(seen)), scoped(None))
    assert "find_documents" not in seen[0]
    assert "find_documents" in seen[1]


@pytest.mark.asyncio
async def test_comparison_alignment_needs_evidence_from_two_sources():
    seen = []
    await run_agent(FunctionModel(tools_seen(seen)), deps(blocks=[block(), block(BACKUP, id="c2")]))
    await run_agent(
        FunctionModel(tools_seen(seen)),
        deps(blocks=[block(), block(BACKUP, id="c2", source_id="other")]),
    )
    assert "compare_evidence" not in seen[0]
    assert "compare_evidence" in seen[1]


@pytest.mark.asyncio
async def test_empty_search_says_what_to_do_next():
    returned = []

    def model(messages, info):
        tool_returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        if not tool_returns:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup"})])
        returned.append(tool_returns[0].content)
        return final(info)

    await run_agent(FunctionModel(model), deps(retrieve=no_retrieve))
    assert returned[0]["added_blocks"] == 0
    assert "current evidence" in returned[0]["next_action"]


# Context --------------------------------------------------------------------


def prompt_parts(messages):
    return [
        p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ]


@pytest.mark.asyncio
async def test_admitted_evidence_is_carried_once_and_instructions_stay_stable():
    histories, instructions = [], []

    async def retrieve(query):
        return [block(f"Backup note {query} says SSH.", id=f"c{query}")]

    def model(messages, info):
        histories.append(messages)
        instructions.append(info.instructions)
        if len(histories) < 3:
            return ModelResponse(parts=[ToolCallPart("search", {"query": str(len(histories))})])
        return final(info, ("Backup note 1 says SSH.", "E3.S1"))

    agent_deps = deps(retrieve=retrieve)
    agent_deps.ledger = EvidenceLedger(lambda text: len(text.split()), 5000)
    agent_deps.ledger.add([block(), block("The archive uses SFTP.", id="c9")])
    await run_agent(FunctionModel(model), agent_deps)
    last = histories[-1]
    serialized = json.dumps([getattr(p, "content", "") for m in last for p in m.parts], default=str)
    for text in ("Backup note 1 says SSH.", "Backup note 2 says SSH.", "The archive uses SFTP."):
        assert serialized.count(text) == 1
    prompt = prompt_parts(last)[0].content
    assert prompt.index("E1.S1") < prompt.index("E3.S1") < prompt.index("E4.S1")
    assert len(set(instructions)) == 1


@pytest.mark.asyncio
async def test_closed_research_notice_is_a_message_not_an_instruction_change():
    histories, instructions = [], []

    def model(messages, info):
        histories.append(messages)
        instructions.append(info.instructions)
        if len(histories) == 1:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "a"})])
        if len(histories) == 2:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "b"})])
        return final(info)

    await run_agent(FunctionModel(model), deps(retrieve=no_retrieve))
    assert len(set(instructions)) == 1
    notices = [p for p in prompt_parts(histories[-1]) if "Research is closed" in str(p.content)]
    assert len(notices) == 1


@pytest.mark.asyncio
async def test_the_withheld_fixed_path_reason_is_given_to_the_agent():
    prompts = []

    def model(messages, info):
        prompts.append(prompt_parts(messages)[0].content)
        return final(info)

    await run_agent(FunctionModel(model), deps(classic_failure_codes=("VERSION_NOT_IN_SUPPORT",)))
    assert "VERSION_NOT_IN_SUPPORT" in prompts[0]


# Escalated runs: repair from present evidence, then research -----------------


@pytest.mark.asyncio
async def test_escalated_run_first_repairs_from_the_evidence_it_was_given():
    seen = []

    def model(messages, info):
        seen.append(sorted(t.name for t in info.function_tools))
        return final(info, ("The service uses TLS.", "E1.S1"))

    result = await run_agent(
        FunctionModel(model),
        deps(retrieve=no_retrieve, reread_first=True, classic_failure_codes=("X",)),
    )
    assert seen == [[]] and result.failure_code is None
    assert not json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_abstaining_on_reread_opens_research_without_spending_the_repair():
    seen = []

    async def retrieve(query):
        return [block(BACKUP, id="c2")]

    def model(messages, info):
        seen.append(sorted(t.name for t in info.function_tools))
        if len(seen) == 1:
            return final(info)
        if len(seen) == 2:
            return ModelResponse(parts=[ToolCallPart("search", {"query": "backup"})])
        return final(info, (BACKUP, "E2.S1"))

    result = await run_agent(FunctionModel(model), deps(retrieve=retrieve, reread_first=True))
    assert seen[0] == [] and "search" in seen[1]
    assert result.failure_code is None and not json.loads(result.raw)["abstain"]
    assert [e["tool"] for e in result.telemetry["tools"]][0] == "research_opened"
    assert result.telemetry["budget"]["research"]["validation_rejections"] == 0


@pytest.mark.asyncio
async def test_research_that_found_nothing_concludes_without_another_model_turn():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return final(info)
        return ModelResponse(parts=[ToolCallPart("search", {"query": "backup"})])

    result = await run_agent(FunctionModel(model), deps(retrieve=no_retrieve, reread_first=True))
    # The re-read already abstained on unchanged evidence; a third turn could not
    # see anything new, so code concludes with that abstention.
    assert calls == 2
    assert result.failure_code is None and json.loads(result.raw)["abstain"]
    assert result.telemetry["tools"][-1]["tool"] == "concluded_without_new_evidence"


# Telemetry ------------------------------------------------------------------


# Escalation canary audit: every agent run showed one tool attempt and no
# tool event; a tool that asked the model to retry left no trace of why.
@pytest.mark.asyncio
async def test_a_tool_that_asks_for_a_retry_is_recorded_with_its_reason():
    def model(messages, info):
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("search", {"query": "backup", "support_id": "E9.S1"})]
            )
        return final(info)

    result = await run_agent(FunctionModel(model), deps(retrieve=no_retrieve))
    failed = [e for e in result.telemetry["tools"] if e["tool"] == "tool_failed"]
    assert failed == [
        {"tool": "tool_failed", "operation": "search", "reason": "UNKNOWN_SUPPORT_ID"}
    ]
