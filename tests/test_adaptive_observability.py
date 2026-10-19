"""Prove evidence lineage, failure reasons and safe UI trace visibility offline."""

import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.models.function import FunctionModel

from app.evaluation.forensic_capture import (
    ForensicCapture,
    reset_current_capture,
    set_current_capture,
)
from app.llm import agent_observability as obs
from app.llm.adaptive import run_adaptive_agent
from app.llm.research_budget import ResearchPolicy
from app.llm.research_state import ResearchState, TaskSpec
from app.shared.trace_client import _parse_spans
from tests.test_adaptive import answer, block, deps, payload, reply, session


@pytest.fixture
def tracing(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.adaptive")
    monkeypatch.setattr(obs, "get_tracer", lambda _: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.mark.asyncio
async def test_extraction_calculation_and_finalization_share_trace_and_keep_evidence_links(tracing):
    tracer, exporter = tracing

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "action" in props:
            if not data["facts"]:
                return reply(
                    info,
                    {"action": "extract", "need": "Read source operands", "support_ids": ["E1.S1"]},
                )
            return reply(
                info,
                {
                    "action": "calculate",
                    "need": "Sum sourced lengths",
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
        assert data["allowed_actions"] == ["answer"]
        return reply(info, answer("The total length is 3.20 m.", "E2.S1"))

    with tracer.start_as_current_span("chat_request") as root:
        result = await run_adaptive_agent(
            FunctionModel(model),
            deps(
                "PRIVATE SOURCE. A 120 cm; B 2 m.",
                question="Total length?",
                derived_answers=True,
            ),
            research_policy=ResearchPolicy(max_research_requests=2),
        )
    assert result.failure_code is None
    spans = exporter.get_finished_spans()
    assert all(s.context.trace_id == root.get_span_context().trace_id for s in spans)
    by_name = {s.name: s for s in spans}
    assert {
        "research.decide",
        "tool.extract",
        "evidence.extract.validate",
        "tool.calculate",
        "evidence.admit",
        "research.context",
        "research.finalize",
        "answer.validate",
    } <= set(by_name)
    extraction = by_name["evidence.extract.validate"].attributes
    assert extraction["evidence.input_support_ids"] == ("E1.S1",)
    assert extraction["extraction.retained_count"] == 2
    calculated = by_name["calculation.execute"].attributes
    assert len(calculated["calculation.input_fact_ids"]) == 2
    assert calculated["calculation.result_support_ids"] == ("E2.S1",)
    assert by_name["answer.validate"].attributes["evidence.cited_support_ids"] == ("E2.S1",)
    assert by_name["research.finalize"].attributes["research.stop_reason"] == "RESEARCH_TURN_LIMIT"
    exported = repr([(s.attributes, s.events) for s in spans])
    assert "PRIVATE SOURCE" not in exported
    assert "total length is 3.20" not in exported
    assert all(s.parent for s in spans if s.name != "chat_request")


@pytest.mark.asyncio
async def test_context_omission_and_admission_losses_are_distinguishable(tracing):
    active = session()
    active.deps.ledger.add([block(f"Evidence {i}.", str(i)) for i in range(8)])
    active.context()
    active.admit(
        [
            block("secret", "denied", tenant_id="b"),
            block("The service uses TLS.", "initial"),
            block("x " * 20000, "oversized"),
        ]
    )
    spans = tracing[1].get_finished_spans()
    context = next(s for s in spans if s.name == "research.context").attributes
    assert len(context["evidence.available_ids"]) == 9
    assert len(context["evidence.selected_ids"]) == 5
    assert len(context["evidence.omitted_ids"]) == 4
    admission = next(s for s in spans if s.name == "evidence.admit").attributes
    assert admission["evidence.authorization_or_scope_excluded"] == 1
    assert admission["evidence.duplicate_blocks"] == 1
    assert admission["evidence.budget_excluded_blocks"] == 1
    assert set(admission["evidence.dropped_block_ids"]) == {"denied", "initial", "oversized"}


@pytest.mark.asyncio
async def test_rejected_extraction_is_visible_and_not_a_fact(tracing):
    active = session(deps("A 120 cm"))

    def model(messages, info):
        if "accepted_indexes" in info.output_tools[0].parameters_json_schema["properties"]:
            return reply(info, {"accepted_indexes": [0]})
        return reply(
            info,
            {
                "values": [
                    {
                        "category": "A",
                        "value": "999",
                        "unit": "cm",
                        "witness": "A 120 cm",
                        "status": "readable",
                    }
                ]
            },
        )

    active.model = FunctionModel(model)
    from app.llm.adaptive import ResearchDecision

    await active.execute(
        ResearchDecision(action="extract", need="Read value", support_ids=["E1.S1"])
    )
    assert not active.state.facts
    assert len(active.state.extractions) == 1
    attrs = next(
        s for s in tracing[1].get_finished_spans() if s.name == "evidence.extract.validate"
    ).attributes
    assert attrs["extraction.retained_count"] == 0
    assert attrs["extraction.rejected_count"] == 1
    assert attrs["research.outcome"] == "rejected"


def test_safe_trace_api_preserves_new_lineage_fields_but_excludes_content():
    spans = _parse_spans(
        {
            "data": [
                {
                    "spans": [
                        {
                            "operationName": "evidence.admit",
                            "duration": 1000,
                            "startTime": 1,
                            "tags": [
                                {"key": k, "value": v}
                                for k, v in {
                                    "evidence.input_block_ids": ["initial"],
                                    "evidence.budget_excluded_blocks": 1,
                                    "calculation.result_id": "C1",
                                    "raw_model_output": "SECRET",
                                    "password": "SECRET",
                                }.items()
                            ],
                        }
                    ]
                }
            ]
        }
    )
    assert spans[0].attributes == {
        "evidence.input_block_ids": ["initial"],
        "evidence.budget_excluded_blocks": 1,
        "calculation.result_id": "C1",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_enabled", [False, True])
async def test_full_results_available_only_in_explicit_forensic_capture(raw_enabled):
    capture = ForensicCapture.create("PRIVATE QUESTION", raw_text=raw_enabled)
    token = set_current_capture(capture)
    state = ResearchState(task=TaskSpec(question="PRIVATE QUESTION"))

    def model(messages, info):
        return reply(info, {"action": "answer", "answer": answer()})

    try:
        await run_adaptive_agent(
            FunctionModel(model), deps(question="PRIVATE QUESTION"), state=state
        )
    finally:
        reset_current_capture(token)
    record = json.dumps(capture.snapshot())
    assert ("PRIVATE QUESTION" in record) is raw_enabled
    assert ("The service uses TLS." in record) is raw_enabled
    assert "adaptive_state" in record and "adaptive_model_1_reader" in record
