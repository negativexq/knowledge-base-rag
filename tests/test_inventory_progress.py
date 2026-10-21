"""Checked count windows survive continuation without certifying a partial total."""

from dataclasses import replace

import pytest

from app.llm.adaptive import ResearchClosed
from app.llm.inventory_evidence import inventory_model_view
from app.llm.inventory_progress import checkpoint_inventory, inventory_view
from app.llm.quantities import candidate, collect
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityDraft,
    QuantityImageBinding,
    QuantityIssue,
    QuantityRecord,
    QuantitySource,
)
from tests.test_quantities import active_session


def window(key, page, labels, *, reviewed=True, inputs="supported", version="v1"):
    return QuantityRecord(
        id=key, need_id="need", source_id="manual", document_version=version,
        support_ids=["E1.S1"], pages=[page], modality="image", inventory_scope="document",
        draft=QuantityDraft(mode="count", complete=False, groups=[dict(
            label="Requested diagrams", complete=False, items=[dict(
                text=text, source_object=f"Diagram {i}", position=i, page=page,
                image_ids=["image_1"], witness=text,
            ) for i, text in enumerate(labels, 1)],
        )]),
        image_bindings=[QuantityImageBinding(
            image_id="image_1", source_id="manual", document_version=version,
            physical_page=page, support_ids=["E1.S1"],
        )],
        assessments=[QuantityAssessment(
            inputs=inputs, coverage="incomplete", operation="supported",
        )] if reviewed else [],
    )


def put(active, record):
    active.state.quantities[record.id] = record
    return checkpoint_inventory(active.state, record)


def test_image_payload_keeps_every_literal_line_and_locator_without_duplicate_geometry():
    raw = dict(page_count=3, pages=[dict(page=2, limited=True, lines=[dict(
        id=f"P2.L{i}", text=text, heading=True, caption=False,
        bbox=[0.1, 0.2, 0.8, 0.3], size=12,
    ) for i, text in enumerate(["Heading", "Signal A", "\\\\", "Signal B"], 1)])])
    view = inventory_model_view(raw, image_authority=True)
    assert view["pages"][0]["limited"]
    assert view["pages"][0]["lines"] == [
        {"id": line["id"], "text": line["text"]} for line in raw["pages"][0]["lines"]
    ]
    assert all("bbox" in line for line in raw["pages"][0]["lines"])


def test_disjoint_windows_accumulate_without_publishing_an_incomplete_total():
    active, _ = active_session()
    first = window("first", 2, ["A", "B", "C"])
    second = window("second", 5, ["D", "E"])
    put(active, first)
    progress = put(active, second)
    assert len(progress.items) == 5 and not progress.complete
    assert len(progress.windows) == 2
    assert len(active.state.quantities["first"].draft.groups[0].items) == 3
    assert len(active.state.quantities["second"].draft.groups[0].items) == 2
    for record in [first, second]:
        with pytest.raises(ValueError, match="NOT_CHECKED"):
            candidate(record)
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    units = {k: replace(v, page_end=8) for k, v in active.units().items()}
    view = inventory_view(restored, units)[0]
    assert view["observed_positive_pages"] == [2, 5]
    assert len(view["checked_occurrences"]) == 5 and not view["complete"]


def test_equal_labels_on_different_pages_are_not_collapsed_and_overlap_is_deduplicated():
    active, _ = active_session()
    put(active, window("a", 2, ["Repeated label"]))
    put(active, window("b", 5, ["Repeated label"]))
    progress = put(active, window("c", 2, ["Repeated label"]))
    assert len(progress.items) == 2 and not progress.conflicts


def test_disagreement_on_the_same_source_occurrence_requires_review():
    active, _ = active_session()
    put(active, window("a", 2, ["One reading"]))
    progress = put(active, window("b", 2, ["Contradictory reading"]))
    assert not progress.items and len(progress.conflicts) == 1


def test_pending_and_rejected_windows_do_not_erase_or_approve_existing_findings():
    active, _ = active_session()
    put(active, window("a", 2, ["Checked"]))
    put(active, window("b", 3, ["Pending"], reviewed=False))
    progress = put(active, window("c", 4, ["Wrong group"], inputs="mismatch"))
    assert len(progress.items) == 1
    assert [w.input_status for w in progress.windows] == ["supported", "pending", "rejected"]
    # A completed independent review can add the pending window without recollection.
    progress = put(active, window("b", 3, ["Pending"]))
    assert len(progress.items) == 2


def test_output_operation_rejection_does_not_erase_independently_supported_source_items():
    active, _ = active_session()
    record = window("a", 2, ["Checked source title"])
    record = record.model_copy(update={"assessments": [
        record.assessments[0].model_copy(update={"operation": "mismatch"})
    ]})
    progress = put(active, record)
    assert len(progress.items) == 1 and not progress.complete
    with pytest.raises(ValueError, match="NOT_CHECKED"):
        candidate(record)


def test_source_versions_and_needs_are_separate_inventories():
    active, _ = active_session()
    put(active, window("a", 2, ["A"]))
    put(active, window("b", 2, ["B"], version="v2"))
    put(active, window("c", 2, ["C"]).model_copy(update={"need_id": "other"}))
    assert len(active.state.inventories) == 3
    assert all(len(p.items) == 1 for p in active.state.inventories.values())


def test_hidden_stale_or_rejected_sources_are_not_reintroduced_by_the_checkpoint():
    active, _ = active_session()
    record = window("a", 1, ["Checked"])
    put(active, record)
    units = active.units()
    assert inventory_view(active.state, units)[0]["checked_occurrences"]
    assert not inventory_view(active.state, {
        k: replace(v, model_visible=False) for k, v in units.items()
    })
    assert not inventory_view(active.state, {
        k: replace(v, document_version="new") for k, v in units.items()
    })
    active.state.quantities[record.id] = record.model_copy(update={
        "diagnostic_errors": ["INVALID_SOURCE_BINDING"],
    })
    assert not inventory_view(active.state, units)[0]["checked_occurrences"]


@pytest.mark.asyncio
async def test_real_collection_checkpoints_supported_items_before_the_next_checker_stops():
    active, need = active_session("Alpha\nBeta\nContinued")
    collections = 0

    async def call(role, output_type, instructions, data, *, research, images=None):
        nonlocal collections
        if role == "quantity_selector":
            return QuantitySource(available=True, operation_kind="count", support_ids=["E1.S1"])
        if role == "quantity_collector":
            collections += 1
            return output_type.model_validate(dict(
                mode="count", complete=False, count_mode="total", groups=[dict(
                    label="Items", complete=False,
                    boundary_ranges=[dict(support_id="E1.S1", start_line=3, end_line=3)],
                    items=[dict(text="Alpha" if collections == 1 else "Beta", position=collections,
                        source_object="Items", source_ranges=[dict(
                            support_id="E1.S1", start_line=collections, end_line=collections,
                        )])],
                )],
            ))
        if collections == 2:
            raise ResearchClosed("TOKEN_RESERVE")
        return QuantityAssessment(
            inputs="supported", coverage="incomplete", operation="supported",
            issues=[QuantityIssue(
                kind="boundary", target="group", index=0, description="More items follow",
                source_ranges=[dict(support_id="E1.S1", start_line=3, end_line=3)],
                needed_evidence="Remaining items",
            )],
        )

    active.call = call
    assert await collect(active, need, repairs_left=0) is None
    with pytest.raises(ResearchClosed, match="TOKEN_RESERVE"):
        await collect(active, need, repairs_left=0)
    progress = next(iter(active.state.inventories.values()))
    assert [w.input_status for w in progress.windows] == ["supported", "pending"]
    assert len(progress.items) == 1
    view = active.context()["partial_inventories"][0]
    assert view["checked_occurrences"][0]["text"] == "Alpha"
    assert not view["complete"]
