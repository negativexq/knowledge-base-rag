"""Generic evidence requirements: wrong object, accurate-but-irrelevant data and budgets."""

import hashlib
import json

import fitz
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import UserPromptPart
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import ResearchDecision, finalize_research, run_adaptive_agent
from app.llm.research_needs import NeedWorkflow, ScopedExtractionCheck
from app.llm.research_state import (
    DataExtraction,
    EvidenceNeedSpec,
    NeedConstraint,
    SourceMatch,
)
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import answer, deps, payload, session
from tests.test_adaptive import reply as raw_reply

QUESTION = "List the F1 scores for Model-X using Small in the gold condition."


def reply(info, data):
    if "relevant_indexes" in data and "bindings" not in data:
        data = {
            **data,
            "bindings": [
                {"observation_index": i, "verdicts": ["supported"] * len(data["checks"])}
                for i in data["relevant_indexes"]
            ],
        }
    return raw_reply(info, data)


def spec():
    return EvidenceNeedSpec(
        description="Requested model's F1 scores",
        operation="sort",
        constraints=[
            NeedConstraint(dimension="entity", value="Model-X", question_quote="Model-X"),
            NeedConstraint(dimension="metric", value="F1", question_quote="F1"),
            NeedConstraint(
                dimension="condition",
                value="Small; gold",
                question_quote="Small in the gold condition",
            ),
        ],
    )


def checks(verdict="supported"):
    return [{"constraint_index": i, "verdict": verdict} for i in range(3)]


def active_session():
    active = session(deps("Model-X F1 Small gold 12", question=QUESTION))
    active.need_workflow = NeedWorkflow(active)
    active.state.add_need(spec())
    active.state.need_planning = "ready"
    return active


def observation(category="Model-X", value="12", witness="Model-X F1 Small gold 12"):
    return {"category": category, "value": value, "witness": witness, "status": "readable"}


def test_question_constraints_have_no_expected_answer_and_cannot_invent_question_bindings():
    active = active_session()
    existing = list(active.state.evidence_needs)
    same = active.state.add_need(spec())
    assert list(active.state.evidence_needs) == existing
    assert same.status == "unresolved" and not same.fact_ids
    bad = spec().model_copy(
        update={
            "constraints": [
                NeedConstraint(dimension="period", value="2030", question_quote="in 2030")
            ]
        }
    )
    with pytest.raises(ValueError, match="NEED_NOT_GROUNDED"):
        active.state.add_need(bad)
    assert len(active.state.evidence_needs) == 1
    with pytest.raises(ValidationError):
        EvidenceNeedSpec.model_validate({**spec().model_dump(), "expected_answer": "12"})


@pytest.mark.parametrize(
    "provided", [checks()[:-1], [checks()[0]] * 3, checks("unknown"), checks("mismatch")]
)
def test_missing_duplicate_unknown_or_conflicting_scope_bindings_never_match(provided):
    assert not SourceMatch(title="Looks similar", checks=provided).matches(spec())


@pytest.mark.asyncio
async def test_mismatched_source_stops_before_extraction_and_does_not_satisfy_need():
    active = active_session()
    calls = []

    def model(messages, info):
        calls.append(info.output_tools[0].parameters_json_schema["properties"])
        return reply(
            info, {"kind": "chart", "title": "Retrieval recall", "checks": checks("mismatch")}
        )

    active.model = FunctionModel(model)
    assert not await active.execute(ResearchDecision(action="extract", support_ids=["E1.S1"]))
    assert len(calls) == 1 and "accepted_indexes" not in calls[0]
    assert not active.state.extractions and not active.state.facts
    assert not active.state.source_selections[-1].accepted
    assert next(iter(active.state.evidence_needs.values())).status == "unresolved"
    assert "SOURCE_NEED_MISMATCH" in active.state.needs[-1]


@pytest.mark.asyncio
async def test_correctly_read_but_wrong_scope_observation_is_retained_not_promoted():
    active = active_session()

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "kind" in props:
            return reply(info, {"title": "Model-X F1", "kind": "text", "checks": checks()})
        if "accepted_indexes" in props:
            return reply(
                info,
                {
                    "accepted_indexes": [0],
                    "relevant_indexes": [0],
                    "checks": checks("mismatch"),
                    "coverage": "complete",
                },
            )
        assert "question" not in payload(messages)
        assert payload(messages)["extraction_scope"]["evidence_need"]["constraints"]
        return reply(info, {"values": [observation()], "complete": True})

    active.model = FunctionModel(model)
    assert not await active.execute(ResearchDecision(action="extract", support_ids=["E1.S1"]))
    assert active.state.extractions[-1].accepted_indexes == [0]
    assert active.state.need_extractions[-1].relevant_indexes == []
    assert active.state.need_extractions[-1].coverage == "unresolved"
    assert not active.state.facts and len(active.deps.ledger.blocks) == 1


@pytest.mark.asyncio
async def test_partial_scope_bound_fact_survives_and_unrelated_facts_are_not_projected():
    active = active_session()

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "kind" in props:
            return reply(info, {"title": "Model-X F1", "kind": "text", "checks": checks()})
        if "accepted_indexes" in props:
            return reply(
                info,
                {
                    "accepted_indexes": [0],
                    "relevant_indexes": [0],
                    "checks": checks(),
                    "coverage": "partial",
                },
            )
        return reply(info, {"values": [observation()], "complete": False})

    active.model = FunctionModel(model)
    assert await active.execute(ResearchDecision(action="extract", support_ids=["E1.S1"]))
    need = next(iter(active.state.evidence_needs.values()))
    assert need.status == "partial" and len(need.fact_ids) == 1
    fact = active.state.facts[need.fact_ids[0]]
    active.state.facts["unrelated"] = fact.model_copy(update={"id": "unrelated"})
    packet = active.context(finalizing=True)
    assert [f["id"] for f in packet["facts"]] == need.fact_ids
    assert packet["facts_projection"]["stored"] == 2
    assert packet["evidence_requirements"][0]["status"] == "partial"
    # Research closes, but successful fact and its need binding remain for finalization.
    active.state.research_stop = "TOKEN_RESERVE"
    active.model = FunctionModel(lambda m, i: reply(i, answer("Model-X F1 Small gold 12")))
    result, _ = await finalize_research(active)
    assert not result.abstain and active.state.evidence_needs[need.id].fact_ids == need.fact_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["foreign_page", "foreign_element", "version_changed"])
async def test_source_selection_cannot_invent_location_or_use_changed_pdf(tmp_path, invalid):
    active = pdf_session(tmp_path)

    def model(messages, info):
        return reply(
            info,
            {
                "page": 99 if invalid == "foreign_page" else 2,
                "element_id": "P2.I99" if invalid == "foreign_element" else "",
                "title": "Model-X F1",
                "kind": "chart",
                "checks": checks(),
            },
        )

    active.model = FunctionModel(model)
    if invalid == "version_changed":
        (tmp_path / "manual.pdf").write_bytes(b"changed")
    with pytest.raises(Exception):
        await active.execute(
            ResearchDecision(action="extract", support_ids=["E1.S1"], modality="image")
        )
    assert not active.state.extractions and not active.state.facts


def pdf_session(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 40), "Table 1: Model-X recall Large gold")
        page = pdf.new_page()
        page.insert_text((30, 40), "Figure 2: Model-X F1 Small gold 12")
        page.insert_text((30, 100), "Figure 3: Unrelated recall graph")
        pdf.save(path)
    active = active_session()
    active.deps.visual_answers = True
    active.deps.render_page = PdfPages(str(tmp_path))
    block = active.deps.ledger.blocks[0]
    block.payload.update(
        source_id="manual_pdf",
        page_number=1,
        page_end=2,
        document_version=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    return active


@pytest.mark.asyncio
async def test_page_range_resolves_actual_page_before_narrow_image_extraction(tmp_path):
    active = pdf_session(tmp_path)
    roles = []

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        prompt = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        image_count = len(prompt.content) - 1
        if "kind" in props:
            roles.append("selector")
            assert image_count == 2
            assert [p["physical_page"] for p in data["candidate_pages_in_image_order"]] == [1, 2]
            return reply(
                info,
                {
                    "page": 2,
                    "title": "Figure 2: Model-X F1 Small gold",
                    "kind": "chart",
                    "checks": checks(),
                },
            )
        assert image_count == 1  # other candidate page never reaches extractor/checker
        if "accepted_indexes" in props:
            roles.append("checker")
            return reply(
                info,
                {
                    "accepted_indexes": [0, 1],
                    "relevant_indexes": [0],
                    "checks": checks(),
                    "coverage": "complete",
                },
            )
        roles.append("extractor")
        assert data["extraction_scope"]["selected_object"]["page"] == 2
        return reply(
            info,
            {
                "values": [observation(), observation("Unrelated", "99", "Unrelated 99")],
                "complete": True,
            },
        )

    active.model = FunctionModel(model)
    assert await active.execute(
        ResearchDecision(action="extract", support_ids=["E1.S1"], page=1, modality="image")
    )
    assert roles == ["selector", "extractor", "checker"]
    assert "Figure 2: Model-X F1 Small gold 12" in active.state.source_selections[-1].source_context
    assert "Figure 3" not in active.state.source_selections[-1].source_context
    assert (
        "Source captions from the version-checked PDF"
        in active.deps.ledger.blocks[-1].payload["text"]
    )
    assert "Figure 2: Model-X F1 Small gold 12" in active.deps.ledger.blocks[-1].payload["text"]
    assert len(active.state.facts) == 1
    assert next(iter(active.state.facts.values())).evidence.page == 2
    assert len(active.state.extractions[-1].accepted_indexes) == 2
    assert active.state.need_extractions[-1].relevant_indexes == [0]
    assert next(iter(active.state.evidence_needs.values())).status == "satisfied"
    packet = active.context()
    assert "Unrelated 99" not in json.dumps(packet["facts"])
    assert "Unrelated 99" not in active.deps.ledger.blocks[-1].payload["text"]

    from app.llm.research_state import CalculationInput, ComputationPlan

    active.deps.derived_answers = True
    fact = next(iter(active.state.facts.values()))
    active.calculate_plan(
        ComputationPlan(
            expression="a", inputs=[CalculationInput(name="a", fact_id=fact.id)], decimals=1
        )
    )
    assert (
        "Source captions from the version-checked PDF"
        in active.deps.ledger.blocks[-1].payload["text"]
    )
    assert "Figure 2: Model-X F1 Small gold 12" in active.deps.ledger.blocks[-1].payload["text"]


@pytest.mark.asyncio
async def test_need_planner_only_sees_question_and_reuses_same_shared_request_budget():
    calls = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        data = payload(messages)
        if "evidence_needs" in props:
            calls.append("planner")
            assert data == {"question": QUESTION}
            return reply(info, {"evidence_needs": [spec().model_dump()]})
        calls.append("reader")
        assert data["evidence_requirements"][0]["spec"]["constraints"]
        return reply(info, {"action": "answer", "answer": answer("Model-X F1 Small gold 12")})

    result = await run_adaptive_agent(
        FunctionModel(model),
        deps("Model-X F1 Small gold 12", question=QUESTION),
        evidence_needs_enabled=True,
        max_requests=3,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"]
    assert calls == ["planner", "reader"] and result.telemetry["requests"] == 2


@pytest.mark.asyncio
async def test_planner_failure_preserves_independent_validated_finalization():
    from tests.test_adaptive import scope

    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "evidence_needs" in props:
            roles.append("planner")
            bad = spec().model_dump()
            bad["constraints"][0]["question_quote"] = "invented phrase"
            return reply(info, {"evidence_needs": [bad]})
        if "checks" in props:
            roles.append("scope")
            return scope(info, quote="Model-X F1 Small gold 12")
        if "action" in props:
            roles.append("reader")
            return reply(info, {"action": "answer", "answer": answer("Model-X F1 Small gold 12")})
        roles.append("finalizer")
        return reply(info, answer("Model-X F1 Small gold 12"))

    dependencies = deps(
        "Model-X F1 Small gold 12", question=QUESTION, scope_validation_enabled=True
    )
    active_state = session(dependencies).state
    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=active_state, evidence_needs_enabled=True
    )
    assert not json.loads(result.raw)["abstain"]
    assert roles == ["planner", "reader", "scope"]
    assert active_state.need_planning == "failed" and not active_state.evidence_needs
    assert result.scope_receipt.accepts(QUESTION, result.raw, dependencies.ledger.units)


@pytest.mark.asyncio
async def test_needs_trace_records_locations_and_coverage_without_source_content(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app.llm import agent_observability as obs
    from app.shared.trace_client import SAFE_ATTRIBUTES

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("needs-test")
    monkeypatch.setattr(obs, "get_tracer", lambda _: tracer)
    active = active_session()
    active.model = FunctionModel(
        lambda m, i: reply(
            i,
            {
                "kind": "chart",
                "title": "PRIVATE GRAPH TITLE",
                "checks": checks("mismatch"),
            },
        )
    )
    try:
        with tracer.start_as_current_span("request") as root:
            await active.execute(ResearchDecision(action="extract", support_ids=["E1.S1"]))
        spans = exporter.get_finished_spans()
        selected = next(s for s in spans if s.name == "evidence.need.select")
        assert selected.context.trace_id == root.get_span_context().trace_id
        assert selected.attributes["research.source_match"] is False
        assert selected.attributes["research.need_ids"]
        attrs = json.dumps([dict(s.attributes) for s in spans])
        assert "PRIVATE GRAPH TITLE" not in attrs and QUESTION not in attrs
        assert "research.need_ids" in SAFE_ATTRIBUTES
    finally:
        provider.shutdown()


@pytest.mark.asyncio
async def test_need_aware_final_scope_uses_original_release_receipt():
    from tests.test_adaptive_fast_path import line_scope

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        data = payload(messages)
        if "evidence_needs" in props:
            return reply(info, {"evidence_needs": [spec().model_dump()]})
        if "checks" in props:
            assert data["evidence_requirements"][0]["constraints"]
            return line_scope(messages, info, support="E1.S1", quote="Model-X F1 Small gold 12")
        return reply(
            info,
            {
                "answer": {
                    "answer_parts": [{"text": "Model-X F1 Small gold 12", "support_ids": ["E1.S1"]}]
                }
            },
        )

    dependencies = deps(
        "Model-X F1 Small gold 12", question=QUESTION, scope_validation_enabled=True
    )
    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, fast_path=True, evidence_needs_enabled=True
    )
    assert result.failure_code is None
    assert result.scope_receipt.accepts(QUESTION, result.raw, dependencies.ledger.units)
    assert result.telemetry["requests"] == 3


def test_irrelevant_indexes_cannot_be_promoted_without_accuracy_acceptance():
    active = active_session()
    from app.llm.research_state import EvidenceRef, NeedSourceRecord

    need_id = next(iter(active.state.evidence_needs))
    record = NeedSourceRecord(
        id="S1",
        need_id=need_id,
        evidence=EvidenceRef(support_id="E1.S1", source_id="manual"),
        candidate_pages=[],
        match=SourceMatch(checks=checks()),
        accepted=True,
    )
    checked = ScopedExtractionCheck(
        accepted_indexes=[], relevant_indexes=[0], checks=checks(), coverage="complete"
    )
    with pytest.raises(ValueError, match="INVALID_RELEVANCE_CHECK"):
        active.need_workflow.record_extraction(
            record, 0, checked, DataExtraction(values=[observation()]), []
        )
    assert not active.state.need_extractions


@pytest.mark.asyncio
async def test_correct_page_selection_is_reused_and_unchecked_draft_survives_checker_error(
    tmp_path,
):
    active = pdf_session(tmp_path)
    calls = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "kind" in props:
            calls.append("selector")
            return reply(
                info,
                {"page": 2, "title": "Model-X F1 Small gold", "kind": "chart", "checks": checks()},
            )
        if "accepted_indexes" in props:
            calls.append("checker")
            return reply(
                info,
                {
                    "accepted_indexes": [99],
                    "relevant_indexes": [],
                    "checks": checks(),
                    "coverage": "unresolved",
                },
            )
        calls.append("extractor")
        value = observation()
        value.pop("status")  # Omission is normalized, not source-verified.
        return reply(info, {"values": [value], "complete": True})

    active.model = FunctionModel(model)
    with pytest.raises(ValueError, match="INVALID_EXTRACTION_CHECK"):
        await active.execute(
            ResearchDecision(action="extract", support_ids=["E1.S1"], modality="image", page=1)
        )
    assert calls == ["selector", "extractor", "checker"]
    assert active.state.extractions[0].extraction.values[0].value == "12"
    assert not active.state.extractions[0].accepted_indexes and not active.state.facts
    record, images = await active.need_workflow.select(
        ResearchDecision(action="extract", support_ids=["E1.S1"], modality="image", page=2),
        active.units()["E1.S1"],
    )
    assert record.accepted and record.evidence.page == 2 and len(images) == 1
    assert calls == ["selector", "extractor", "checker"]


@pytest.mark.asyncio
async def test_application_sorts_rounds_and_finalizes_without_another_reader_call():
    from app.llm.research_state import NumericPresentation

    question = QUESTION + " Sort descending with one decimal place."
    text = "\n".join(
        f"Model-X F1 Small gold {c} {v}"
        for c, v in [("A", "12.35"), ("B", "10.23"), ("C", "11.46")]
    )
    dependencies = deps(text, question=question, derived_answers=True)
    active = session(dependencies)
    need = active.state.add_need(
        spec().model_copy(
            update={
                "presentation": NumericPresentation(
                    decimals=1,
                    order="descending",
                    question_quote="Sort descending with one decimal place",
                )
            }
        )
    )
    active.state.need_planning = "ready"
    roles = []

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "action" in props:
            roles.append("reader")
            return reply(info, {"action": "extract", "need_id": need.id, "support_ids": ["E1.S1"]})
        if "kind" in props:
            roles.append("selector")
            return reply(
                info, {"title": "Model-X F1 Small gold", "kind": "text", "checks": checks()}
            )
        if "accepted_indexes" in props:
            roles.append("checker")
            return reply(
                info,
                {
                    "accepted_indexes": [0, 1, 2],
                    "relevant_indexes": [0, 1, 2],
                    "coverage": "complete",
                    "checks": checks(),
                },
            )
        if "values" in props:
            roles.append("extractor")
            return reply(
                info,
                {
                    "values": [
                        {
                            "category": c,
                            "series": "Model-X",
                            "period": "Small",
                            "unit": "F1",
                            "qualifiers": ["gold"],
                            "value": v,
                            "witness": f"Model-X F1 Small gold {c} {v}",
                        }
                        for c, v in [("A", "12.35"), ("B", "10.23"), ("C", "11.46")]
                    ],
                    "complete": True,
                },
            )
        roles.append("finalizer")
        result = data["presentations"][0]
        assert [v["value"] for v in result["values"]] == ["12.4", "11.5", "10.2"]
        assert len(data["computations"]) == 3
        assert data["research_stop"] == "EVIDENCE_NEEDS_SATISFIED"
        supports = [s for v in result["values"] for s in v["support_ids"]]
        return reply(
            info,
            {
                "abstain": False,
                "answer_parts": [{"text": "12.4, 11.5, 10.2", "support_ids": supports}],
            },
        )

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        evidence_needs_enabled=True,
        state=active.state,
        max_requests=8,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"]
    assert roles == ["reader", "selector", "extractor", "checker", "finalizer"]
    assert len(active.state.computations) == 3
    assert len(active.state.presentations[need.id].values) == 3


def test_output_format_is_question_bound_and_not_a_source_unit_constraint():
    from app.llm.research_state import NumericPresentation

    active = active_session()
    bad = spec().model_copy(
        update={"presentation": NumericPresentation(decimals=1, question_quote="one decimal place")}
    )
    with pytest.raises(ValueError, match="NEED_NOT_GROUNDED"):
        active.state.add_need(bad)


def test_observation_binding_is_required_per_value_even_when_page_scope_matches():
    from app.llm.research_state import EvidenceRef, NeedSourceRecord

    active = active_session()
    need_id = next(iter(active.state.evidence_needs))
    selection = NeedSourceRecord(
        id="S1",
        need_id=need_id,
        evidence=EvidenceRef(support_id="E1.S1", source_id="manual"),
        candidate_pages=[],
        match=SourceMatch(checks=checks()),
        accepted=True,
    )
    extraction = DataExtraction(
        values=[observation(), observation("Other", "99", "Other 99")], complete=True
    )
    check = ScopedExtractionCheck(
        accepted_indexes=[0, 1],
        relevant_indexes=[0, 1],
        checks=checks(),
        coverage="complete",
        bindings=[
            {"observation_index": 0, "verdicts": ["supported"] * 3},
            {"observation_index": 1, "verdicts": ["supported", "supported", "mismatch"]},
        ],
    )
    record = active.need_workflow.record_extraction(selection, 0, check, extraction, [0, 1])
    assert record.relevant_indexes == [0] and record.coverage == "partial"
    no_binding = check.model_copy(update={"bindings": []})
    record = active.need_workflow.record_extraction(selection, 0, no_binding, extraction, [0, 1])
    assert not record.relevant_indexes and record.coverage == "unresolved"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["ellipsis", "presentation", "schema"])
async def test_invalid_plan_is_not_repaired_and_normal_search_continues(invalid):
    from tests.test_adaptive import block

    calls, queries = [], []

    async def search(query):
        queries.append(query)
        return [block("Model-X F1 Small gold 12", id="found")]

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "evidence_needs" in props:
            calls.append("planner")
            bad = spec().model_dump()
            if invalid == "ellipsis":
                bad["constraints"][0]["question_quote"] = "Model-X ... gold"
            elif invalid == "presentation":
                bad["presentation"] = {"decimals": 3, "question_quote": "round ... places"}
            else:
                bad["operation"] = "invented operation"
            return reply(info, {"evidence_needs": [spec().model_dump(), bad]})
        calls.append("reader")
        assert data["question"] == QUESTION
        assert data["need_planning"] == "failed"
        assert not data["evidence_requirements"]
        assert "extract" not in data["allowed_actions"]
        if not queries:
            return reply(info, {"action": "search", "query": "Model-X F1 Small gold"})
        unit = next(e for e in data["evidence"] if e["text"] == "Model-X F1 Small gold 12")
        return reply(
            info,
            {
                "action": "answer",
                "answer": answer("Model-X F1 Small gold 12", unit["support_unit_id"]),
            },
        )

    dependencies = deps("Unrelated source", question=QUESTION, retrieve=search)
    state = session(dependencies).state
    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        evidence_needs_enabled=True,
    )
    assert calls == ["planner", "reader", "reader"]
    assert queries == ["Model-X F1 Small gold"]
    assert state.need_planning == "failed" and not state.evidence_needs
    assert state.research_stop is None and state.finalization == "answered"
    assert result.telemetry["requests"] == 3 and result.telemetry["observability"]["retries"] == 0
    assert "12" in result.raw and not json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_failed_plan_blocks_extraction_at_execution_not_only_in_prompt():
    active = active_session()
    active.state.need_planning = "failed"
    with pytest.raises(ValueError, match="ACTION_UNAVAILABLE"):
        await active.execute(ResearchDecision(action="extract", support_ids=["E1.S1"]))
    assert not active.state.extractions and active.usage.requests == 0


@pytest.mark.asyncio
async def test_invalid_plan_preserves_reserved_finalizer_when_no_research_request_remains():
    calls = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "evidence_needs" in props:
            calls.append("planner")
            bad = spec().model_dump()
            bad["constraints"][0]["question_quote"] = "Model-X ... gold"
            return reply(info, {"evidence_needs": [bad]})
        assert "action" not in props
        calls.append("finalizer")
        return reply(info, answer("Model-X F1 Small gold 12"))

    dependencies = deps("Model-X F1 Small gold 12", question=QUESTION)
    state = session(dependencies).state
    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        evidence_needs_enabled=True,
        max_requests=2,
    )
    assert calls == ["planner", "finalizer"]
    assert state.research_stop == "REQUEST_RESERVE" and state.finalization == "answered"
    assert result.telemetry["requests"] == 2


@pytest.mark.asyncio
async def test_single_field_search_uses_application_bindings_not_shotgun_query():
    queries = []

    async def retrieve(query):
        queries.append(query)
        return []

    active = active_session()
    active.deps.retrieve = retrieve
    await active.execute(
        ResearchDecision(
            action="search",
            target_field="F1",
            query="F1 and unrelated metric and many other things",
        )
    )
    assert queries == ["Model-X F1"]
