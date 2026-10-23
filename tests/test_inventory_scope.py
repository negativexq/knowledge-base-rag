"""Source membership, inventory closure and question restrictions need distinct evidence."""

import hashlib
import json
from dataclasses import replace

import fitz
import pytest

from app.llm.inventory_evidence import extend_inventory_window, inventory_issues
from app.llm.quantities import collect, execute
from app.llm.quantity_state import QuantityAssessment, QuantityDraft, QuantitySource
from app.llm.scope_requirements import RequiredScopeJudgment, range_conflicts, validate_requirements
from app.llm.scope_validation import scope_payload
from app.llm.visual_answer import PdfPages
from tests.test_quantities import active_session


def line(key, text, *, heading=False, caption=False, y=0.3):
    return dict(
        id=key, text=text, heading=heading, caption=caption, size=12, bbox=[0.1, y, 0.8, y + 0.02]
    )


def context(*lines):
    return dict(page_count=3, pages=[dict(page=1, limited=False, lines=list(lines))])


def inventory(items, **extra):
    return QuantityDraft(
        mode="count",
        complete=True,
        count_mode="total",
        groups=[
            dict(
                label="Alpha team",
                complete=True,
                object_anchor="P1.L1",
                closure_anchor="P1.L3",
                closure_basis="bounded_object",
                items=[
                    dict(text=text, position=i, page=1, witness=text)
                    for i, text in enumerate(items, 1)
                ],
                **extra,
            )
        ],
    )


def test_sibling_membership_cannot_be_approved_by_a_complete_boolean():
    source = context(
        line("P1.L1", "Alpha team", heading=True),
        line("P1.L2", "Ann"),
        line("P1.L3", "Beta team", heading=True),
        line("P1.L4", "Ben"),
    )
    assert not inventory_issues(inventory(["Ann"]), source, "How many in Alpha team?")
    wrong = inventory(["Ann", "Ben"])
    assert any(
        "MEMBER_OUTSIDE_OBJECT" in i.description
        for i in inventory_issues(wrong, source, "Alpha team?")
    )
    # Re-labelling the closure does not move a sibling into this named object.
    wrong.groups[0] = wrong.groups[0].model_copy(update={"closure_basis": "declared_inventory"})
    assert any(
        "MEMBER_OUTSIDE_OBJECT" in i.description
        for i in inventory_issues(wrong, source, "Alpha team?")
    )


def test_native_closure_metadata_is_a_hint_not_an_independent_release_gate():
    source = context(
        line("P1.L1", "Alpha team", heading=True), line("P1.L2", "Ann"), line("P1.L3", "1")
    )
    # A missing or nonstructural handle neither proves closure nor contradicts
    # the original-image check. That independent receipt remains mandatory.
    for anchor in ["", "P1.L3", "document_end"]:
        draft = inventory(["Ann"])
        draft.groups[0] = draft.groups[0].model_copy(update={"closure_anchor": anchor})
        assert not inventory_issues(draft, source, "All?")
    draft.groups[0] = draft.groups[0].model_copy(update={"object_anchor": ""})
    assert not inventory_issues(draft, source, "All?")


def test_bold_numbered_rows_are_not_sibling_categories():
    source = context(
        line("P1.L1", "Quality levels", heading=True),
        line("P1.L2", "1", heading=True),
        line("P1.L3", "2", heading=True),
        line("P1.L4", "3", heading=True),
    )
    assert not inventory_issues(inventory(["1", "2", "3"]), source, "How many levels?")


def test_declared_summary_still_needs_every_observed_numbered_item():
    source = context(
        line("P1.L1", "ALL ASSIGNMENTS", heading=True),
        line("P1.L2", "Test #1"),
        line("P1.L3", "TERM TWO", heading=True),
        line("P1.L4", "Test #2"),
        line("P1.L5", "END", heading=True),
    )
    draft = inventory(["Test #1"])
    draft.groups[0] = draft.groups[0].model_copy(
        update={"closure_basis": "declared_inventory", "closure_anchor": "P1.L5"}
    )
    assert any(
        "SOURCE_ITEMS_OMITTED" in i.description
        for i in inventory_issues(draft, source, "All tests?")
    )
    draft.groups[0].items.append(
        draft.groups[0].items[0].model_copy(update={"text": "Test #2", "position": 2})
    )
    assert not inventory_issues(draft, source, "All tests?")


def test_bottom_object_check_and_grounded_zero_count():
    source = context(
        line("P1.L1", "Figure 1: Top", caption=True, y=0.2),
        line("P1.L3", "Figure 2: Bottom", caption=True, y=0.8),
    )
    draft = inventory(["Shown example"])
    assert any(
        "LOCATION_MISMATCH" in i.description
        for i in inventory_issues(draft, source, "Figure at the bottom?")
    )
    draft.groups[0] = draft.groups[0].model_copy(update={"object_anchor": "P1.L3", "items": []})
    assert not inventory_issues(draft, source, "Figure at the bottom?")
    assert execute(draft)[0] == ["0"]


def test_forward_window_is_bounded_to_visible_same_snapshot_authority():
    active, _ = active_session()
    unit = active.units()["E1.S1"]
    units = {
        "E1.S1": unit,
        "next": replace(unit, support_unit_id="next", page_number=2, page_end=5),
    }
    selected = QuantitySource(
        operation_kind="count", support_ids=["E1.S1"], pages=[1], available=True
    )
    assert extend_inventory_window(selected, units).pages == [1, 2, 3]
    two_pages = selected.model_copy(update={"pages": [1, 2], "support_ids": ["E1.S1", "next"]})
    assert extend_inventory_window(two_pages, units).pages == [1, 2, 3]
    noncontiguous = two_pages.model_copy(update={"pages": [1, 3]})
    assert extend_inventory_window(noncontiguous, units) == noncontiguous
    for changes in [
        dict(model_visible=False),
        dict(authorized=False),
        dict(document_version="other"),
    ]:
        units["next"] = replace(units["next"], **changes)
        assert extend_inventory_window(selected, units).pages == [1]
        units["next"] = replace(unit, support_unit_id="next", page_number=2, page_end=5)


def binding_payload(source="Westhaven is part of North District."):
    active, _ = active_session(text=source)
    raw = json.dumps(
        dict(answer_parts=[dict(text="North District", support_ids=["E1.S1"])], abstain=False)
    )
    return scope_payload("Which district includes Westhaven?", raw, active.deps.ledger.units)


def judgment(**changes):
    entry = dict(
        requirement_index=0,
        verdict="supported",
        binding_basis="source_relationship",
        claim_indexes=[0],
        witnesses=[dict(support_id="E1.S1", start_line=1, end_line=1)],
    )
    entry.update(changes)
    return RequiredScopeJudgment(
        checks=[dict(claim_index=0, verdict="supported", reason="NONE")],
        requirement_bindings=[entry],
    )


def test_source_relationship_needs_a_positive_entity_bridge_not_generated_proof_text():
    reqs = [dict(dimension="entity", question_quote="Westhaven")]
    assert not validate_requirements(binding_payload(), reqs, judgment(), set())
    # An absent relationship is a semantic unknown/mismatch, not a failed
    # capitalization match. Neither verdict can release a positive answer.
    for verdict in ("unknown", "mismatch"):
        assert "SCOPE_REQUIREMENT_UNRESOLVED" in validate_requirements(
            binding_payload("North District"), reqs, judgment(verdict=verdict), set()
        )
    assert "SCOPE_NAMED_ENTITY_RELATION_UNGROUNDED" in validate_requirements(
        binding_payload(), reqs, judgment(), {"E1.S1"}
    )
    for changes in [dict(witnesses=[]), dict(claim_indexes=[2]), dict(verdict="unknown")]:
        assert validate_requirements(binding_payload(), reqs, judgment(**changes), set())
    empty = judgment().model_copy(update={"requirement_bindings": []})
    assert validate_requirements(binding_payload(), reqs, empty, set()) == [
        "SCOPE_REQUIREMENT_COVERAGE_INVALID"
    ]


def test_leading_named_target_must_satisfy_question_range_without_constraining_computed_numbers():
    def claims(text):
        return [dict(claim=dict(text=text))]

    assert range_conflicts("Which channel from channels 5-9?", claims("Channel 2, with capture."))
    assert not range_conflicts("Which channel from channels 5-9?", claims("Channel 7."))
    assert not range_conflicts("How many people ages 10-13?", claims("4 people."))


def test_condition_cannot_use_generated_transcription_as_independent_evidence():
    requirements = [dict(dimension="condition", question_quote="blue background")]
    payload = binding_payload("The label is on a blue background.")
    assert not validate_requirements(payload, requirements, judgment(), set())
    assert "SCOPE_CONDITION_SOURCE_UNGROUNDED" in validate_requirements(
        payload, requirements, judgment(), {"E1.S1"}
    )
    images = [dict(image_id="scope_image_1", claim_indexes=[0])]
    visual = judgment(
        witnesses=[],
        image_witnesses=[
            dict(image_id="scope_image_1", observation="The label is inside the blue box")
        ],
    )
    assert not validate_requirements(payload, requirements, visual, {"E1.S1"}, images)
    for invalid in [
        [],
        [dict(image_id="scope_image_2", claim_indexes=[0])],
        [dict(image_id="scope_image_1", claim_indexes=[1])],
    ]:
        assert "SCOPE_REQUIREMENT_IMAGE_INVALID" in validate_requirements(
            payload, requirements, visual, {"E1.S1"}, invalid
        )


@pytest.mark.parametrize("case", [
    "valid_image", "no_image", "unknown_image", "wrong_image_claim", "unknown_support",
    "unknown_verdict",
])
def test_original_image_authority_is_independent_of_optional_ocr_locator(case):
    requirements = [dict(dimension="condition", question_quote="blue background")]
    payload = binding_payload("An OCR label without color information.")
    proposed = judgment(
        witnesses=[dict(
            support_id="E99.S1" if case == "unknown_support" else "E1.S1",
            start_line=88, end_line=88,
        )],
        image_witnesses=[] if case == "no_image" else [dict(
            image_id="scope_image_1", observation="The label is inside the blue background."
        )],
        verdict="unknown" if case == "unknown_verdict" else "supported",
    )
    images = [dict(
        image_id="scope_image_2" if case == "unknown_image" else "scope_image_1",
        claim_indexes=[1] if case == "wrong_image_claim" else [0],
    )]
    diagnostics = {}
    errors = validate_requirements(
        payload, requirements, proposed, {"E1.S1"}, images, diagnostics=diagnostics
    )
    if case == "valid_image":
        assert not errors and diagnostics == {"ignored_optional_text_witnesses": 1}
    else:
        assert errors
        assert not diagnostics


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_modality", ["image", "text"])
async def test_native_omission_repairs_in_same_view_without_another_selector_call(
    tmp_path, initial_modality
):
    path = tmp_path / "manual.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 60), "ALL ASSIGNMENTS", fontname="hebo", fontsize=14)
        page.insert_text((40, 90), "Test #1\nTest #2")
        page.insert_text((40, 180), "NEXT SECTION", fontname="hebo", fontsize=14)
        doc.save(path)
    active, need = active_session(
        "ALL ASSIGNMENTS\nTest #1\nTest #2\nNEXT SECTION"
        if initial_modality == "image"
        else "ALL ASSIGNMENTS\nTest #1\nNEXT SECTION",
        visual_answers=True,
        render_page=PdfPages(str(tmp_path)),
    )
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active.deps.ledger.blocks[0].payload.update(source_id="manual_pdf", document_version=version)
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    seen = []

    async def call(role, output_type, instructions, data, **kwargs):
        seen.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                operation_kind="count",
                available=True,
                support_ids=["E1.S1"],
                pages=[1],
                modality=initial_modality,
            )
        if role == "quantity_checker":
            return QuantityAssessment(
                inputs="supported",
                coverage="complete",
                operation="supported",
                entity_identity="supported",
            )
        native = data["native_inventory"]["pages"][0]["lines"]
        first = next(entry["id"] for entry in native if entry["text"] == "ALL ASSIGNMENTS")
        last = next(entry["id"] for entry in native if entry["text"] == "NEXT SECTION")
        n = 1 if seen.count("quantity_collector") == 1 else 2
        result = dict(
            mode="count",
            complete=True,
            groups=[
                dict(
                    label="All tests",
                    complete=True,
                    object_anchor=first,
                    closure_anchor=last,
                    closure_basis="declared_inventory",
                    boundary_witness="The summary is delimited by NEXT SECTION.",
                    items=[
                        dict(
                            position=i,
                            text=f"Test #{i}",
                            image_ids=["image_1"],
                            witness=f"Test #{i}",
                        )
                        for i in range(1, n + 1)
                    ],
                )
            ],
        )
        if "count_mode" in output_type.model_fields:
            result["count_mode"] = "total"
        return output_type.model_validate(result)

    active.call = call
    result = await collect(active, need)
    assert result and result.answer_parts[0].text == "2"
    assert seen == [
        "quantity_selector",
        "quantity_collector",
        "quantity_checker",
        "quantity_collector",
        "quantity_checker",
    ]
    records = list(active.state.quantities.values())
    assert records[0].inventory_errors == ["INVENTORY_SOURCE_ITEMS_OMITTED"]
    assert records[-1].values == ["2"]
    assert records[0].draft.groups[0].items[0].text == "Test #1"
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert restored.quantities[records[-1].id].inventory_context


def test_operation_only_correction_never_changes_source_items_or_approves_missing_coverage():
    from app.llm.quantity_review import correct_count_operation

    draft = inventory(["Ann", "Ben"]).model_copy(update={"count_mode": "per_group"})
    review = QuantityAssessment(
        inputs="supported",
        coverage="complete",
        operation="mismatch",
        alternatives=["total"],
        issues=[
            dict(target="operation", kind="operation", description="One combined count requested")
        ],
    )
    corrected, checked = correct_count_operation(draft, review)
    assert corrected.count_mode == "total" and corrected.groups is draft.groups
    assert checked.operation == "supported" and not checked.issues
    assert draft.count_mode == "per_group" and review.operation == "mismatch"
    for changes in [
        dict(inputs="unknown"),
        dict(coverage="incomplete"),
        dict(alternatives=["total", "distinct"]),
    ]:
        untouched = review.model_copy(update=changes)
        assert correct_count_operation(draft, untouched) == (draft, untouched)


def test_an_operation_objection_without_a_named_count_mode_is_not_rewritten_as_total():
    # Row 730: the table has no Boeing row. The checker objected that counting
    # the empty list turns an unreported value into zero and named no count
    # mode. An empty set is a subset of {"total"}, so this objection was read
    # as "count the total" and cleared, and 0 was released.
    from app.llm.quantity_review import correct_count_operation

    draft = inventory(["Ann", "Ben"]).model_copy(update={"count_mode": "per_group"})
    empty = draft.model_copy(update={"groups": [draft.groups[0].model_copy(update={"items": []})]})
    review = QuantityAssessment(
        inputs="supported",
        coverage="complete",
        operation="mismatch",
        alternatives=[],
        issues=[
            dict(
                target="operation",
                kind="operation",
                description="No Boeing row; counting the empty list would report zero",
            )
        ],
    )
    for current in (draft, empty):
        assert correct_count_operation(current, review) == (current, review)


@pytest.mark.asyncio
async def test_an_empty_count_the_checker_rejects_is_never_released_as_zero():
    from tests.test_quantities import enumeration

    active, need = active_session("Benefits until Risks on page 2\nFast\nReliable\nAffordable")
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(operation_kind="count", available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            draft = enumeration()
            return draft.model_copy(
                update={
                    "count_mode": "per_group",
                    "groups": [draft.groups[0].model_copy(update={"items": []})],
                }
            )
        return QuantityAssessment(
            inputs="supported",
            coverage="complete",
            operation="mismatch",
            alternatives=[],
            issues=[
                dict(
                    target="operation",
                    kind="operation",
                    description="The requested entity is not listed; zero is not reported",
                    source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                )
            ],
        )

    active.call = call
    result = await collect(active, need)
    assert not (result and not result.abstain and result.answer_parts)
    record = next(iter(active.state.quantities.values()))
    assert record.values != ["0"] and record.execution_status != "completed"
    assert record.assessments[-1].operation == "mismatch"


@pytest.mark.asyncio
async def test_count_operation_patch_finishes_without_another_collection_call():
    from tests.test_quantities import enumeration

    active, need = active_session("Benefits until Risks on page 2\nFast\nReliable\nAffordable")
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(operation_kind="count", available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return enumeration().model_copy(update={"count_mode": "per_group"})
        return QuantityAssessment(
            inputs="supported",
            coverage="complete",
            operation="mismatch",
            alternatives=["total"],
            issues=[
                dict(
                    target="operation",
                    kind="operation",
                    description="One total requested",
                    source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                )
            ],
        )

    active.call = call
    result = await collect(active, need)
    assert result and not result.abstain
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
    record = next(iter(active.state.quantities.values()))
    assert record.execution_status == "completed" and record.check.accepted
    assert record.assessments[0].operation == "mismatch"
    assert record.assessments[-1].operation == "supported"


@pytest.mark.asyncio
async def test_checked_count_projection_does_not_revalidate_missing_parser_rows():
    from app.llm.quantities import candidate
    from app.llm.quantity_scope import semantic_scope_projection
    from tests.test_quantities import enumeration, fake_calls

    active, need = active_session("Benefits until Risks on page 2\nFast\nReliable\nAffordable")
    fake_calls(active, draft=enumeration())
    answer = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    payload = scope_payload(
        active.state.task.question, answer.raw_answer(), active.deps.ledger.units
    )
    view, ids = semantic_scope_projection(payload, [record])
    assert ids == [record.id]
    operation = view["verified_operations"][0]
    assert operation["operation"] == "count"
    assert operation["checked_inputs"][0]["items"][0]["text"] == "Fast"
    assert "counts" in payload["claims"][0]["claim"]
    assert "counts" not in view["claims"][0]["claim"]
    wrong = record.model_copy(update={"values": ["999"]})
    assert semantic_scope_projection(payload, [wrong]) == (payload, [])
    unreviewed = record.model_copy(update={"check": None})
    assert semantic_scope_projection(payload, [unreviewed]) == (payload, [])
    assert candidate(record).raw_answer() == answer.raw_answer()


def test_catalog_can_surface_question_terms_in_middle_of_a_page(tmp_path):
    from app.evidence.pdf_structure import PdfStructure
    from app.llm.visual_answer import PdfSnapshot

    path = tmp_path / "catalog.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 60), "Header one\nHeader two\nHeader three")
        page.insert_text((40, 300), "Test #9: middle-of-page assignment")
        page.insert_text((40, 650), "Footer one\nFooter two\nFooter three")
        doc.save(path)
    content = path.read_bytes()
    snapshot = PdfSnapshot(source_id="catalog", content=content)
    observed = PdfStructure(snapshot).page_catalog([1], "How many tests?")
    assert any("Test #9" in text for text in observed[0]["native_lines"])
    assert len(observed[0]["native_lines"]) <= 6
    assert observed[0]["numbered_items"] == ["Test #9"]


@pytest.mark.asyncio
@pytest.mark.parametrize("all_empty", [False, True])
async def test_checked_empty_group_uses_application_result_without_an_empty_count_claim(all_empty):
    from tests.test_quantities import enumeration, fake_calls

    active, need = active_session("Benefits until Risks on page 2\nFast\nReliable\nAffordable")
    original = enumeration().groups[0]
    empty = original.model_copy(update={"label": "Empty inspected category", "items": []})
    groups = [empty] if all_empty else [original, empty]
    draft = enumeration().model_copy(update={"groups": groups, "count_mode": "total"})
    fake_calls(active, draft=draft)
    answer = await collect(active, need)
    assert answer and all(count.items for count in answer.answer_parts[0].counts)
    verified, _ = await active.verify(answer)
    assert not verified.abstain
    assert next(iter(active.state.quantities.values())).values == ["0" if all_empty else "3"]


def test_descriptive_optional_locator_cannot_erase_a_correct_inventory():
    from app.llm.quantity_contracts import bind_collection, collection_contract
    from app.llm.quantity_state import QuantityImageBinding

    active, _ = active_session()
    bindings = [
        QuantityImageBinding(
            image_id="image_1",
            source_id="manual",
            document_version="v1",
            physical_page=1,
            support_ids=["E1.S1"],
        )
    ]
    contract = collection_contract("count", bindings, ["E1.S1"])
    raw = dict(
        mode="count",
        complete=True,
        count_mode="total",
        groups=[
            dict(
                label="Requested category",
                complete=True,
                object_anchor="Requested category heading and its continuation on the next page",
                closure_anchor=(
                    "The next category heading establishes the end of this complete list"
                ),
                closure_basis="bounded_object",
                boundary_witness="List ends at the next category.",
                items=[
                    dict(
                        text="Observed member",
                        position=1,
                        image_ids=["image_1"],
                        witness="Observed member appears under the requested category.",
                    )
                ],
            )
        ],
    )
    draft = bind_collection(contract.model_validate(raw), bindings, active.units())
    assert draft.groups[0].items[0].text == "Observed member"
    assert draft.groups[0].items[0].page == 1
    assert len(draft.groups[0].closure_anchor) > 40


@pytest.mark.asyncio
async def test_long_literal_references_survive_without_truncating_or_copying_a_quote():
    from app.llm.quantity_contracts import collection_contract

    source = "Category " + "source context " * 150 + "Observed member"
    active, need = active_session(source)
    from app.llm.scope_validation import scope_lines

    ref = [dict(support_id="E1.S1", start_line=1, end_line=len(scope_lines(source)))]
    draft = collection_contract("count", [], ["E1.S1"]).model_validate(
        dict(
            mode="count",
            complete=True,
            count_mode="total",
            groups=[
                dict(
                    label="Category",
                    complete=True,
                    boundary_ranges=ref,
                    items=[dict(text="Observed member", position=1, source_ranges=ref)],
                )
            ],
        )
    )

    async def call(role, output_type, instructions, data, **kwargs):
        if role == "quantity_selector":
            return QuantitySource(operation_kind="count", available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return draft
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    answer = await collect(active, need)
    assert answer and not answer.abstain
    record = next(iter(active.state.quantities.values()))
    assert record.draft.groups[0].boundary_witness == ""
    assert record.draft.groups[0].items[0].witness == ""
    assert record.draft.groups[0].items[0].source_ranges[0].support_id == "E1.S1"
    assert active.units()["E1.S1"].text == source
    assert QuantityDraft.model_validate_json(record.draft.model_dump_json()) == record.draft


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_counted_numeric_input_hands_off_to_inventory_without_another_selector(
    tmp_path, exhausted
):
    from app.llm.quantity_state import QuantityRecord

    path = tmp_path / "roster.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 60), "MEMBERS", fontname="hebo", fontsize=14)
        page.insert_text((40, 100), "Alpha\nBeta")
        page.insert_text((40, 180), "NEXT GROUP", fontname="hebo", fontsize=14)
        doc.save(path)
    active, need = active_session(
        "MEMBERS\nAlpha\nBeta\nNEXT GROUP", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    active.deps.ledger.blocks[0].payload.update(
        source_id="roster_pdf", document_version=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    active.deps.ledger.source_ids = frozenset({"roster_pdf"})
    if exhausted:
        active.deps.observations.tool_calls = active.policy.max_tool_attempts
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                operation_kind="arithmetic",
                available=True,
                support_ids=["E1.S1"],
                pages=[1],
                modality="image",
            )
        if role == "quantity_checker":
            return QuantityAssessment(
                inputs="supported", coverage="complete", operation="supported"
            )
        if calls.count("quantity_collector") == 1:
            return QuantityDraft(
                mode="arithmetic",
                complete=True,
                expression="members",
                decimals=0,
                operands=[
                    dict(
                        name="members",
                        label="Members",
                        unit="members",
                        value="2",
                        value_origin="counted_items",
                        page=1,
                        image_ids=["image_1"],
                        witness="Alpha and Beta are listed below MEMBERS.",
                    )
                ],
            )
        assert output_type.model_json_schema()["properties"]["mode"]["const"] == "count"
        return output_type.model_validate(
            dict(
                mode="count",
                count_mode="total",
                complete=True,
                groups=[
                    dict(
                        label="MEMBERS",
                        complete=True,
                        boundary_witness="NEXT GROUP ends MEMBERS",
                        items=[
                            dict(position=i, text=name, image_ids=["image_1"], witness=name)
                            for i, name in enumerate(["Alpha", "Beta"], 1)
                        ],
                    )
                ],
            )
        )

    active.call = call
    answer = await collect(active, need)
    if exhausted:
        assert answer is None and calls == ["quantity_selector", "quantity_collector"]
        return
    assert answer and not answer.abstain
    assert calls == [
        "quantity_selector",
        "quantity_collector",
        "quantity_collector",
        "quantity_checker",
    ]
    parent, result = list(active.state.quantities.values())
    assert not parent.has_result and result.values == ["2"]
    assert result.parent_id == parent.id and result.context_support_ids
    native = [active.units()[key] for key in result.context_support_ids]
    assert any("Alpha\nBeta" in unit.text for unit in native)
    assert all("Checked source input" not in unit.text for unit in native)
    assert all(unit.document_version == result.document_version for unit in native)
    assert QuantityRecord.model_validate_json(result.model_dump_json()) == result


def test_model_view_preserves_every_source_line_without_repeating_unused_geometry():
    import copy

    from app.llm.inventory_evidence import inventory_model_view

    raw = context(
        line("P1.L1", "Members", heading=True),
        line("P1.L2", "Alpha"),
        line("P1.L3", "Figure 1", caption=True),
    )
    saved = copy.deepcopy(raw)
    view = inventory_model_view(raw)
    assert raw == saved
    assert [(entry["id"], entry["text"]) for entry in view["pages"][0]["lines"]] == [
        (entry["id"], entry["text"]) for entry in raw["pages"][0]["lines"]
    ]
    assert "bbox" not in view["pages"][0]["lines"][1]
    assert view["pages"][0]["lines"][2]["bbox"] == raw["pages"][0]["lines"][2]["bbox"]
    assert len(json.dumps(view)) < len(json.dumps(raw))


@pytest.mark.asyncio
async def test_boundary_gap_reselects_a_fuller_source_instead_of_repeating_known_pages(tmp_path):
    from app.llm.quantity_state import QuantityRecord

    path = tmp_path / "members.pdf"
    with fitz.open() as doc:
        first = doc.new_page()
        first.insert_text((40, 60), "MEMBERS\nAlpha\nContinued on next page")
        second = doc.new_page()
        second.insert_text((40, 60), "MEMBERS continued\nBeta\nNEXT GROUP")
        doc.save(path)
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    active, need = active_session(
        "MEMBERS\nAlpha\nContinued\nBeta\nNEXT GROUP",
        visual_answers=True,
        render_page=PdfPages(str(tmp_path)),
    )
    active.deps.ledger.blocks[0].payload.update(
        source_id="members_pdf", document_version=version, page_number=1, page_end=2
    )
    active.deps.ledger.source_ids = frozenset({"members_pdf"})
    parent = QuantityRecord(
        id="partial",
        need_id=need,
        support_ids=["E1.S1"],
        source_id="members_pdf",
        document_version=version,
        pages=[1],
        modality="image",
        draft=QuantityDraft(
            mode="count",
            count_mode="total",
            complete=False,
            groups=[
                dict(
                    label="MEMBERS",
                    complete=False,
                    items=[dict(text="Alpha", position=1, page=1, witness="Alpha")],
                )
            ],
        ),
        assessments=[
            QuantityAssessment(
                inputs="supported",
                coverage="incomplete",
                operation="supported",
                issues=[
                    dict(
                        target="group",
                        index=0,
                        kind="boundary",
                        page=1,
                        witness="Continued on next page",
                        description="Inventory continues beyond this view",
                        needed_evidence="The inventory continuation and final boundary",
                        evidence_kind="entity_inventory",
                    )
                ],
            )
        ],
    )
    active.state.quantities[parent.id] = parent
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        if role == "quantity_selector":
            return QuantitySource(
                operation_kind="count",
                available=True,
                support_ids=["E1.S1"],
                pages=[1, 2],
                modality="image",
            )
        if role == "quantity_checker":
            return QuantityAssessment(
                inputs="supported", coverage="complete", operation="supported"
            )
        assert data["physical_pages"] == [1, 2]
        return output_type.model_validate(
            dict(
                mode="count",
                complete=True,
                count_mode="total",
                groups=[
                    dict(
                        label="MEMBERS",
                        complete=True,
                        boundary_witness="NEXT GROUP ends the list",
                        items=[
                            dict(text=name, position=1, image_ids=[f"image_{i}"], witness=name)
                            for i, name in enumerate(["Alpha", "Beta"], 1)
                        ],
                    )
                ],
            )
        )

    active.call = call
    answer = await collect(active, need, parent=parent, repairs_left=0)
    assert answer and not answer.abstain
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]
    assert list(active.state.quantities.values())[-1].values == ["2"]


def test_numbered_window_hint_offers_source_coverage_without_overriding_the_requested_subset():
    from app.llm.inventory_evidence import numbered_window_hints
    from app.llm.quantity_state import QuantityCatalogPage

    def page(number, items, version="v1"):
        return QuantityCatalogPage(
            source_id="manual",
            document_version=version,
            physical_page=number,
            support_ids=[f"p{number}"],
            numbered_items=items,
        )

    pages = [
        page(1, ["Test #1"]),
        page(2, ["Test #2"]),
        page(3, ["Test #1", "Test #2", "Test #3"]),
        page(4, ["Test #4"]),
        page(8, ["Test #9"], version="v2"),
    ]
    hints = numbered_window_hints(pages, "How many tests in the whole course?")
    first = next(h for h in hints if h["document_version"] == "v1")
    assert first["physical_pages"] == [3, 4]
    assert first["observed_identifiers"] == ["test #1", "test #2", "test #3", "test #4"]
    assert "not a completeness receipt" in first["authority"]
    assert numbered_window_hints(pages, "How many tests in Unit One?")
    # Hints remain suggestions. They neither assert the subset answer nor merge versions.
    assert all(len(h["physical_pages"]) <= 3 for h in hints)
    assert not numbered_window_hints(pages, "How many figures?")


def test_document_window_dispatch_stays_source_scoped_and_never_overrides_a_subset():
    from app.llm.inventory_evidence import prefer_document_inventory_window
    from app.llm.quantity_state import QuantityCatalogPage

    active, _ = active_session()
    unit = active.units()["E1.S1"]
    units = {
        f"p{n}": replace(unit, support_unit_id=f"p{n}", page_number=n, page_end=n)
        for n in [1, 2, 3]
    }
    catalog = [
        QuantityCatalogPage(
            source_id=unit.source_id,
            document_version=unit.document_version,
            physical_page=n,
            support_ids=[f"p{n}"],
            numbered_items=labels,
        )
        for n, labels in [(1, ["Test #1"]), (2, ["Test #1", "Test #2"]), (3, ["Test #3"])]
    ]
    original = QuantitySource(
        operation_kind="count",
        available=True,
        support_ids=["p1"],
        pages=[1],
        inventory_scope="document",
    )
    selected = prefer_document_inventory_window(original, catalog, "How many tests?", units)
    assert selected.pages == [2, 3] and selected.modality == "image"
    assert original.pages == [1] and selected.inventory_scope == "document"
    for scope in ["bounded_object", "unknown"]:
        subset = original.model_copy(update={"inventory_scope": scope})
        assert (
            prefer_document_inventory_window(subset, catalog, "Tests in Unit One?", units) == subset
        )
    for changes in [
        dict(authorized=False),
        dict(model_visible=False),
        dict(document_version="other"),
    ]:
        invalid = {**units, "p2": replace(units["p2"], **changes)}
        assert (
            prefer_document_inventory_window(original, catalog, "How many tests?", invalid)
            == original
        )


@pytest.mark.parametrize("quote,dimension,source", [
    ("Among the Higher-income seniors", "population", "Income $75,000+: 90%"),
    ("EPS Code AR01", "entity", "Little Rock | AR01"),
    ("Westhaven", "entity", "West Haven belongs to North District."),
])
def test_grounded_semantic_bindings_do_not_require_question_word_tokens(quote, dimension, source):
    requirements = [dict(dimension=dimension, question_quote=quote)]
    payload = binding_payload(source)
    assert not validate_requirements(payload, requirements, judgment(), set())
    # This changes no source authority: a generated statement of a relationship
    # cannot replace an original source, even when called an equivalent name.
    for basis in ("explicit", "source_relationship", "linguistic_equivalence"):
        assert validate_requirements(
            payload, requirements, judgment(binding_basis=basis), {"E1.S1"}
        )
