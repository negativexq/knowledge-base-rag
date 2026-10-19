"""Operation contracts reject unrelated fields and bind evidence handles in application code."""

import pytest
from pydantic import ValidationError

from app.llm.quantities import execute
from app.llm.quantity_contracts import bind_collection, collection_contract
from app.llm.quantity_review import merge_repair, repair_requirement
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityDraft,
    QuantityImageBinding,
    QuantityIssue,
    QuantityRecord,
)


def binding():
    return QuantityImageBinding(
        image_id="image_1", source_id="report", document_version="v1", physical_page=16
    )


def operand():
    return dict(
        name="internet",
        label="Men aged 65+",
        value="65",
        unit="%",
        image_ids=["image_1"],
        witness="65",
    )


def test_read_uses_application_page_identity_and_never_requires_comparison():
    schema = collection_contract("read", [binding()], ["E1.S1"])
    wire = schema.model_validate(dict(mode="read", complete=True, operands=[operand()]))
    draft = bind_collection(wire, [binding()], {})
    assert draft.operands[0].page == 16
    assert execute(draft) == (["65"], "")
    for changes in ({"page": 15}, {"image_ids": ["printed_page_15"]}):
        with pytest.raises(ValidationError):
            schema.model_validate(dict(mode="read", complete=True, operands=[operand() | changes]))
    comparison = collection_contract("select", [binding()], ["E1.S1"])
    with pytest.raises(ValidationError):
        comparison.model_validate(
            dict(mode="select", complete=True, operands=[operand()], select_mode="minimum")
        )


def test_arithmetic_cannot_emit_count_settings_or_model_written_result():
    schema = collection_contract("arithmetic", [binding()], ["E1.S1"])
    raw = dict(
        mode="arithmetic",
        complete=True,
        operands=[operand()],
        expression="internet",
        decimals=2,
        result_unit="%",
        interpretation="Internet use",
    )
    assert bind_collection(schema.model_validate(raw), [binding()], {}).expression == "internet"
    for extra in ({"count_mode": "total"}, {"result": "65"}):
        with pytest.raises(ValidationError):
            schema.model_validate(raw | extra)
    assert set(schema.model_fields) == {
        "mode",
        "complete",
        "operands",
        "expression",
        "decimals",
        "result_unit",
        "interpretation",
    }


def test_text_collection_accepts_only_supplied_support_handles():
    schema = collection_contract("read", [], ["E1.S1"])
    item = {key: value for key, value in operand().items() if key not in {"image_ids", "witness"}}
    item["source_ranges"] = [{"support_id": "E2.S1", "start_line": 1, "end_line": 1}]
    with pytest.raises(ValidationError):
        schema.model_validate(dict(mode="read", complete=True, operands=[item]))


def test_coverage_repair_preserves_goal_and_verified_items_then_rechecks_union():
    old = QuantityDraft(
        mode="list",
        list_unique=True,
        complete=False,
        items=[
            dict(text="Alpha", position=1, page=11, witness="Alpha"),
            dict(text="Beta", position=2, page=11, witness="Beta"),
        ],
    )
    record = QuantityRecord(
        id="original",
        need_id="need",
        support_ids=["E1.S1"],
        source_id="report",
        document_version="v1",
        pages=[11],
        modality="image",
        draft=old,
        assessments=[
            QuantityAssessment(
                inputs="supported",
                coverage="incomplete",
                operation="supported",
                issues=[
                    QuantityIssue(
                        kind="missing_item",
                        target="item",
                        index=0,
                        description="Full roster continues",
                        page=9,
                        witness="Gamma",
                    )
                ],
            )
        ],
    )
    assert repair_requirement(record).evidence_kind == "coverage_completion"
    replacement = QuantityDraft(
        mode="list",
        complete=True,
        items=[
            dict(text="Alpha", position=1, page=9, witness="Alpha"),
            dict(text="Gamma", position=3, page=9, witness="Gamma"),
        ],
    )
    merged = merge_repair(record, replacement)
    assert [i.text for i in merged.items] == ["Alpha", "Beta", "Gamma"]
    assert merged.items[0] == old.items[0]
    assert record.draft == old and record.check is None
    with pytest.raises(ValueError, match="REPAIR_CHANGED_GOAL_OPERATION"):
        merge_repair(
            record,
            QuantityDraft(
                mode="read", operands=[dict(name="n", label="Count", value="3", witness="3")]
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed_receipt", [False, True])
async def test_incomplete_list_can_read_new_source_without_changing_goal(malformed_receipt):
    import json

    from app.llm.quantities import collect
    from app.llm.quantity_state import QuantitySource
    from tests.test_adaptive import block
    from tests.test_quantities import active_session

    active, need = active_session("Alpha Beta")
    active.deps.ledger.add([block("Gamma", id="full-roster", page_number=2)])
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        repairing = bool(data.get("repair_requirement"))
        if role == "quantity_selector":
            return QuantitySource(
                available=True,
                operation_kind="list",
                support_ids=["E2.S1" if repairing else "E1.S1"],
            )
        if role == "quantity_collector":
            if repairing:
                assert data["goal_operation"] == "list"
                assert not data["preserve_other_inputs"]
            key = "E2.S1" if repairing else "E1.S1"
            names = ["Gamma"] if repairing else ["Alpha", "Beta"]
            return output_type.model_validate(
                dict(
                    mode="list",
                    complete=True,
                    list_order="source",
                    list_unique=True,
                    items=[
                        dict(
                            text=name,
                            position=i,
                            source_ranges=[
                                dict(
                                    support_id=key,
                                    start_line=1,
                                    end_line=1,
                                )
                            ],
                        )
                        for i, name in enumerate(names, 1)
                    ],
                )
            )
        if malformed_receipt and calls.count("quantity_checker") == 1:
            return QuantityAssessment(
                inputs="supported",
                coverage="incomplete",
                operation="supported",
                issues=[
                    QuantityIssue(
                        kind="boundary",
                        target="operand",
                        index=0,
                        description="Wrong diagnostic target for a list",
                        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                    )
                ],
            )
        if calls.count("quantity_checker") == (2 if malformed_receipt else 1):
            return QuantityAssessment(
                inputs="supported",
                coverage="incomplete",
                operation="supported",
                issues=[
                    QuantityIssue(
                        kind="boundary",
                        target="item",
                        index=0,
                        description="Roster continues",
                        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                    )
                ],
            )
        assert len(data["draft"]["items"]) == 3
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    assert json.loads(result.answer_parts[0].text) == ["Alpha", "Beta", "Gamma"]
    assert len(active.state.quantities) == 2
    child = next(r for r in active.state.quantities.values() if r.parent_id)
    assert child.review_status == "accepted"
    assert active.state.quantities[child.parent_id].review_status == "rejected"
    expected = ["quantity_selector", "quantity_collector", "quantity_checker"]
    assert calls == expected + (["quantity_checker"] if malformed_receipt else []) + expected


def test_list_review_cannot_spend_repair_budget_on_a_nonexistent_operand():
    from app.llm.quantity_contracts import review_contract

    draft = QuantityDraft(
        mode="list", complete=True, items=[dict(text="Alpha", position=1, witness="Alpha")]
    )
    schema = review_contract(draft)
    issue = dict(
        kind="boundary",
        target="item",
        index=0,
        description="Roster is incomplete",
        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
    )
    raw = dict(inputs="supported", coverage="incomplete", operation="supported", issues=[issue])
    assert schema.model_validate(raw).issues[0].target == "item"
    for changes in ({"target": "operand"}, {"target": "group"}, {"index": 1}, {"index": None}):
        with pytest.raises(ValidationError):
            schema.model_validate(raw | {"issues": [issue | changes]})
    assert isinstance(schema.model_validate(raw), QuantityAssessment)


@pytest.mark.parametrize("coverage", ["incomplete", "unknown"])
def test_unresolved_binding_and_coverage_replace_inventory_without_discarding_parent(coverage):
    from tests.test_quantity_scope_repair import record

    parent = record().model_copy(
        update={
            "assessments": [
                QuantityAssessment(
                    inputs="unknown",
                    coverage=coverage,
                    operation="supported",
                    issues=[
                        QuantityIssue(
                            kind="boundary",
                            target="item",
                            index=0,
                            description="Company-wide coverage is unverified",
                            source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                        )
                    ],
                )
            ],
        }
    )
    replacement = QuantityDraft(
        mode="list",
        complete=True,
        items=[
            dict(text="Beta", position=1, witness="Full roster: Beta"),
            dict(text="Gamma", position=2, witness="Full roster: Gamma"),
        ],
    )
    assert repair_requirement(parent).evidence_kind == "scope_research"
    result = merge_repair(parent, replacement)
    assert [i.text for i in result.items] == ["Beta", "Gamma"]
    assert parent.values == ["Alpha"] and parent.draft.items[0].text == "Alpha"
