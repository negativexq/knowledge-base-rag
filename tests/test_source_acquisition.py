"""Locate-to-open handoffs use existing tools, source authority and shared budgets."""

import hashlib
import json
from types import SimpleNamespace

import fitz
import pytest
from pydantic_ai.models.function import FunctionModel

from app.evidence.documents import DocumentResult
from app.llm.adaptive import run_adaptive_agent
from app.llm.quantity_state import QuantityAssessment, QuantitySource
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint, ResearchState, TaskSpec
from app.llm.source_acquisition import open_quantity_pages
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import answer, block, payload, reply
from tests.test_quantities import active_session, arithmetic


def native_session(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((30, 30), "North 3")
        doc.new_page().insert_text((30, 30), "South 7")
        doc.save(path)
    active, need = active_session(
        "Annual summary", render_page=PdfPages(str(tmp_path)), visual_answers=True
    )
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active.deps.ledger.blocks[0].payload.update(
        source_id="manual_pdf", document_version=version, page_number=1, page_end=2
    )
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    calls = []

    async def read(request):
        calls.append(request)
        return DocumentResult(
            [
                block(
                    "North 3" if request.page == 1 else "South 7",
                    f"page-{request.page}",
                    source_id="manual_pdf",
                    document_version=version,
                    page_number=request.page,
                    page_end=request.page,
                )
            ],
            [],
        )

    active.deps.documents = SimpleNamespace(read=read)
    return active, need, calls


@pytest.mark.asyncio
async def test_heading_seeds_open_selected_pages_and_reuse_version_bound_receipts(tmp_path):
    active, _, calls = native_session(tmp_path)
    source = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1, 2])
    opened = await open_quantity_pages(active, source)
    text = "\n".join(active.units()[key].text for key in opened.support_ids)
    assert "North 3" in text and "South 7" in text
    assert len(calls) == 2 and active.deps.observations.tool_calls == 2
    assert len(active.state.page_acquisitions) == 2
    assert await open_quantity_pages(active, source) == opened
    assert len(calls) == 2
    assert ResearchState.model_validate_json(active.state.model_dump_json()).page_acquisitions


@pytest.mark.asyncio
async def test_opened_page_inputs_reach_collector_and_compute_without_another_selector(tmp_path):
    from app.llm.quantities import collect

    active, need, calls = native_session(tmp_path)
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"], pages=[1, 2])
        if role == "quantity_collector":
            text = json.dumps(data["source"])
            assert "North 3" in text and "South 7" in text and not images
            return arithmetic()
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need, repairs_left=0)
    assert result.answer_parts[0].text == "10"
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    assert len(calls) == 2
    assert next(iter(active.state.quantities.values())).check.accepted


@pytest.mark.asyncio
async def test_page_opening_preserves_original_when_budget_empty_or_reader_empty(tmp_path):
    active, _, calls = native_session(tmp_path)
    source = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1])
    active.deps.observations.tool_calls = active.policy.max_tool_attempts
    assert await open_quantity_pages(active, source) == source
    assert not calls
    active.deps.observations.tool_calls = 0

    async def empty(request):
        return DocumentResult([], [], has_more=True, scan_limited=True)

    active.deps.documents = SimpleNamespace(read=empty)
    assert await open_quantity_pages(active, source) == source
    receipt = active.state.page_acquisitions[-1]
    assert not receipt.support_ids and receipt.has_more and receipt.scan_limited


@pytest.mark.asyncio
async def test_opening_cannot_cross_page_or_version_authority(tmp_path):
    active, _, calls = native_session(tmp_path)
    with pytest.raises(ValueError, match="QUANTITY_PAGE_OUTSIDE_SOURCE"):
        await open_quantity_pages(
            active, QuantitySource(available=True, support_ids=["E1.S1"], pages=[3])
        )
    assert not calls
    before = set(active.units())

    async def foreign(request):
        return DocumentResult(
            [
                block(
                    "Counterfeit income 99",
                    "foreign",
                    source_id="manual_pdf",
                    document_version="other",
                    page_number=1,
                )
            ],
            [],
        )

    active.deps.documents = SimpleNamespace(read=foreign)
    source = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1])
    assert await open_quantity_pages(active, source) == source
    assert set(active.units()) == before


@pytest.mark.asyncio
async def test_visual_count_and_non_pdf_paths_do_not_add_page_reads(tmp_path):
    active, _, calls = native_session(tmp_path)
    for updates in [{"operation_kind": "count"}, {"operation_kind": "list"}, {"modality": "image"}]:
        source = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1], **updates)
        assert await open_quantity_pages(active, source) == source
    active.deps.render_page = None
    source = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1])
    assert await open_quantity_pages(active, source) == source
    assert not calls


@pytest.mark.asyncio
async def test_visual_need_dispatches_location_match_and_checked_extraction_before_finalization(
    tmp_path,
):
    active, _, _ = native_session(tmp_path)
    question = "Which of North and South covers more area?"
    dependencies = active.deps
    dependencies.question = question
    state = ResearchState(task=TaskSpec(question=question), need_planning="ready")
    state.add_need(
        EvidenceNeedSpec(
            description="Map comparison",
            operation="compare",
            acquisition="image",
            constraints=[
                NeedConstraint(
                    dimension="entity", value="North and South", question_quote="North and South"
                ),
                NeedConstraint(
                    dimension="metric", value="covers more area", question_quote="covers more area"
                ),
            ],
        )
    )
    roles = []

    def model(messages, info):
        data = payload(messages)
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "available" in props:
            roles.append("locate")
            assert "page_catalog" in data
            return reply(
                info,
                {
                    "available": True,
                    "support_id": data["candidates"][0]["support_id"],
                    "physical_page": 1,
                },
            )
        if "kind" in props and "checks" in props:
            roles.append("match")
            return reply(
                info,
                {
                    "page": 1,
                    "title": "Map",
                    "kind": "chart",
                    "checks": [{"constraint_index": i, "verdict": "supported"} for i in range(2)],
                },
            )
        if "values" in props:
            roles.append("extract")
            assert data["extraction_scope"]["evidence_need"]["acquisition"] == "image"
            return reply(
                info,
                {
                    "complete": True,
                    "values": [
                        {
                            "category": "North",
                            "value": (
                                "The mapped region labelled North occupies a visibly "
                                "smaller bounded area than the region labelled South, "
                                "as shown by their outlines in the source map."
                            ),
                            "witness": "North is visibly smaller than South",
                            "status": "readable",
                        }
                    ],
                },
            )
        if "relevant_indexes" in props:
            roles.append("check")
            return reply(
                info,
                {
                    "accepted_indexes": [0],
                    "relevant_indexes": [0],
                    "coverage": "complete",
                    "checks": [{"constraint_index": i, "verdict": "supported"} for i in range(2)],
                    "bindings": [{"observation_index": 0, "verdicts": ["supported", "supported"]}],
                },
            )
        roles.append("finalize")
        assert "missing" not in props and "action" not in props
        ref = next(iter(state.facts.values())).evidence.support_id
        return reply(info, answer("South", ref))

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        evidence_needs_enabled=True,
        fast_path=True,
        max_requests=10,
    )
    assert result.failure_code is None and not json.loads(result.raw)["abstain"], state.needs
    assert roles == ["locate", "match", "extract", "check", "finalize"], (
        roles,
        state.needs,
        state.research_stop,
        state.evidence_needs,
    )
    assert state.research_stop == "EVIDENCE_NEEDS_SATISFIED"
    assert len(state.extractions) == 1 and len(state.facts) == 1
    assert result.telemetry["tool_calls"] == 1


@pytest.mark.asyncio
async def test_visual_locator_cannot_inspect_an_unpresented_or_out_of_range_page(tmp_path):
    from app.llm.source_acquisition import VisualSourceLocation, locate_visual

    active, need, _ = native_session(tmp_path)

    async def call(role, output_type, instructions, data, *, research, images=None):
        assert role == "source_selector" and not images
        return VisualSourceLocation(available=True, support_id="E1.S1", physical_page=3)

    active.call = call
    with pytest.raises(ValueError, match="VISUAL_PAGE_OUTSIDE_SOURCE"):
        await locate_visual(active, need)
    assert not active.state.extractions and not active.state.facts


@pytest.mark.asyncio
async def test_unlocated_visual_need_continues_without_certifying_an_answer(tmp_path):
    active, _, _ = native_session(tmp_path)
    dependencies = active.deps
    question = "Which region is larger?"
    dependencies.question = question
    state = ResearchState(task=TaskSpec(question=question), need_planning="ready")
    state.add_need(
        EvidenceNeedSpec(
            description="Visual extent",
            operation="compare",
            acquisition="image",
            constraints=[
                NeedConstraint(dimension="metric", value="larger", question_quote="larger")
            ],
        )
    )
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "available" in props:
            roles.append("locate")
            return reply(info, {"available": False, "support_id": "", "physical_page": None})
        if "missing" in props:
            roles.append("fast")
            return reply(info, {"answer": None, "missing": ["Map not located"]})
        if "action" in props:
            roles.append("research")
            return reply(info, {"action": "stop"})
        roles.append("finalize")
        return reply(info, {"abstain": True, "answer_parts": []})

    result = await run_adaptive_agent(
        FunctionModel(model),
        dependencies,
        state=state,
        evidence_needs_enabled=True,
        fast_path=True,
        max_requests=10,
    )
    assert json.loads(result.raw)["abstain"] and not state.facts
    assert roles == ["locate", "fast", "research", "finalize"]


def test_qualitative_value_capacity_does_not_relax_numeric_execution_limits():
    from app.llm.research_state import ObservedValue, decimal_value

    text = "The source identifies a qualitative relationship between the two regions. " * 3
    observation = ObservedValue(
        category="Relationship", value=text, witness="Original map", status="readable"
    )
    assert observation.value == text and len(text) > 100
    with pytest.raises(ValueError):
        decimal_value(observation.value)
    with pytest.raises(ValueError):
        decimal_value("9" * 101)
