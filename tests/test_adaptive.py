"""Run the native PydanticAI workflow offline, without providers or credentials."""

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import fitz
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits

from app.llm.adaptive import (
    AdaptiveSession,
    ResearchDecision,
    finalize_research,
    run_adaptive_agent,
)
from app.llm.agentic import AgentDependencies, EvidenceLedger
from app.llm.research_budget import ResearchPolicy
from app.llm.research_state import ResearchEvent, ResearchState, TaskSpec
from app.llm.visual_answer import PdfPages
from app.retrieval.hybrid_search import SearchResult
from app.security.models import RetrievalContext
from app.shared.config import Settings
from tests.test_research_state import prepared


def block(text="The service uses TLS.", id="initial", **kwargs):
    return SearchResult(
        id=id,
        score=1,
        payload={
            "text": text,
            "source_id": "manual",
            "source_type": "filesystem",
            "tenant_id": "a",
            "document_version": "v1",
            "page_number": 1,
            **kwargs,
        },
    )


def deps(text="The service uses TLS.", question="What does the service use?", **kwargs):
    ledger = EvidenceLedger(
        lambda t: len(t.split()),
        15000,
        context=RetrievalContext("a"),
        source_ids=frozenset({"manual"}),
    )
    ledger.add([block(text)])
    return AgentDependencies(question, ledger, **kwargs)


def reply(info, data):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


def answer(text="The service uses TLS.", support="E1.S1"):
    return {"abstain": False, "answer_parts": [{"text": text, "support_ids": [support]}]}


def payload(messages):
    content = next(
        p.content for m in reversed(messages) for p in m.parts if isinstance(p, UserPromptPart)
    )
    return json.loads(content if isinstance(content, str) else content[0])


def scope(info, support="E1.S1", quote="The service uses TLS."):
    return reply(
        info,
        {
            "checks": [
                {
                    "claim_index": 0,
                    "verdict": "supported",
                    "reason": "NONE",
                    "witnesses": [{"support_id": support, "quote": quote}],
                }
            ]
        },
    )


def session(dependencies=None, state=None):
    dependencies = dependencies or deps()
    return AdaptiveSession(
        FunctionModel(lambda m, i: reply(i, {"abstain": True})),
        dependencies,
        state or ResearchState(task=TaskSpec(question=dependencies.question)),
        ResearchPolicy(),
        RunUsage(),
        UsageLimits(request_limit=6, total_tokens_limit=60000),
        time.monotonic() + 60,
        time.monotonic() + 40,
        None,
    )


@pytest.mark.asyncio
async def test_text_fast_path_uses_only_reader_and_scope():
    roles = []

    def model(messages, info):
        properties = info.output_tools[0].parameters_json_schema["properties"]
        roles.append("scope" if "checks" in properties else "reader")
        if "checks" in properties:
            return scope(info)
        return reply(info, {"action": "answer", "answer": answer()})

    result = await run_adaptive_agent(FunctionModel(model), deps(scope_validation_enabled=True))
    assert result.failure_code is None
    assert roles == ["reader", "scope"]
    assert result.scope_receipt.accepts(deps().question, result.raw, deps().ledger.units)
    assert result.telemetry["tool_calls"] == 0


@pytest.mark.asyncio
async def test_prepared_math_runs_without_reader_and_survives_zero_research_allowance():
    state, plan = prepared()
    state.pending_calculations.append(plan)
    seen = []

    def model(messages, info):
        data = payload(messages)
        seen.append(data)
        assert "action" not in info.output_tools[0].parameters_json_schema["properties"]
        assert data["computations"][0]["value"] == "3.20"
        return reply(info, answer("The total length is 3.20 m.", "E2.S1"))

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(
            "A 120 cm; B 2 m.",
            question=state.task.question,
            derived_answers=True,
        ),
        state=state,
        max_tool_calls=0,
    )
    assert result.failure_code is None
    assert len(seen) == 1
    assert state.research_stop == "TOOL_ATTEMPT_LIMIT"
    assert state.finalization == "answered" and len(state.computations) == 1
    assert "3.20 m" in result.raw


@pytest.mark.asyncio
async def test_finalization_can_run_independently_of_research():
    active = session()
    active.state.research_stop = "TOKEN_RESERVE"
    active.model = FunctionModel(lambda m, i: reply(i, answer()))
    result, receipt = await finalize_research(active)
    assert not result.abstain and receipt is None
    assert active.usage.requests == 1
    assert active.state.research_stop == "TOKEN_RESERVE"


@pytest.mark.asyncio
async def test_empty_searches_are_bounded_and_finalization_sees_existing_evidence():
    queries = []

    async def search(query):
        queries.append(query)
        return []

    def model(messages, info):
        if "action" in info.output_tools[0].parameters_json_schema["properties"]:
            # Changing only the explanation must not evade duplicate detection.
            return reply(
                info,
                {
                    "action": "search",
                    "query": "missing",
                    "need": f"Fact missing, iteration {len(queries)}",
                },
            )
        return reply(info, answer())

    result = await run_adaptive_agent(FunctionModel(model), deps(retrieve=search))
    assert result.failure_code is None and queries == ["missing"]
    assert result.telemetry["research_stop"] == "REPEATED_OPERATION"
    assert "TLS" in result.raw


@pytest.mark.asyncio
async def test_search_cannot_admit_other_tenants_or_out_of_scope_sources():
    active = session()
    assert not active.admit(
        [block("secret", "b", tenant_id="b"), block("secret", "c", source_id="other")]
    )
    assert list(active.units()) == ["E1.S1"]


@pytest.mark.asyncio
async def test_unknown_source_tool_is_blocked_before_document_access():
    active = session()
    with pytest.raises(ValueError, match="UNKNOWN_OR_REVOKED"):
        await active.execute(
            ResearchDecision(action="read", need="Missing", support_ids=["E99.S1"])
        )


@pytest.mark.asyncio
async def test_read_local_evidence_requires_no_document_reader_or_extra_model():
    active = session()
    active.deps.ledger.add([block("Additional source text.", "next")])
    assert await active.execute(
        ResearchDecision(action="read", need="Read next source", support_ids=["E2.S1"])
    )
    assert active.usage.requests == 0 and active.selected == ("E2.S1",)


@pytest.mark.parametrize(
    "data",
    [
        {"action": "extract", "support_ids": ["E1.S1", "E2.S1"]},
        {"action": "extract", "support_ids": ["E1.S1"], "page": 2},
    ],
)
def test_tool_arguments_cannot_expand_responsibilities(data):
    with pytest.raises(ValidationError):
        ResearchDecision(need="Missing evidence", **data)


def test_intent_fields_are_projected_to_only_the_selected_tools_arguments():
    read = ResearchDecision(action="read", need="Read this table", support_ids=["E1.S1"], page=3)
    assert read.tool_arguments() == {"support_ids": ["E1.S1"], "page": 3}
    search = ResearchDecision(action="search", query="x", support_ids=["E99.S1"])
    assert search.tool_arguments() == {"query": "x"}


@pytest.mark.asyncio
@pytest.mark.parametrize("value,accepted,facts", [("120", [0], 1), ("999", [0], 0), ("120", [], 0)])
async def test_text_extraction_is_source_bound_and_independently_checked(value, accepted, facts):
    active = session(deps("A 120 cm", question="PRIVATE QUESTION NOT FOR EXTRACTOR"))
    prompts = []

    def model(messages, info):
        data = payload(messages)
        prompts.append(json.dumps(data))
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "accepted_indexes" in props:
            assert data["source"] == "A 120 cm"
            return reply(info, {"accepted_indexes": accepted})
        return reply(
            info,
            {
                "values": [
                    {
                        "category": "A",
                        "value": value,
                        "unit": "cm",
                        "witness": "A 120 cm",
                        "status": "readable",
                    }
                ]
            },
        )

    active.model = FunctionModel(model)
    await active.execute(
        ResearchDecision(action="extract", need="Read value", support_ids=["E1.S1"])
    )
    assert len(active.state.facts) == facts
    assert len(active.deps.ledger.blocks) == 1  # No self-proving model text.
    assert all("PRIVATE QUESTION" not in p for p in prompts)


@pytest.mark.asyncio
async def test_image_extraction_uses_version_checked_original_page_and_independent_check(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "A 120 cm")
        pdf.save(path)
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active = session(
        deps("Chart on page 1.", visual_answers=True, render_page=PdfPages(str(tmp_path)))
    )
    # Use the actual version-checked PDF renderer, not a fake byte loader.
    active.deps.ledger.blocks[0].payload["source_id"] = "manual_pdf"
    active.deps.ledger.blocks[0].payload["document_version"] = version
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    calls = []

    def model(messages, info):
        part = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        assert not isinstance(part.content, str)
        assert part.content[1].data.startswith(b"\x89PNG")
        props = info.output_tools[0].parameters_json_schema["properties"]
        calls.append(props)
        if "accepted_indexes" in props:
            return reply(info, {"accepted_indexes": [0]})
        return reply(
            info,
            {
                "values": [
                    {
                        "category": "A",
                        "value": "120",
                        "unit": "cm",
                        "witness": "A 120 cm",
                        "status": "readable",
                    }
                ]
            },
        )

    active.model = FunctionModel(model)
    assert await active.execute(
        ResearchDecision(
            action="extract", need="Read chart", support_ids=["E1.S1"], modality="image"
        )
    )
    assert len(calls) == 2 and len(active.state.facts) == 1
    assert next(iter(active.state.facts.values())).method == "image_checked"
    assert active.deps.ledger.blocks[-1].payload["parent_support_id"] == "E1.S1"


@pytest.mark.asyncio
async def test_image_extraction_is_not_available_when_disabled():
    active = session()
    with pytest.raises(ValueError, match="IMAGE_EXTRACTION_DISABLED"):
        await active.execute(
            ResearchDecision(
                action="extract", need="Read chart", support_ids=["E1.S1"], modality="image"
            )
        )
    assert active.usage.requests == 0


@pytest.mark.asyncio
async def test_total_request_limit_reserves_finalizer_and_scope():
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "action" not in props  # Reader cannot consume the two reserved calls.
        roles.append("scope" if "checks" in props else "finalizer")
        return scope(info) if "checks" in props else reply(info, answer())

    result = await run_adaptive_agent(
        FunctionModel(model), deps(scope_validation_enabled=True), max_requests=2
    )
    assert roles == ["finalizer", "scope"]
    assert result.failure_code is None and result.telemetry["requests"] == 2
    assert result.telemetry["research_stop"] == "REQUEST_RESERVE"


@pytest.mark.asyncio
async def test_tool_timeout_preserves_final_answer():
    async def search(query):
        await asyncio.Event().wait()

    def model(messages, info):
        if "action" in info.output_tools[0].parameters_json_schema["properties"]:
            return reply(info, {"action": "search", "need": "Missing fact", "query": "x"})
        return reply(info, answer())

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(retrieve=search),
        research_policy=ResearchPolicy(tool_timeout_seconds=0.01, max_no_progress=1),
    )
    assert result.failure_code is None
    assert result.telemetry["research_stop"] == "NO_RESEARCH_PROGRESS"
    assert result.telemetry["tools"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_successful_results_remain_when_finalizer_fails():
    state, plan = prepared()
    state.pending_calculations.append(plan)

    def model(messages, info):
        raise RuntimeError("PRIVATE provider details")

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(
            "A 120 cm; B 2 m.",
            question=state.task.question,
            derived_answers=True,
        ),
        state=state,
        max_tool_calls=0,
    )
    assert result.failure_code == "ADAPTIVE_FINALIZATION_FAILED"
    assert len(state.facts) == 2 and len(state.computations) == 1
    assert state.finalization == "failed"
    assert "PRIVATE" not in json.dumps(result.telemetry)


def test_adaptive_is_opt_in_and_requires_support_ids_and_unambiguous_mode():
    assert not Settings(_env_file=None).adaptive_rag_enabled
    with pytest.raises(ValidationError, match="requires SUPPORT_IDS_ENABLED"):
        Settings(_env_file=None, adaptive_rag_enabled=True, support_ids_enabled=False)
    with pytest.raises(ValidationError, match="only one"):
        Settings(_env_file=None, adaptive_rag_enabled=True, agentic_rag_enabled=True)


def test_expanded_source_preserves_retrieval_anchors_instead_of_document_prefix():
    active = session()
    chunks = [
        {"chunk_id": f"cover-{i}", "section_key": "cover", "text": f"Cover metadata {i}."}
        for i in range(80)
    ] + [
        {"chunk_id": "target-a", "section_key": "answer", "text": "The service uses TLS."},
        {"chunk_id": "target-b", "section_key": "answer", "text": "The backup uses SSH."},
    ]
    active.deps.ledger = EvidenceLedger(lambda t: len(t.split()), 5000)
    active.deps.ledger.add(
        [
            block(
                "\n\n".join(c["text"] for c in chunks),
                section_chunks=chunks,
                anchor_chunk_ids=["target-b", "target-a"],
            )
        ]
    )
    visible = active.context()["evidence"]
    assert visible[0]["text"] == "The backup uses SSH."
    assert visible[1]["text"] == "The service uses TLS."
    assert len(visible) == 5 and len(active.units()) == 82


@pytest.mark.asyncio
async def test_invalid_decision_gets_one_bounded_repair_and_failed_output_is_retained():
    from app.evaluation.forensic_capture import (
        ForensicCapture,
        reset_current_capture,
        set_current_capture,
    )

    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Invalid tool args must never execute, but need not erase all research.
            return reply(
                info,
                {
                    "action": "extract",
                    "need": "Read two sources",
                    "support_ids": ["E1.S1", "E99.S1"],
                },
            )
        assert "MODEL_OUTPUT_INVALID" in str(payload(messages)["needs"])
        return reply(info, {"action": "answer", "answer": answer()})

    capture = ForensicCapture.create("question", raw_text=True)
    token = set_current_capture(capture)
    try:
        result = await run_adaptive_agent(FunctionModel(model), deps())
    finally:
        reset_current_capture(token)
    assert result.failure_code is None and calls == 2
    assert result.telemetry["tool_calls"] == 0
    assert "E99.S1" in capture.record["stages"]["adaptive_model_1_reader"]["raw_model_output"]


@pytest.mark.asyncio
async def test_reasoning_policy_is_role_specific_and_omits_temperature():
    seen = []

    def model(messages, info):
        seen.append(info.model_settings)
        return reply(info, {"abstain": True})

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(),
        max_tool_calls=0,
        model_settings={"temperature": 0.0},
        role_model_settings={
            "finalizer": {"openai_reasoning_effort": "medium", "temperature": None},
        },
    )
    assert result.failure_code is None
    assert seen[0]["openai_reasoning_effort"] == "medium"
    assert "temperature" not in seen[0]


@pytest.mark.asyncio
async def test_search_does_not_require_an_extra_prose_explanation():
    queries = []

    async def retrieve(query):
        queries.append(query)
        return []

    active = session(deps(retrieve=retrieve))
    await active.execute(
        ResearchDecision(action="search", query="Missing table values", support_ids=["E99.S1"])
    )
    assert queries == ["Missing table values"]


@pytest.mark.asyncio
async def test_read_page_passes_only_page_contract_and_preserves_fragmented_values():
    requests = []

    async def read(request):
        requests.append(request)
        return SimpleNamespace(
            blocks=[
                block(
                    "Table heading\n\nParty A\n\n21%\n\nParty B\n\n18%",
                    "chart",
                    page_number=13,
                )
            ]
        )

    active = session(deps(documents=SimpleNamespace(read=read)))
    decision = ResearchDecision(
        action="read", need="Read chart, do not search", support_ids=["E1.S1"], page=13
    )
    assert await active.execute(decision)
    assert requests[0].action == "page" and requests[0].page == 13
    assert not requests[0].query
    view = active.units()[active.selected[0]]
    assert "Party A\n21%" in view.text and "Party B\n18%" in view.text
    assert view.page_number == 13 and view.page_end == 13


@pytest.mark.asyncio
async def test_read_accepts_multiple_witnesses_but_only_one_document_version():
    active = session()
    active.deps.ledger.add([block("The backup uses SSH.", "next")])
    assert await active.execute(ResearchDecision(action="read", support_ids=["E1.S1", "E2.S1"]))
    active.deps.ledger.add([block("Other version.", "version2", document_version="v2")])
    with pytest.raises(ValueError, match="ONE_DOCUMENT_VERSION"):
        await active.execute(ResearchDecision(action="read", support_ids=["E1.S1", "E3.S1"]))


@pytest.mark.asyncio
async def test_finalizer_schema_error_has_a_shared_budget_repair():
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return reply(
                info,
                {
                    "abstain": False,
                    "answer_parts": [
                        {"text": "Incomplete citation", "support_ids": []},
                    ],
                },
            )
        return reply(info, answer())

    result = await run_adaptive_agent(FunctionModel(model), deps(), max_tool_calls=0)
    assert result.failure_code is None and calls == 2
    assert result.telemetry["observability"]["retries"] == 1


@pytest.mark.asyncio
async def test_abstention_draft_is_normalized_without_releasing_partial_claims_or_retrying():
    def model(messages, info):
        return reply(info, {"abstain": True, "answer_parts": answer()["answer_parts"]})

    result = await run_adaptive_agent(FunctionModel(model), deps(), max_tool_calls=0)
    assert result.failure_code is None
    assert json.loads(result.raw) == {"abstain": True, "answer_parts": []}
    assert result.telemetry["requests"] == 1


@pytest.mark.asyncio
async def test_local_read_opens_the_whole_selected_chunk_without_a_page_or_model_call():
    active = session(deps("Chart title\n\nParty A\n\n21%\n\nParty B\n\n18%"))
    first = ResearchDecision(action="read", support_ids=["E1.S2"], need="Read the full table")
    second = ResearchDecision(action="read", support_ids=["E1.S4"], need="Read another label")
    assert active.operation_signature(first) == active.operation_signature(second)
    assert await active.execute(first)
    assert active.usage.requests == 0
    visible = active.units()[active.selected[0]].text
    assert "Party A\n21%" in visible and "Party B\n18%" in visible


@pytest.mark.asyncio
async def test_read_view_keeps_equal_values_in_distinct_rows_but_not_duplicate_chunk_copies():
    text = "Table\n\nParty A\n\n21%\n\nParty B\n\n21%\n\nParty C\n\n18%"
    active = session(deps(text))
    active.deps.ledger.blocks[0].payload["contributing_chunk_ids"] = ["same-source-chunk"]
    active.deps.ledger.add([block(text, "same-source-chunk")])
    assert await active.execute(ResearchDecision(action="read", support_ids=["E1.S2"]))
    visible = active.units()[active.selected[0]].text
    assert visible.count("21%") == 2
    assert "Party A\n21%\nParty B\n21%\nParty C\n18%" in visible


@pytest.mark.asyncio
async def test_wiring_selects_adaptive_and_passes_existing_release_contract(monkeypatch):
    import app.llm.agentic as agentic
    import app.wiring as wiring

    class NoGeneration:
        async def generate(self, *args, **kwargs):
            raise AssertionError("Legacy generation must not run")

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "checks" in props:
            return scope(info)
        return reply(info, {"action": "answer", "answer": answer()})

    @asynccontextmanager
    async def models(settings):
        yield FunctionModel(model)

    monkeypatch.setattr(wiring, "build_reranker", lambda _: None)
    monkeypatch.setattr(wiring, "get_chat_provider", lambda _: NoGeneration())
    monkeypatch.setattr(wiring, "count_prompt_tokens", lambda t: len(t.split()))
    monkeypatch.setattr(wiring, "active_embedding_config", lambda _: SimpleNamespace())
    monkeypatch.setattr(agentic, "agent_model", models)
    dependencies, _ = wiring.build_chat_dependencies(
        Settings(_env_file=None, adaptive_rag_enabled=True),
        object(),
        object(),
        object(),
        "test",
    )
    assert dependencies.agentic_rag_enabled
    assert dependencies.pipeline_version == "pipeline_adaptive_v1"
    events = [e async for e in dependencies.stream_fn("What does the service use?", [block()])]
    assert next(e for e in events if e["type"] == "security_validation")["passed"]
    assert next(e for e in events if e["type"] == "metadata")["pipeline_version"] == (
        "pipeline_adaptive_v1"
    )


@pytest.mark.parametrize("action", ["read", "inspect"])
def test_source_read_cannot_silently_ignore_a_search_query(action):
    with pytest.raises(ValidationError, match="cannot search"):
        ResearchDecision(action=action, support_ids=["E1.S1"], query="Find missing evidence")


@pytest.mark.asyncio
@pytest.mark.parametrize("repeated", [False, True])
async def test_stalled_read_uses_restricted_search_then_answers_without_repeating_read(repeated):
    queries, read_turns, recovery_turns = [], [], []
    text = "Existing evidence"
    dependencies = deps(text, question="What protocol is used?")
    state = ResearchState(task=TaskSpec(question=dependencies.question))
    if repeated:
        state.events.append(
            ResearchEvent(
                operation="read",
                signature=session(dependencies, state).operation_signature(
                    ResearchDecision(action="read", support_ids=["E1.S1"])
                ),
                status="ok",
            )
        )

    async def retrieve(query):
        queries.append(query)
        return [block("The protocol is TLS.", id="located", page_number=9)]

    dependencies.retrieve = retrieve

    def model(messages, info):
        data = payload(messages)
        if data["read_recovery"] and data["read_recovery"]["status"] == "pending":
            recovery_turns.append(data)
            assert set(data["allowed_actions"]) == {"answer", "search", "stop"}
            assert info.output_tools[0].parameters_json_schema["properties"]["action"]["enum"] == [
                "search",
                "answer",
                "stop",
            ]
            return reply(info, {"action": "search", "query": "protocol specification"})
        if queries:
            support = next(e for e in data["evidence"] if e["text"] == "The protocol is TLS.")
            return reply(
                info,
                {
                    "action": "answer",
                    "answer": answer("The protocol is TLS.", support["support_unit_id"]),
                },
            )
        read_turns.append(True)
        return reply(info, {"action": "read", "support_ids": ["E1.S1"], "need": "Missing protocol"})

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        research_policy=ResearchPolicy(max_research_requests=6),
    )
    assert "TLS" in result.raw and not json.loads(result.raw)["abstain"]
    assert queries == ["protocol specification"] and len(recovery_turns) == 1
    assert len(read_turns) == 1
    assert [e.operation for e in state.events] == ["read", "search"]
    assert state.read_recovery.reason == ("REPEATED_READ" if repeated else "READ_NO_NEW_EVIDENCE")
    assert state.read_recovery.status == "search_requested"
    assert result.telemetry["tool_calls"] == (1 if repeated else 2)


@pytest.mark.asyncio
async def test_recovery_empty_search_preserves_evidence_and_obeys_no_progress_limit():
    queries = []
    dependencies = deps()
    state = ResearchState(task=TaskSpec(question=dependencies.question))

    async def retrieve(query):
        queries.append(query)
        return []

    dependencies.retrieve = retrieve

    def model(messages, info):
        data = payload(messages)
        if "action" not in info.output_tools[0].parameters_json_schema["properties"]:
            assert data["evidence"] and state.events[0].status == "not_found"
            return reply(info, answer())
        if data["read_recovery"]:
            return reply(info, {"action": "search", "query": "missing evidence"})
        return reply(info, {"action": "read", "support_ids": ["E1.S1"]})

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        research_policy=ResearchPolicy(max_research_requests=6),
    )
    assert queries == ["missing evidence"]
    assert state.research_stop == "NO_RESEARCH_PROGRESS"
    assert state.finalization == "answered" and "TLS" in result.raw
    assert result.telemetry["tool_calls"] == 2


@pytest.mark.asyncio
async def test_recovery_cannot_exceed_tool_limit_or_consume_reserved_finalization():
    queries = []
    dependencies = deps()
    state = ResearchState(task=TaskSpec(question=dependencies.question))

    async def retrieve(query):
        queries.append(query)
        return []

    dependencies.retrieve = retrieve

    def model(messages, info):
        if "action" in info.output_tools[0].parameters_json_schema["properties"]:
            return reply(info, {"action": "read", "support_ids": ["E1.S1"]})
        return reply(info, answer())

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, max_tool_calls=1
    )
    assert not queries and state.research_stop == "TOOL_ATTEMPT_LIMIT"
    assert state.read_recovery.status == "failed"
    assert state.finalization == "answered" and result.telemetry["tool_calls"] == 1


@pytest.mark.asyncio
async def test_stalled_read_without_search_capability_still_finalizes():
    def model(messages, info):
        if "action" in info.output_tools[0].parameters_json_schema["properties"]:
            return reply(info, {"action": "read", "support_ids": ["E1.S1"]})
        return reply(info, answer())

    state = ResearchState(task=TaskSpec(question=deps().question))
    result = await run_adaptive_agent(FunctionModel(model), deps(), state=state)
    assert state.read_recovery is None and state.research_stop == "REPEATED_OPERATION"
    assert "TLS" in result.raw


@pytest.mark.asyncio
@pytest.mark.parametrize("adaptive,failure", [(True, False), (False, False), (True, True)])
async def test_release_distinguishes_insufficient_evidence_without_changing_legacy_or_errors(
    adaptive, failure
):
    from app.llm.agentic import AgentCandidate
    from app.llm.prompt import NOT_FOUND_PHRASE
    from app.llm.structured_output import UNVERIFIED_ANSWER_PHRASE, stream_support_unit_answer

    async def generate(*_):
        return AgentCandidate(
            raw='{"abstain":true,"answer_parts":[]}',
            blocks=[block()],
            telemetry={
                "pipeline_version": "pipeline_adaptive_v1" if adaptive else "pipeline_agentic_v1",
                "abstention_reason": "INSUFFICIENT_EVIDENCE",
            },
            failure_code="ADAPTIVE_FINALIZATION_FAILED" if failure else None,
        )

    events = [
        e
        async for e in stream_support_unit_answer(
            "What is missing?", [], None, model="fake", candidate_generator=generate
        )
    ]
    visible = "".join(e["content"] for e in events if e["type"] == "token")
    security = next(e for e in events if e["type"] == "security_validation")
    assert security["abstain"] and security["citation_suppressed"]
    expected = "I could not obtain enough evidence to answer this question."
    assert visible == (
        UNVERIFIED_ANSWER_PHRASE if failure else expected if adaptive else NOT_FOUND_PHRASE
    )


@pytest.mark.asyncio
async def test_strict_no_progress_policy_takes_precedence_over_read_recovery():
    async def retrieve(_):
        raise AssertionError("No research allowance left for recovery search")

    def model(messages, info):
        if "action" in info.output_tools[0].parameters_json_schema["properties"]:
            return reply(info, {"action": "read", "support_ids": ["E1.S1"]})
        return reply(info, answer())

    state = ResearchState(task=TaskSpec(question=deps().question))
    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(retrieve=retrieve),
        state=state,
        research_policy=ResearchPolicy(max_no_progress=1),
    )
    assert state.read_recovery is None and state.research_stop == "NO_RESEARCH_PROGRESS"
    assert state.finalization == "answered" and result.telemetry["tool_calls"] == 1


def expanded_search_block(id, target, **kwargs):
    chunks = [
        {
            "chunk_id": f"{id}-child-{i}",
            "section_key": f"section-{i}",
            "text": f"Unrelated background section {i}.",
            "page_number": i + 1,
        }
        for i in range(20)
    ] + [{"chunk_id": f"{id}-target", "section_key": "target", "text": target, "page_number": 40}]
    return block(
        "\n\n".join(c["text"] for c in chunks),
        id=id,
        section_chunks=chunks,
        contributing_chunk_ids=[c["chunk_id"] for c in chunks],
        **kwargs,
    )


@pytest.mark.asyncio
async def test_expanded_search_parent_selects_child_table_for_next_model_and_finalizer():
    target = "Current rental obligations: 22 million. Noncurrent rental obligations: 35 million."

    async def retrieve(_):
        return [expanded_search_block("expanded-parent", target)]

    active = session(
        deps("Original inventory evidence.", question="What is inventory?", retrieve=retrieve)
    )
    active.compact_context = True
    assert await active.execute(
        ResearchDecision(action="search", query="current rental obligations")
    )
    record = active.state.search_evidence[0]
    selected = [active.units()[key] for key in active.selected]
    assert selected[0].text == target
    assert all(u.source_id == "manual" for u in selected)
    assert any("expanded-parent-target" in u.contributing_chunk_ids for u in selected)
    assert all("expanded-parent" not in u.contributing_chunk_ids for u in selected)
    for finalizing in [False, True]:
        context = active.context(finalizing=finalizing)
        assert target in [u["text"] for u in context["evidence"]]
        assert len(context["evidence"]) <= 12
    assert record.selected_support_ids[0] == active.selected[0]
    assert not active.state.facts and active.usage.requests == 0


@pytest.mark.asyncio
async def test_later_search_and_empty_result_do_not_hide_previous_search_input():
    results = {
        "rental obligations": [expanded_search_block("rental-parent", "Rental obligations: 22.")],
        "operating income": [expanded_search_block("income-parent", "Operating income: 18.")],
        "missing": [],
    }

    async def retrieve(query):
        return results[query]

    active = session(deps(retrieve=retrieve))
    active.compact_context = True
    for query in ["rental obligations", "operating income", "missing"]:
        await active.execute(ResearchDecision(action="search", query=query))
    assert len(active.state.search_evidence) == 2
    for finalizing in [False, True]:
        texts = [u["text"] for u in active.context(finalizing=finalizing)["evidence"]]
        assert "Rental obligations: 22." in texts and "Operating income: 18." in texts
        assert len(texts) <= 12
    assert active.usage.requests == 0 and not active.state.facts


@pytest.mark.asyncio
async def test_search_cycling_previously_exposed_evidence_is_not_progress_after_restore():
    sources = {
        key: block(f"Source {key} contains a useful witness.", id=key, contributing_chunk_ids=[key])
        for key in ("a", "b")
    }

    async def retrieve(query):
        return [sources[query]]

    active = session(deps(retrieve=retrieve))
    for query in ("a", "b"):
        assert await active.execute(ResearchDecision(action="search", query=query))
        active.context()
    restored = ResearchState.model_validate_json(active.state.model_dump_json())
    active = session(active.deps, restored)
    for query in ("a", "b", "a"):
        assert not await active.execute(ResearchDecision(action="search", query=query))
        active.context()
    assert len(active.state.search_evidence) == 2
    assert not active.state.facts and active.usage.requests == 0


@pytest.mark.asyncio
async def test_search_exposing_hidden_admitted_evidence_still_counts_as_progress():
    found = block("Hidden denominator: 24.", id="hidden", contributing_chunk_ids=["hidden"])

    async def retrieve(_):
        return [found]

    active = session(deps(retrieve=retrieve))
    active.deps.ledger.add(
        [block(f"Background {i}.", id=f"background-{i}") for i in range(8)] + [found]
    )
    before = set(active.units())
    hidden = next(key for key, unit in active.units().items() if unit.text == found.payload["text"])
    # Select enough other evidence to keep this admitted unit out of the actual
    # bounded context. A catalog preview does not count as a full exposure.
    active.selected = tuple(key for key in active.units() if key != hidden)
    active.context()
    assert hidden not in active.state.evidence_exposures
    assert await active.execute(ResearchDecision(action="search", query="denominator"))
    assert set(active.units()) == before
    assert active.state.search_evidence[-1].newly_exposed_support_ids == [hidden]
    active.context()
    assert not await active.execute(ResearchDecision(action="search", query="population size"))


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_answer", [True, False])
async def test_search_churn_stops_acquisition_without_losing_finalization(publish_answer):
    sources = [
        block("The service uses TLS.", id="tls", contributing_chunk_ids=["tls"]),
        block("The service supports HTTPS.", id="https", contributing_chunk_ids=["https"]),
    ]
    queries = []

    async def retrieve(query):
        queries.append(query)
        return [sources[(len(queries) - 1) % 2]]

    dependencies = deps(retrieve=retrieve, scope_validation_enabled=publish_answer)
    dependencies.ledger.add(sources)
    state = ResearchState(task=TaskSpec(question=dependencies.question))

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "action" in props:
            return reply(info, {"action": "search", "query": f"missing context {len(queries)}"})
        if "checks" in props:
            return scope(info)
        assert data["evidence"] and state.evidence_exposures
        return reply(info, answer() if publish_answer else {"abstain": True})

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, max_requests=10
    )
    # The first search exposes the second, previously deduplicated TLS witness;
    # it counts once. Two subsequent revisits do not reset acquisition progress.
    assert len(queries) == 3
    assert [event.status for event in state.events] == ["ok", "not_found", "not_found"]
    assert state.research_stop == "NO_RESEARCH_PROGRESS"
    assert state.finalization == ("answered" if publish_answer else "abstained")
    assert result.failure_code is None
    assert len(dependencies.ledger.units) == 3
    assert ("TLS" in result.raw) == publish_answer


@pytest.mark.asyncio
async def test_search_selection_only_uses_ledger_admitted_parents():
    async def retrieve(_):
        return [
            expanded_search_block("denied", "Rental obligations: SECRET.", tenant_id="b"),
            expanded_search_block("wrong-source", "Rental obligations: SECRET.", source_id="other"),
            expanded_search_block("accepted", "Rental obligations: 22."),
        ]

    active = session(deps(retrieve=retrieve))
    assert await active.execute(ResearchDecision(action="search", query="rental obligations"))
    context = active.context()
    assert "SECRET" not in json.dumps(context)
    assert active.state.search_evidence[0].selected_support_ids
    assert all(
        c.startswith("accepted-")
        for key in active.selected
        for c in active.units()[key].contributing_chunk_ids
    )


@pytest.mark.asyncio
async def test_targeted_search_fits_complete_table_when_expanded_section_exceeds_budget():
    target = "Table: year | rental obligations in million USD\n2020 | 14\n2021 | 22"
    found = expanded_search_block("large", target)
    for c in found.payload["section_chunks"][:-1]:
        c["text"] = "Irrelevant background " * 100
    found.payload["text"] = "\n\n".join(c["text"] for c in found.payload["section_chunks"])

    async def retrieve(_):
        return [found]

    dependencies = deps(retrieve=retrieve)
    dependencies.ledger._budget = 400
    active = session(dependencies)
    assert len(found.payload["text"].split()) > 400
    assert await active.execute(
        ResearchDecision(action="search", target_field="rental obligations")
    )
    assert any(u["text"] == target for u in active.context()["evidence"])
    assert dependencies.ledger.remaining_tokens >= 0


@pytest.mark.asyncio
async def test_identical_chunks_are_reused_without_additional_ledger_tokens():
    target = "Rental obligations: 22."
    found = expanded_search_block("large", target)

    async def retrieve(_):
        return [found]

    active = session(deps(retrieve=retrieve))
    decision = ResearchDecision(action="search", target_field="rental obligations")
    assert await active.execute(decision)
    count = len(active.deps.ledger.blocks)
    remaining = active.deps.ledger.remaining_tokens
    assert not await active.execute(decision)
    assert len(active.deps.ledger.blocks) == count
    assert active.deps.ledger.remaining_tokens == remaining
    assert any(u["text"] == target for u in active.context()["evidence"])


@pytest.mark.asyncio
async def test_covered_expansion_child_is_reused_from_original_authorized_block():
    target = "Rental obligations: 22."
    found = expanded_search_block("original-section", target)
    dependencies = deps()
    dependencies.ledger.add([found])

    async def retrieve(_):
        return [found]

    dependencies.retrieve = retrieve
    active = session(dependencies)
    remaining = dependencies.ledger.remaining_tokens
    assert await active.execute(
        ResearchDecision(action="search", target_field="rental obligations")
    )
    assert dependencies.ledger.remaining_tokens == remaining
    assert len(dependencies.ledger.blocks) == 2
    assert target in [u["text"] for u in active.context()["evidence"]]


@pytest.mark.asyncio
async def test_printed_source_math_needs_no_fact_ids_or_extra_model_call_and_keeps_sources():
    from app.llm.research_state import TextCalculationPlan

    active = session(deps("A for 2021 is 12.\n\nB for 2021 is 3.", derived_answers=True))
    plan = TextCalculationPlan(support_ids=["E1.S1", "E1.S2"], expression="12/3", decimals=2)
    assert await active.execute(ResearchDecision(action="calculate", text_calculation=plan))
    result = next(iter(active.state.text_computations.values()))
    assert result.value == "4.00" and not active.state.facts and active.usage.requests == 0
    assert result.proof_support_ids
    from app.llm.adaptive import AdaptiveAnswer

    draft = AdaptiveAnswer.model_validate(answer("The ratio is 4.00.", result.proof_support_ids[0]))
    verified, _ = await active.verify(draft)
    assert set(verified.answer_parts[0].support_ids) == {
        *result.proof_support_ids,
        "E1.S1",
        "E1.S2",
    }
    remaining = active.deps.ledger.remaining_tokens
    assert not active.calculate_text(plan)
    assert active.deps.ledger.remaining_tokens == remaining


@pytest.mark.asyncio
@pytest.mark.parametrize("expression", ["99/3", "__import__('os')", "12**3", "12/0"])
async def test_printed_source_math_rejects_unsourced_values_code_and_invalid_arithmetic(expression):
    from app.llm.research_state import TextCalculationPlan

    active = session(deps("Values are 12 and 3.", derived_answers=True))
    with pytest.raises(ValueError):
        active.calculate_text(TextCalculationPlan(support_ids=["E1.S1"], expression=expression))
    assert not active.state.text_computations


@pytest.mark.asyncio
async def test_text_math_success_survives_proof_admission_budget_failure_and_finalizes():
    from app.llm.research_state import TextCalculationPlan

    active = session(deps("Values are 12 and 3.", derived_answers=True))
    active.deps.ledger._budget -= active.deps.ledger.remaining_tokens
    active.calculate_text(TextCalculationPlan(support_ids=["E1.S1"], expression="12/3", decimals=2))
    result = next(iter(active.state.text_computations.values()))
    assert result.value == "4.00" and result.proof_support_ids == []

    def model(messages, info):
        assert payload(messages)["text_computations"][0]["value"] == "4.00"
        return reply(
            info,
            {
                "abstain": False,
                "answer_parts": [
                    {
                        "text": "The ratio is 4.00.",
                        "support_ids": ["E1.S1"],
                        "calculation": {"expression": "12/3", "result": "4.00"},
                    }
                ],
            },
        )

    active.model = FunctionModel(model)
    verified, _ = await finalize_research(active)
    assert not verified.abstain and active.usage.requests == 1


def test_decimal_source_math_is_application_rounded_and_bounded():
    from app.llm.calculation import evaluate_decimal_expression

    assert evaluate_decimal_expression("1.245", 2) == "1.24"
    assert evaluate_decimal_expression("1.255", 2) == "1.26"
    with pytest.raises(ValueError):
        evaluate_decimal_expression("1,245", 2)


@pytest.mark.asyncio
async def test_initial_operands_remain_visible_after_multiple_searches_and_finalization():
    async def retrieve(query):
        return [block(f"Found {query}.", id=query)]

    active = session(deps("Initial input is 17.", retrieve=retrieve))
    active.compact_context = True
    active.prepare_initial_context()
    for query in ["new input alpha", "new input beta", "new input gamma"]:
        await active.execute(ResearchDecision(action="search", target_field=query))
    for finalizing in [False, True]:
        data = active.context(finalizing=finalizing)
        assert "Initial input is 17." in [u["text"] for u in data["evidence"]]
        assert len(data["evidence"]) <= 12


@pytest.mark.asyncio
async def test_single_known_document_search_locates_field_without_another_model_call():
    from app.evidence.documents import DocumentResult

    requests = []

    async def retrieve(_):
        return []

    async def read(request):
        requests.append(request)
        return DocumentResult(
            [block("Operating margin for 2021 is 17.", id="located", page_number=8)], []
        )

    active = session(deps(retrieve=retrieve, documents=SimpleNamespace(read=read)))
    assert await active.execute(ResearchDecision(action="search", target_field="operating margin"))
    request = requests[0]
    assert request.action == "search" and request.search_mode == "ranked"
    assert request.document.source_id == "manual" and request.document.document_version == "v1"
    assert request.query == "operating margin" and request.limit == 3
    assert "17" in json.dumps(active.context()) and active.usage.requests == 0


def test_ranked_document_search_ignores_unmatched_qualifiers_but_keeps_complete_table():
    from app.evidence.documents import ranked_document_matches

    target = block("2021 | 2020\nOperating margin | 17 | 14", id="target")
    noise = [block("The company is a retailer.", id=f"noise-{i}") for i in range(10)]
    ranked = ranked_document_matches(
        [*noise, target], "FY2021 operating margin, dollars in millions"
    )
    assert ranked[0].id == "target" and ranked[0].payload["text"] == target.payload["text"]


@pytest.mark.asyncio
async def test_an_answer_rejected_three_times_for_one_reason_on_the_same_evidence_stops():
    # TechQA Q252: the reader re-sent reworded drafts of one answer, and each
    # drew the same objection, until the request budget ran out.
    calls = []

    def model(messages, info):
        properties = info.output_tools[0].parameters_json_schema["properties"]
        if "checks" in properties:
            calls.append("scope")
            check = {"claim_index": 0, "verdict": "mismatch", "reason": "ENTITY_MISMATCH"}
            return reply(info, {"checks": [{**check, "witnesses": []}]})
        if "action" in properties:
            calls.append("reader")
            return reply(info, {"action": "answer", "answer": answer()})
        calls.append("final")
        return reply(info, {"abstain": True, "answer_parts": []})

    result = await run_adaptive_agent(
        FunctionModel(model), deps(scope_validation_enabled=True), max_requests=10
    )
    assert result.telemetry["research_stop"] == "REPEATED_ANSWER_REJECTION"
    assert calls.count("reader") == 3


@pytest.mark.asyncio
async def test_a_sentence_the_scope_check_removes_is_dropped_from_the_released_answer():
    # TechQA Q112: one overreaching sentence used to reject the whole answer.
    text = "The service uses TLS. The same cause also breaks the export command."

    def model(messages, info):
        properties = info.output_tools[0].parameters_json_schema["properties"]
        if "checks" in properties:
            sentences = payload(messages)["claims"][0]["claim_sentences"]
            assert [s["sentence"] for s in sentences] == [1, 2]
            check = {
                "claim_index": 0,
                "verdict": "supported",
                "reason": "NONE",
                "witnesses": [{"support_id": "E1.S1", "start_line": 1, "end_line": 1}],
                "removed_sentences": [2],
            }
            return reply(info, {"checks": [check], "material_omissions": []})
        if "action" in properties:
            return reply(info, {"action": "answer", "answer": answer(text)})
        return reply(info, {"evidence_operation": "text", "answer": answer(text), "missing": []})

    dependencies = deps(scope_validation_enabled=True)
    result = await run_adaptive_agent(FunctionModel(model), dependencies, fast_path=True)
    assert result.failure_code is None
    assert json.loads(result.raw)["answer_parts"][0]["text"] == "The service uses TLS."
    assert result.scope_receipt.accepts(
        dependencies.question, result.raw, dependencies.ledger.units
    )
