"""Original-page authority and relationship evidence survive the quantitative path."""

import hashlib

import fitz
import pytest

from app.evidence.pdf_structure import PdfStructure
from app.llm.agentic import AgentAnswer, AgentAnswerPart, AgentCalculation
from app.llm.quantities import collect
from app.llm.quantity_sources import inspect_pages
from app.llm.quantity_state import QuantityAssessment, QuantitySource
from app.llm.visual_answer import PdfPages, PdfSnapshot
from tests.test_adaptive import block
from tests.test_quantities import active_session, arithmetic


def scan_session(tmp_path):
    with fitz.open() as native:
        native.new_page().insert_text((30, 30), "North 3\nSouth 7")
        image = native[0].get_pixmap().tobytes("png")
    path = tmp_path / "manual.pdf"
    with fitz.open() as scanned:
        page = scanned.new_page()
        page.insert_image(page.rect, stream=image)
        scanned.save(path)
    active, need = active_session(
        "North 3\nSouth 9", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    active.deps.ledger.blocks[0].payload.update(
        source_id="manual_pdf", document_version=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    return active, need, path


def test_original_page_quality_distinguishes_native_from_image_only(tmp_path):
    active, _, path = scan_session(tmp_path)
    scan = PdfStructure(PdfSnapshot("manual_pdf", path.read_bytes()))
    q = scan.page_quality(1)
    assert q["native_text_chars"] == 0 and q["requires_image"]
    with fitz.open() as native:
        native.new_page().insert_text((30, 30), "North 3\nSouth 7")
        q = PdfStructure(PdfSnapshot("native", native.tobytes())).page_quality(1)
    assert q["native_text_chars"] > 0 and not q["requires_image"]


@pytest.mark.asyncio
async def test_raster_numeric_source_uses_images_without_an_extra_model_stage(tmp_path):
    active, need, _ = scan_session(tmp_path)
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"], pages=[1])
        assert images and len(images) == 1
        assert data["source_quality"][0]["requires_image"]
        if role == "quantity_collector":
            assert data["source"] == "Read original images in page order."
            draft = arithmetic()
            return draft.model_copy(
                update={"operands": [o.model_copy(update={"page": 1}) for o in draft.operands]}
            )
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    assert result.answer_parts[0].text == "10"
    assert not active.deps.validation(result).failure_codes
    record = next(iter(active.state.quantities.values()))
    assert record.modality == "image" and record.draft.operands[1].value == "7"
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    assert active.state.quantity_source_inspections[0].pages[0].requires_image
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert restored.quantity_source_inspections[0].pages[0].native_text_chars == 0


@pytest.mark.asyncio
async def test_fast_model_math_cannot_bypass_original_scan_verification(tmp_path):
    active, _, _ = scan_session(tmp_path)
    answer = AgentAnswer(
        abstain=False,
        answer_parts=[
            AgentAnswerPart(
                text="12",
                support_ids=["E1.S1"],
                calculation=AgentCalculation(expression="3 + 9", result="12"),
            )
        ],
    )
    with pytest.raises(ValueError, match="REQUIRES_IMAGE_CHECK"):
        await active.verify(answer)


@pytest.mark.asyncio
async def test_context_sources_travel_to_final_scope_without_becoming_numeric_inputs():
    active, need = active_session()
    active.deps.ledger.add([block("Tracked measures identify North and South.", id="definition")])

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(
                available=True, support_ids=["E1.S1"], context_support_ids=["E2.S1"]
            )
        assert data["context_sources"][0]["support_id"] == "E2.S1"
        if role == "quantity_collector":
            return arithmetic()
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert record.support_ids == ["E1.S1"] and record.context_support_ids == ["E2.S1"]
    assert "E2.S1" in result.answer_parts[0].support_ids
    assert [o.value for o in record.draft.operands] == ["3", "7"]
    # Removing context from a later finalizer candidate cannot lose the owned provenance.
    minimal = result.model_copy(
        update={
            "answer_parts": [
                result.answer_parts[0].model_copy(update={"support_ids": record.proof_support_ids})
            ]
        }
    )
    verified, _ = await active.verify(minimal)
    assert "E2.S1" in verified.answer_parts[0].support_ids


@pytest.mark.asyncio
async def test_context_ids_must_be_authorized_and_presented_to_selector():
    active, need = active_session()

    async def call(role, output_type, instructions, data, *, research, images=None):
        assert role == "quantity_selector"
        return QuantitySource(available=True, support_ids=["E1.S1"], context_support_ids=["E99.S1"])

    active.call = call
    with pytest.raises(ValueError):
        await collect(active, need)


@pytest.mark.asyncio
async def test_native_quality_receipt_reused_and_page_bounds_enforced(tmp_path):
    active, _, _ = scan_session(tmp_path)
    first = await inspect_pages(active, ["E1.S1"], [1])
    second = await inspect_pages(active, ["E1.S1"], [1])
    assert first == second and len(active.state.quantity_source_inspections) == 1
    with pytest.raises(ValueError, match="OUTSIDE_SOURCE"):
        await inspect_pages(active, ["E1.S1"], [2])


@pytest.mark.asyncio
async def test_authorized_context_pages_are_not_rendered_as_numeric_pages():
    active, need = active_session()
    active.deps.ledger.add(
        [block("Tracked measures identify North and South.", id="definition", page_number=2)]
    )

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                support_ids=["E1.S1"],
                context_support_ids=["E2.S1"],
                pages=[1, 2],
            )
        assert data["physical_pages"] == [1]
        if role == "quantity_collector":
            return arithmetic()
        assert "count_mode" not in data["draft"]
        assert "groups" not in data["draft"]
        assert data["draft"]["expression"] == "a + b"
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert record.pages == [1] and record.context_support_ids == ["E2.S1"]
    assert result.answer_parts[0].text == "10"
    assert "count_mode" not in active.context(finalizing=True)["checked_quantities"][0]["draft"]


def test_semantic_projection_keeps_count_operations_and_removes_inapplicable_arithmetic_fields():
    from app.llm.quantities import semantic_draft
    from tests.test_quantities import enumeration

    arithmetic_payload = semantic_draft(arithmetic())
    assert "count_mode" not in arithmetic_payload and "groups" not in arithmetic_payload
    assert arithmetic_payload["expression"] == "a + b"
    counting_payload = semantic_draft(enumeration().model_copy(update={"count_mode": "distinct"}))
    assert counting_payload["count_mode"] == "distinct" and counting_payload["groups"]
    assert not {"operands", "expression", "decimals"} & counting_payload.keys()
