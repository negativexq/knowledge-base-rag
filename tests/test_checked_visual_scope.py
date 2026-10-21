"""Semantic review receives the same checked original page, not only conflicting OCR."""

import hashlib

import fitz
import pytest

from app.llm.adaptive import ResearchDecision
from app.llm.agentic import AgentAnswer, AgentAnswerPart
from app.llm.quantities import collect
from app.llm.quantity_scope import (
    checked_scope_images,
    checked_visual_fact_sources,
    semantic_scope_projection,
)
from app.llm.quantity_state import QuantityAssessment, QuantitySource
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint
from app.llm.scope_validation import scope_payload
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import deps, session


async def visual_result(tmp_path, *, reject_scope=False, list_mode=False):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        if list_mode:
            page.draw_rect(fitz.Rect(25, 35, 180, 80), fill=(0.7, 0.85, 1))
        page.insert_text((30, 30), "Company | Tweets\nGermanwings | 24\nLufthansa | 12")
        pdf.save(path)
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    question = "How many more Tweets are attributed to Germanwings than Lufthansa?"
    if list_mode:
        question = "List labels with blue backgrounds."
    active = session(
        deps(
            "Company | Tweets\nGermanwings | 24\nLufthansa | 42",
            question=question,
            derived_answers=True,
            scope_validation_enabled=True,
            visual_answers=True,
            render_page=PdfPages(str(tmp_path)),
        )
    )
    active.deps.ledger.blocks[0].payload.update(source_id="manual_pdf", document_version=version)
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    need = active.state.add_need(
        EvidenceNeedSpec(
            description="Difference in Tweets",
            operation="lookup" if list_mode else "calculate",
            constraints=[
                NeedConstraint(
                    dimension="condition", value="blue", question_quote="blue backgrounds"
                )
                if list_mode
                else NeedConstraint(dimension="metric", value="Tweets", question_quote="Tweets")
            ],
        )
    )
    active.state.need_planning = "ready"
    calls, checked_images = [], []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                support_ids=["E1.S1"],
                pages=[1],
                modality="image",
                operation_kind="list" if list_mode else "arithmetic",
            )
        if role == "quantity_collector":
            if list_mode:
                return output_type.model_validate(
                    dict(
                        mode="list",
                        complete=True,
                        list_order="source",
                        list_unique=True,
                        items=[
                            dict(
                                position=1,
                                text="Germanwings",
                                image_ids=["image_1"],
                                witness="Germanwings has a blue background",
                            )
                        ],
                    )
                )
            return output_type.model_validate(
                dict(
                    mode="arithmetic",
                    complete=True,
                    expression="a - b",
                    decimals=0,
                    result_unit="Tweets",
                    interpretation="Difference in attributed Tweets",
                    operands=[
                        dict(
                            name=name,
                            label=label,
                            value=value,
                            unit="Tweets",
                            witness=f"{label} {value}",
                            image_ids=["image_1"],
                        )
                        for name, label, value in [
                            ("a", "Germanwings", "24"),
                            ("b", "Lufthansa", "12"),
                        ]
                    ],
                )
            )
        if role == "quantity_checker":
            checked_images.extend(images)
            return QuantityAssessment(
                inputs="supported",
                coverage="complete",
                operation="supported",
                entity_identity="supported",
                supported_operand_indexes=[0, 1],
            )
        assert role == "scope_validator" and research is False
        assert images == checked_images and len(images) == 1
        assert images[0].startswith(b"\x89PNG")
        original = data["source_images"][0]
        assert (original["source_id"], original["document_version"], original["physical_page"]) == (
            "manual_pdf",
            version,
            1,
        )
        assert (
            data["verified_operations"][0]["input_authority"]
            == "independently_checked_original_images"
        )
        # Conflicting parser text remains visible for scope relationships; it is
        # neither rewritten to 12 nor silently removed from the release payload.
        assert "42" in str(data["claims"][0]["cited_evidence"])
        if list_mode:
            assert "Germanwings" in data["claims"][0]["claim"]["text"]
            assert data["verified_operations"][0]["operation"] == "list"
            assert original["claim_indexes"] == [0]
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="mismatch" if reject_scope else "supported",
                        reason="ENTITY_MISMATCH" if reject_scope else "NONE",
                        witnesses=[]
                        if reject_scope
                        else [dict(support_id="E1.S1", start_line=1, end_line=3)],
                    )
                ],
                objections=[
                    dict(
                        claim_index=0,
                        description="Wrong source entity",
                        question_start=1,
                        question_end=1,
                        source_locations=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                    )
                ]
                if reject_scope
                else [],
                requirement_bindings=[
                    dict(
                        requirement_index=0,
                        verdict="supported",
                        binding_basis="explicit",
                        claim_indexes=[0],
                        witnesses=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                        image_witnesses=[
                            dict(
                                image_id=original["image_id"],
                                observation="The Germanwings label is on a blue box",
                            )
                        ]
                        if list_mode
                        else [],
                    )
                ],
            )
        )

    active.call = call
    answer = await collect(active, need.id)
    if not list_mode:
        assert answer.answer_parts[0].calculation.result == "12"
    return active, answer, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("reject_scope", [False, True])
async def test_scope_reuses_checked_images_but_still_checks_semantic_binding(
    tmp_path, reject_scope
):
    active, answer, calls = await visual_result(tmp_path, reject_scope=reject_scope)
    if reject_scope:
        with pytest.raises(ValueError, match="SCOPE_ENTITY_MISMATCH"):
            await active.verify(answer, allow_repair=False)
    else:
        result, receipt = await active.verify(answer)
        assert receipt.accepts(active.deps.question, result.raw_answer(), active.deps.ledger.units)
    assert calls == [
        "quantity_selector",
        "quantity_collector",
        "quantity_checker",
        "scope_validator",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"document_version": "different"}, {"physical_page": 2}])
async def test_checked_image_authority_cannot_move_to_a_different_version_or_page(tmp_path, change):
    active, _, calls = await visual_result(tmp_path)
    record = next(iter(active.state.quantities.values()))
    binding = record.image_bindings[0].model_copy(update=change)
    active.state.quantities[record.id] = record.model_copy(update={"image_bindings": [binding]})
    with pytest.raises(ValueError, match="CHECKED_IMAGE_BINDING_STALE"):
        await checked_scope_images(active, [record.id])
    assert "scope_validator" not in calls


@pytest.mark.asyncio
async def test_repeated_checked_record_reuses_one_original_page(tmp_path):
    active, _, _ = await visual_result(tmp_path)
    record = next(iter(active.state.quantities.values()))
    images, bindings = await checked_scope_images(active, [record.id, record.id])
    assert len(images) == len(bindings) == 1


@pytest.mark.asyncio
async def test_text_scope_requires_no_images_or_new_model_call():
    active = session(deps())
    assert await checked_scope_images(active, []) == ([], [])
    assert active.usage.requests == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("reject_scope", [False, True])
async def test_visual_list_keeps_answer_and_receives_original_page(tmp_path, reject_scope):
    active, answer, calls = await visual_result(tmp_path, list_mode=True, reject_scope=reject_scope)
    if reject_scope:
        with pytest.raises(ValueError, match="SCOPE_ENTITY_MISMATCH"):
            await active.verify(answer, allow_repair=False)
    else:
        result, receipt = await active.verify(answer)
        assert receipt.accepts(active.deps.question, result.raw_answer(), active.deps.ledger.units)
    assert calls.count("scope_validator") == 1
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_changed_or_unchecked_list_does_not_gain_original_page_authority(tmp_path):
    active, answer, _ = await visual_result(tmp_path, list_mode=True)
    record = next(iter(active.state.quantities.values()))
    payload = scope_payload(active.deps.question, answer.raw_answer(), active.deps.ledger.units)
    assert semantic_scope_projection(payload, [record])[1] == [record.id]
    changed = answer.model_copy(
        update={
            "answer_parts": [answer.answer_parts[0].model_copy(update={"text": '["Other label"]'})]
        }
    )
    changed_payload = scope_payload(
        active.deps.question, changed.raw_answer(), active.deps.ledger.units
    )
    assert semantic_scope_projection(changed_payload, [record])[1] == []
    unchecked = record.model_copy(update={"check": None})
    assert semantic_scope_projection(payload, [unchecked])[1] == []


@pytest.mark.asyncio
async def test_general_image_extraction_keeps_original_provenance_in_scope(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.draw_rect(fitz.Rect(25, 35, 180, 80), fill=(0.7, 0.85, 1))
        page.insert_text((30, 60), "Valve")
        pdf.save(path)
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active = session(
        deps(
            "Valve",
            question="Which label has a blue background?",
            scope_validation_enabled=True,
            visual_answers=True,
            render_page=PdfPages(str(tmp_path)),
        )
    )
    active.deps.ledger.blocks[0].payload.update(source_id="manual_pdf", document_version=version)
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    checked, calls = [], []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "extractor":
            return output_type.model_validate(
                dict(
                    values=[
                        dict(
                            category="Valve",
                            value="Valve is in a blue box",
                            witness="Valve",
                        )
                    ],
                    complete=True,
                )
            )
        if role == "extraction_checker":
            checked.extend(images)
            return output_type.model_validate(dict(accepted_indexes=[0]))
        assert role == "scope_validator"
        assert images == checked and len(images) == 1
        assert data["source_images"][0]["claim_indexes"] == [0]
        assert data["source_images"][0]["physical_page"] == 1
        assert len(data["claims"][0]["claim"]["support_ids"]) == 2
        assert data["generated_support_ids"] == [
            next(iter(active.state.facts.values())).evidence.support_id
        ]
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[
                            dict(support_id="E1.S1", start_line=1, end_line=1),
                        ],
                    )
                ],
                requirement_bindings=[
                    dict(
                        requirement_index=0,
                        verdict="supported",
                        binding_basis="explicit",
                        claim_indexes=[0],
                        image_witnesses=[
                            dict(image_id="scope_image_1", observation="Valve is in the blue box")
                        ],
                    )
                ],
            )
        )

    active.call = call
    assert await active.execute(
        ResearchDecision(
            action="extract",
            support_ids=["E1.S1"],
            modality="image",
            page=1,
        )
    )
    active.state.add_need(
        EvidenceNeedSpec(
            description="Label color",
            operation="lookup",
            constraints=[
                NeedConstraint(
                    dimension="condition", value="blue", question_quote="blue background"
                ),
            ],
        )
    )
    active.state.need_planning = "ready"
    fact = next(iter(active.state.facts.values()))
    answer = AgentAnswer(
        abstain=False,
        answer_parts=[AgentAnswerPart(text="Valve", support_ids=[fact.evidence.support_id])]
    )
    _, receipt = await active.verify(answer)
    assert receipt is not None and not receipt.failure_codes
    assert calls == ["extractor", "extraction_checker", "scope_validator"]
    active.state.extractions[0] = active.state.extractions[0].model_copy(
        update={"accepted_indexes": []}
    )
    assert checked_visual_fact_sources(active) == {}
