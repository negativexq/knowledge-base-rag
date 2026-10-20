"""Native input repairs keep operations, source locators and requested image authority."""

import hashlib
from dataclasses import replace

import fitz
import pytest
from pydantic import ValidationError

from app.llm.quantities import collect, execute, resolve_draft
from app.llm.quantity_contracts import bind_collection, collection_contract, operation_fields
from app.llm.quantity_review import grounded_issues, merge_repair
from app.llm.quantity_sources import visual_page_supports
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityDraft,
    QuantityImageBinding,
    QuantityIssue,
    QuantityRecord,
    QuantitySource,
)
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import block
from tests.test_quantities import active_session, arithmetic


def parent_record(draft=None, *, modality="text", bindings=()):
    return QuantityRecord(
        id="original",
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual_pdf",
        document_version="v1",
        pages=[1, 2],
        modality=modality,
        draft=draft or arithmetic(),
        image_bindings=list(bindings),
        assessments=[
            QuantityAssessment(
                inputs="unknown",
                coverage="complete",
                operation="supported",
                issues=[
                    QuantityIssue(
                        kind="unreadable",
                        target="operand",
                        index=1,
                        description="Recheck second input against original source.",
                        source_ranges=[dict(support_id="E1.S1", start_line=2, end_line=2)],
                    )
                ],
            )
        ],
    )


def image_binding(key="image_1", page=1, **changes):
    return QuantityImageBinding(
        image_id=key,
        physical_page=page,
        source_id="manual_pdf",
        document_version=changes.get("document_version", "v1"),
    )


def wire_operand(name, value, image="image_1"):
    return dict(
        name=name,
        label=name.upper(),
        value=value,
        unit="items",
        number_format="canonical",
        image_ids=[image],
        witness=f"{name.upper()} {value}",
    )


def test_native_input_patch_cannot_regenerate_operation_and_reorders_by_owned_names():
    original = arithmetic().model_copy(
        update={"interpretation": "Keep this exact application-owned meaning.", "decimals": 2}
    )
    bindings = [image_binding()]
    schema = collection_contract("arithmetic", bindings, ["E1.S1"], repair_operation=original)
    assert set(schema.model_fields) == {"mode", "complete", "operands"}
    raw = dict(
        mode="arithmetic",
        complete=True,
        operands=[wire_operand("b", "7"), wire_operand("a", "999")],
    )
    replacement = bind_collection(
        schema.model_validate(raw), bindings, {}, repair_operation=original
    )
    assert replacement.model_dump(include=operation_fields()) == original.model_dump(
        include=operation_fields()
    )
    assert [o.name for o in replacement.operands] == ["a", "b"]
    merged = merge_repair(parent_record(original), replacement)
    assert merged.operands[0] is original.operands[0]
    assert execute(merged)[0] == ["10.00"]
    for key, value in {
        "expression": "a * b",
        "interpretation": "Same meaning with different wording.",
        "result_unit": "other",
        "decimals": 0,
        "choices": [],
        "result": "100",
    }.items():
        with pytest.raises(ValidationError):
            schema.model_validate(raw | {key: value})
    with pytest.raises(ValidationError):
        schema.model_validate(raw | {"operands": [wire_operand("unknown", "7")]})
    for operands in [[wire_operand("a", "3")], [wire_operand("a", "3")] * 2]:
        with pytest.raises(ValueError, match="IDENTITIES_CHANGED"):
            bind_collection(
                schema.model_validate(raw | {"operands": operands}),
                bindings,
                {},
                repair_operation=original,
            )


def test_read_patch_preserves_reviewed_output_scale_and_sign():
    original = QuantityDraft(
        mode="read",
        complete=True,
        operands=[
            dict(
                name="a",
                label="A",
                value="(8)",
                number_format="canonical",
                value_status="readable",
                source_scale="1000",
                unit="thousand items",
                output_unit="items",
                output_scale="1",
                sign_convention="magnitude",
            )
        ],
    )
    binding = image_binding()
    schema = collection_contract("read", [binding], ["E1.S1"], repair_operation=original)
    raw = dict(
        mode="read",
        complete=True,
        operands=[wire_operand("a", "(8)") | dict(unit="thousand items", source_scale="1000")],
    )
    result = bind_collection(schema.model_validate(raw), [binding], {}, repair_operation=original)
    assert execute(result)[0] == ["8000"]
    with pytest.raises(ValidationError):
        schema.model_validate(
            raw | {"operands": [raw["operands"][0] | {"sign_convention": "signed"}]}
        )


def pdf_session(tmp_path, text="A 6\nB 9", *, page=1, page_end=2, page_texts=("A 6", "B 4")):
    path = tmp_path / "manual.pdf"
    with fitz.open() as document:
        for content in page_texts:
            document.new_page().insert_text((30, 30), content)
        document.save(path)
    active, need = active_session(text, visual_answers=True, render_page=PdfPages(str(tmp_path)))
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active.deps.ledger.blocks[0].payload.update(
        source_id="manual_pdf", document_version=version, page_number=page, page_end=page_end
    )
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    return active, need, version


@pytest.mark.asyncio
async def test_native_text_to_image_repair_retains_literal_operand_and_rechecks_full_result(
    tmp_path,
):
    active, need, _ = pdf_session(tmp_path)
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        repair = calls.count("quantity_selector") == 2
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                support_ids=["E1.S1"],
                pages=[1, 2],
                modality="image" if repair else "text",
            )
        if role == "quantity_collector":
            if not repair:
                return output_type.model_validate(
                    dict(
                        mode="arithmetic",
                        complete=True,
                        operands=[
                            dict(
                                name=name,
                                label=label,
                                value=value,
                                unit="items",
                                source_ranges=[
                                    dict(support_id="E1.S1", start_line=line, end_line=line)
                                ],
                            )
                            for name, label, value, line in [
                                ("a", "A", "6", 1),
                                ("b", "B", "9", 2),
                            ]
                        ],
                        expression="a + b",
                        decimals=0,
                        result_unit="items",
                        interpretation="Total items.",
                    )
                )
            assert images and len(images) == 2 and data["operation_owned_by_application"]
            assert "expression" not in output_type.model_fields
            return output_type.model_validate(
                dict(
                    mode="arithmetic",
                    complete=True,
                    operands=[wire_operand("a", "999"), wire_operand("b", "4", "image_2")],
                )
            )
        if not repair:
            return QuantityAssessment(
                inputs="unknown",
                coverage="complete",
                operation="supported",
                issues=parent_record().assessments[0].issues,
            )
        assert data["draft"]["operands"][0]["value"] == "6"
        assert data["draft"]["operands"][0]["page"] is None
        assert data["draft"]["operands"][1]["page"] == 2
        assert data["retained_sources"] == [
            dict(support_id="E1.S1", segments=[dict(line=1, content="A 6\n")])
        ]
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    answer = await collect(active, need)
    assert answer.answer_parts[0].text == "10 items (Total items.)"
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"] * 2
    parent, child = list(active.state.quantities.values())
    assert child.parent_id == parent.id and child.execution_status == "completed"
    assert parent.draft.operands[1].value == "9"
    assert child.draft.operands[0].source_ranges == parent.draft.operands[0].source_ranges
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert restored.quantities[child.id].draft.operands[0].page is None


@pytest.mark.asyncio
async def test_requested_context_image_reaches_collector_and_checker_with_same_snapshot(tmp_path):
    active, need, version = pdf_session(tmp_path, "B 4", page=2)
    active.deps.ledger.add(
        [
            block(
                "A 6",
                id="comparison",
                source_id="manual_pdf",
                document_version=version,
                page_number=1,
                page_end=1,
            )
        ]
    )
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                support_ids=["E1.S1"],
                context_support_ids=["E2.S1"],
                pages=[1, 2],
                modality="image",
            )
        assert data["physical_pages"] == [1, 2] and images and len(images) == 2
        assert data["source_images"][0]["evidence_role"] == "context"
        assert data["source_images"][0]["support_ids"] == ["E2.S1"]
        if role == "quantity_collector":
            return output_type.model_validate(
                dict(
                    mode="arithmetic",
                    complete=True,
                    operands=[wire_operand("a", "6"), wire_operand("b", "4", "image_2")],
                    expression="a + b",
                    decimals=0,
                    result_unit="items",
                    interpretation="Total items.",
                )
            )
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    assert result.answer_parts[0].text == "10 items (Total items.)"
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
    record = next(iter(active.state.quantities.values()))
    assert record.support_ids == ["E1.S1"] and record.context_support_ids == ["E2.S1"]
    assert [b.physical_page for b in record.image_bindings] == [1, 2]


@pytest.mark.asyncio
async def test_lookup_keeps_comparison_image_and_returns_linked_value_not_largest_output(tmp_path):
    active, need, version = pdf_session(
        tmp_path,
        "East 20 items\nWest 30 items",
        page=2,
        page_texts=("Scores: East 6 points, West 4 points", "Values: East 20 items, West 30 items"),
    )
    active.deps.ledger.add(
        [
            block(
                "Scores: East 6 points, West 4 points",
                id="scores",
                source_id="manual_pdf",
                document_version=version,
                page_number=1,
                page_end=1,
            )
        ]
    )
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                operation_kind="lookup",
                support_ids=["E1.S1"],
                context_support_ids=["E2.S1"],
                pages=[1, 2],
                modality="image",
            )
        assert len(images) == 2 and data["physical_pages"] == [1, 2]
        if role == "quantity_collector":
            operands = []
            for name, value, image, unit, series in [
                ("east_score", "6", "image_1", "points", "score"),
                ("west_score", "4", "image_1", "points", "score"),
                ("east_value", "20", "image_2", "items", "value"),
                ("west_value", "30", "image_2", "items", "value"),
            ]:
                operands.append(
                    wire_operand(name, value, image)
                    | dict(
                        unit=unit,
                        population=name.split("_")[0],
                        series=series,
                        period="",
                    )
                )
            return output_type.model_validate(
                dict(
                    mode="lookup",
                    complete=True,
                    operands=operands,
                    select_mode="maximum",
                    choices=[
                        dict(
                            label=label,
                            score_expression=f"{key}_score",
                            value_operand=f"{key}_value",
                        )
                        for key, label in [("east", "East"), ("west", "West")]
                    ],
                )
            )
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert record.values == ["20"] and record.execution_status == "completed"
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]


@pytest.mark.parametrize(
    "defect", ["version", "hidden", "unauthorized", "missing", "duplicate", "limit"]
)
def test_visual_context_page_authority_fails_closed(defect):
    active, _ = active_session()
    original = next(iter(active.units().values()))
    inputs = [replace(original, page_number=2, page_end=2)]
    context = [replace(original, support_unit_id="E2.S1", page_number=1, page_end=1)]
    selection = QuantitySource(available=True, pages=[1, 2], modality="image")
    if defect == "version":
        context[0] = replace(context[0], document_version="foreign-snapshot")
    elif defect in {"hidden", "unauthorized"}:
        context[0] = replace(
            context[0], **{("model_visible" if defect == "hidden" else "authorized"): False}
        )
    elif defect == "missing":
        selection = selection.model_copy(update={"pages": [2, 3]})
    elif defect == "duplicate":
        selection = selection.model_copy(update={"pages": [1, 1]})
    else:
        selection = selection.model_copy(update={"pages": [1, 2, 3, 4]})
    with pytest.raises(ValueError):
        visual_page_supports(selection, inputs, context)


def test_retained_image_handles_rebind_by_identity_and_page_not_ordinal():
    old_bindings = [image_binding(), image_binding("image_2", 2)]
    original = arithmetic().model_copy(
        update={
            "operands": [
                arithmetic().operands[0].model_copy(update={"page": 1, "image_ids": ["image_1"]}),
                arithmetic().operands[1].model_copy(update={"page": 2, "image_ids": ["image_2"]}),
            ]
        }
    )
    parent = parent_record(original, modality="image", bindings=old_bindings)
    current = [image_binding(page=2), image_binding("image_2", 1)]
    replacement = original.model_copy(
        update={
            "operands": [
                original.operands[0],
                original.operands[1].model_copy(update={"image_ids": ["image_1"]}),
            ]
        }
    )
    merged = merge_repair(parent, replacement)
    resolved = resolve_draft(merged, {}, image_bindings=current, parent=parent)
    assert resolved.operands[0].image_ids == ["image_2"]
    assert resolved.operands[1].image_ids == ["image_1"]
    assert original.operands[0].image_ids == ["image_1"]
    for invalid in [
        current[:1],
        [b.model_copy(update={"document_version": "foreign"}) for b in current],
    ]:
        with pytest.raises(ValueError, match="RETAINED_IMAGE_UNAVAILABLE"):
            resolve_draft(merged, {}, image_bindings=invalid, parent=parent)


def test_image_repair_cannot_launder_unknown_text_reference():
    draft = QuantityDraft(
        mode="read",
        complete=True,
        operands=[
            dict(
                name="a",
                label="A",
                value="6",
                page=1,
                witness="6",
                source_ranges=[dict(support_id="E99.S1", start_line=1, end_line=1)],
            )
        ],
    )
    with pytest.raises(ValueError, match="REFERENCE_OUTSIDE_SOURCE"):
        resolve_draft(draft, {"E1.S1": "6"}, image_bindings=[image_binding()])


def test_retained_text_objection_is_still_grounded_during_image_review():
    issue = parent_record().assessments[0].issues[0]
    review = QuantityAssessment(
        inputs="unknown", coverage="complete", operation="supported", issues=[issue]
    )
    valid, errors = grounded_issues(review, arithmetic(), {"E1.S1": "A 3\nB 7"}, [1], "Total?")
    assert valid == [issue] and not errors
    _, errors = grounded_issues(review, arithmetic(), {}, [1], "Total?")
    assert "ISSUE_SOURCE_NOT_GROUNDED" in errors
