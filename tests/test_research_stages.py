import asyncio

import pytest

from app.llm.agent_observability import operation
from app.llm.research_events import publish, with_progress
from app.llm.research_stages import STAGE_MESSAGES, stage_event, stage_for

SAFE_KEYS = {"type", "id", "kind", "stage", "status", "message", "reason", "duration_ms"}


async def collect(work):
    return [e async for e in with_progress(work)]


def stages(events):
    return [e for e in events if e.get("kind") == "stage"]


def test_span_names_map_to_user_stages():
    assert stage_for("quantity.source.select") == ("source_selection", None)
    assert stage_for("quantity.review") == ("input_review", None)
    assert stage_for("quantity.execute") == ("calculation", None)
    assert stage_for("answer.scope_validate") == ("scope_validation", None)
    assert stage_for("quantity.repair.scope") == ("evidence_repair", "scope_mismatch")
    assert stage_for("answer.repair.coverage") == ("evidence_repair", "incomplete_coverage")
    assert stage_for("research.finalize") == ("finalization", None)
    # Wrappers and model calls are not stages of their own.
    assert stage_for("tool.collect") is None
    assert stage_for("llm.request") is None
    assert stage_for("agent.run") is None


def test_every_stage_and_reason_has_an_application_message():
    names = {"quantity.source.select", "quantity.repair.scope", "answer.repair.coverage"}
    for name in names:
        stage, reason = stage_for(name)
        assert STAGE_MESSAGES[stage]
        event = stage_event("x", stage, "running", reason=reason)
        assert event["message"]


@pytest.mark.asyncio
async def test_stage_transitions_close_the_previous_stage_with_its_duration():
    async def work():
        with operation("quantity.source.select"):
            await asyncio.sleep(0.01)
        with operation("quantity.contract"):
            pass
        return "done"

    events = await collect(work())
    seen = [(e["stage"], e["status"]) for e in stages(events)]
    assert seen == [
        ("source_selection", "running"),
        ("source_selection", "completed"),
        ("evidence_planning", "running"),
        ("evidence_planning", "completed"),
    ]
    closed = stages(events)[1]
    assert closed["duration_ms"] >= 10
    assert events[-1] == {"type": "candidate", "candidate": "done"}
    assert all(set(e) <= SAFE_KEYS for e in stages(events))


@pytest.mark.asyncio
async def test_nested_stage_returns_to_its_parent_and_consecutive_spans_merge():
    async def work():
        with operation("quantity.review"):
            with operation("quantity.gap.review"):
                pass
            with operation("quantity.repair.inputs"):
                pass
        with operation("quantity.execute"):
            pass

    events = stages(await collect(work()))
    running = [e["stage"] for e in events if e["status"] == "running"]
    # The nested gap review is the same stage, so no new entry; the repair
    # interrupts the review, which then resumes as a new entry.
    assert running == ["input_review", "evidence_repair", "input_review", "calculation"]
    repair = next(e for e in events if e["stage"] == "evidence_repair")
    assert repair["reason"] == "input_check_failed"
    assert len({e["id"] for e in events}) == 4


@pytest.mark.asyncio
async def test_a_failed_stage_is_reported_and_the_stream_still_closes():
    async def work():
        with operation("quantity.review"):
            raise TimeoutError

    events = []
    with pytest.raises(TimeoutError):
        async for event in with_progress(work()):
            events.append(event)
    seen = [(e["stage"], e["status"], e.get("reason")) for e in stages(events)]
    assert seen == [("input_review", "running", None), ("input_review", "failed", "timeout")]


@pytest.mark.asyncio
async def test_failed_inner_stage_that_the_workflow_recovers_from_is_marked_retrying():
    async def work():
        with operation("quantity.review"):
            try:
                with operation("quantity.execute"):
                    raise ValueError("bad input")
            except ValueError:
                pass

    events = stages(await collect(work()))
    calc = [e for e in events if e["stage"] == "calculation"]
    assert [e["status"] for e in calc] == ["running", "retrying"]
    assert calc[-1]["reason"] == "check_failed"
    assert events[-1]["stage"] == "input_review" and events[-1]["status"] == "completed"


@pytest.mark.asyncio
async def test_operation_events_keep_flowing_beside_stages():
    async def work():
        with operation("quantity.source.select"):
            publish({"id": "op1", "operation": "collect", "status": "running"})

    events = await collect(work())
    kinds = [e.get("kind", "operation") for e in events if e["type"] == "research_progress"]
    assert kinds == ["stage", "operation", "stage"]


@pytest.mark.asyncio
async def test_adaptive_research_streams_its_real_stages_without_content():
    from pydantic_ai.models.function import FunctionModel

    from app.llm.adaptive import run_adaptive_agent
    from app.llm.research_budget import ResearchPolicy
    from tests.test_adaptive import answer, deps, payload, reply

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "action" in props:
            if not data["facts"]:
                return reply(info, {"action": "extract", "need": "Read", "support_ids": ["E1.S1"]})
            return reply(
                info,
                {
                    "action": "calculate",
                    "need": "Sum",
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
            values = [("A", "120", "cm"), ("B", "2", "m")]
            return reply(
                info,
                {
                    "values": [
                        {
                            "category": c,
                            "value": v,
                            "unit": u,
                            "status": "readable",
                            "witness": f"{c} {v} {u}",
                        }
                        for c, v, u in values
                    ]
                },
            )
        if "accepted_indexes" in props:
            return reply(info, {"accepted_indexes": [0, 1]})
        return reply(info, answer("The total length is 3.20 m.", "E2.S1"))

    work = run_adaptive_agent(
        FunctionModel(model),
        deps("PRIVATE SOURCE. A 120 cm; B 2 m.", question="Total length?", derived_answers=True),
        research_policy=ResearchPolicy(max_research_requests=2),
    )
    events = await collect(work)
    progress = [e for e in events if e["type"] == "research_progress"]
    seen = [e["stage"] for e in stages(events) if e["status"] == "running"]
    assert "calculation" in seen and "finalization" in seen
    assert all(e["status"] != "running" for e in stages(events)[-1:])
    extract = [
        e for e in progress if e.get("operation") == "extract" and e["status"] == "completed"
    ]
    assert extract and extract[0]["added_evidence"] == 0  # extraction adds facts, not sources
    # Fixed application text only: no source text, question or model output.
    assert "PRIVATE" not in str(progress) and "Total length" not in str(progress)
