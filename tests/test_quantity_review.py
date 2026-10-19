"""Unsubstantiated rejection, targeted correction and ambiguity are separate states."""

import json

import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import run_adaptive_agent
from app.llm.quantities import collect
from app.llm.quantity_review import grounded_issues, merge_repair, verdict
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityIssue,
    QuantityRecord,
    QuantitySource,
)
from app.llm.research_state import ResearchState, TaskSpec
from app.llm.scope_diagnostics import DiagnosticScopeJudgment, validate_objections
from app.llm.scope_validation import scope_payload
from tests.test_adaptive import deps, reply
from tests.test_quantities import active_session, arithmetic, enumeration


def good():
    return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")


def issue(**kw):
    return QuantityIssue(
        kind="wrong_binding",
        target="operand",
        index=1,
        description="South input conflicts with its source row",
        source_ranges=[{"support_id": "E1.S1", "start_line": 2, "end_line": 2}],
        **kw,
    )


def test_bare_rejection_is_indeterminate_and_never_approval():
    review = QuantityAssessment(inputs="supported", coverage="incomplete", operation="supported")
    _, errors = grounded_issues(review, arithmetic(), {"E1.S1": "North 3\nSouth 7"}, [], "Total?")
    checked, status = verdict(review, errors)
    assert status == "indeterminate" and not checked.accepted
    assert "NONPASS_WITHOUT_GROUNDED_ISSUE" in errors


@pytest.mark.parametrize(
    "changes",
    [
        {"index": 99},
        {"source_ranges": [{"support_id": "E99.S1", "start_line": 1, "end_line": 1}]},
        {"source_ranges": [{"support_id": "E1.S1", "start_line": 99, "end_line": 99}]},
    ],
)
def test_objection_must_point_to_existing_target_and_authorized_source(changes):
    bad = issue().model_copy(update={})
    raw = bad.model_dump()
    raw.update(changes)
    bad = QuantityIssue.model_validate(raw)
    review = QuantityAssessment(
        inputs="mismatch", coverage="complete", operation="supported", issues=[bad]
    )
    valid, errors = grounded_issues(
        review, arithmetic(), {"E1.S1": "North 3\nSouth 7"}, [], "Total?"
    )
    assert not valid and errors and verdict(review, errors)[1] == "indeterminate"


def test_targeted_merge_preserves_other_inputs_and_formula():
    review = QuantityAssessment(
        inputs="mismatch", coverage="complete", operation="supported", issues=[issue()]
    )
    old = QuantityRecord(
        id="old",
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual",
        document_version="v1",
        pages=[],
        modality="text",
        draft=arithmetic(),
        assessments=[review],
    )
    proposed = arithmetic().model_copy(
        update={
            "operands": [
                arithmetic().operands[0].model_copy(update={"value": "999"}),
                arithmetic().operands[1].model_copy(update={"value": "8"}),
            ]
        }
    )
    merged = merge_repair(old, proposed)
    assert merged.operands[0] is old.draft.operands[0]
    assert merged.operands[1].value == "8" and old.draft.operands[1].value == "7"
    with pytest.raises(ValueError, match="UNTARGETED_STRUCTURE"):
        merge_repair(old, proposed.model_copy(update={"expression": "a * b"}))


@pytest.mark.asyncio
async def test_one_targeted_repair_keeps_valid_operand_and_rechecks_whole_source():
    active, need = active_session()
    roles = []
    bad = arithmetic().model_copy(
        update={
            "operands": [
                arithmetic().operands[0],
                arithmetic().operands[1].model_copy(update={"value": "9"}),
            ]
        }
    )

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            if roles.count(role) == 1:
                return bad
            assert data["repair_only"][0]["index"] == 1
            return arithmetic().model_copy(
                update={
                    "operands": [
                        arithmetic().operands[0].model_copy(update={"value": "999"}),
                        arithmetic().operands[1],
                    ]
                }
            )
        if roles.count("quantity_checker") == 1:
            return QuantityAssessment(
                inputs="mismatch", coverage="complete", operation="supported", issues=[issue()]
            )
        assert data["draft"]["operands"][0]["value"] == "3"
        return good()

    active.call = call
    result = await collect(active, need)
    assert result.answer_parts[0].text == "10"
    records = list(active.state.quantities.values())
    assert len(records) == 2 and records[1].parent_id == records[0].id
    assert not records[0].values and records[1].values == ["10"]
    assert active.state.quantity_repairs == 1 and roles.count("quantity_checker") == 2


@pytest.mark.asyncio
async def test_receipt_correction_does_not_reextract_or_approve_unknown():
    active, need = active_session()
    seen = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        seen.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return arithmetic()
        return QuantityAssessment(inputs="supported", coverage="unknown", operation="supported")

    active.call = call
    assert await collect(active, need) is None
    record = next(iter(active.state.quantities.values()))
    assert len(record.assessments) == 2 and record.review_status == "indeterminate"
    assert record.provisional_values == ["10"] and not record.values
    assert seen.count("quantity_collector") == 1 and seen.count("quantity_checker") == 2
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert next(iter(restored.quantities.values())).provisional_values == ["10"]


@pytest.mark.asyncio
async def test_equivalent_count_interpretations_are_compared_by_application():
    active, need = active_session("Benefits: Fast Reliable Affordable")
    draft = enumeration().model_copy(update={"count_mode": "total"})
    # Text witnesses use the complete supplied line; entity identities remain distinct.
    source = "Benefits: Fast Reliable Affordable"
    draft = draft.model_copy(
        update={
            "groups": [
                draft.groups[0].model_copy(
                    update={
                        "boundary_witness": source,
                        "items": [
                            i.model_copy(update={"witness": i.text}) for i in draft.groups[0].items
                        ],
                    }
                )
            ]
        }
    )

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return draft
        return QuantityAssessment(
            inputs="supported",
            coverage="complete",
            operation="ambiguous",
            entity_identity="supported",
            alternatives=["total", "distinct"],
            issues=[
                QuantityIssue(
                    kind="operation",
                    target="operation",
                    description="Total occurrences versus unique entities",
                    source_ranges=[{"support_id": "E1.S1", "start_line": 1, "end_line": 1}],
                )
            ],
        )

    active.call = call
    result = await collect(active, need, repairs_left=0)
    record = next(iter(active.state.quantities.values()))
    assert record.ambiguity_results == {"total": ["3"], "distinct": ["3"]}
    assert result.answer_parts[0].text == "3" and record.check.accepted


@pytest.mark.asyncio
async def test_failed_review_does_not_start_a_guessing_answer_loop():
    dependencies = deps("North 3\nSouth 7", question="Total?", derived_answers=True)
    state = ResearchState(task=TaskSpec(question="Total?"), need_planning="failed")
    calls = []
    from tests.test_quantities import text_arithmetic

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        calls.append(list(props))
        if "missing" in props:
            return reply(info, {"answer": None, "missing": ["Need arithmetic"]})
        if "available" in props:
            return reply(
                info, {"available": True, "support_ids": ["E1.S1"], "context_support_ids": []}
            )
        if "operands" in props:
            return reply(info, text_arithmetic())
        if "inputs" in props:
            return reply(
                info, {"inputs": "supported", "coverage": "unknown", "operation": "supported"}
            )
        pytest.fail("Reader/finalizer must not regenerate numbers after an unresolved review")

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True, max_requests=10
    )
    assert json.loads(result.raw)["abstain"] and state.research_stop == "QUANTITY_REVIEW_UNRESOLVED"
    assert len(calls) == 5


def test_scope_rejection_requires_claim_question_and_source_locations():
    active, _ = active_session()
    raw = json.dumps({"answer_parts": [{"text": "10", "support_ids": ["E1.S1"]}], "abstain": False})
    payload = scope_payload("Total?", raw, active.deps.ledger.units)
    judgment = DiagnosticScopeJudgment.model_validate(
        {
            "checks": [
                {"claim_index": 0, "verdict": "insufficient", "reason": "SCOPE_NOT_ESTABLISHED"}
            ]
        }
    )
    assert validate_objections(payload, judgment) == ["SCOPE_OBJECTION_MISSING_OR_DUPLICATE"]
    supported = DiagnosticScopeJudgment.model_validate(
        {
            "checks": [
                {
                    "claim_index": 0,
                    "verdict": "supported",
                    "reason": "NONE",
                    "witnesses": [{"support_id": "E1.S1", "start_line": 1, "end_line": 1}],
                }
            ]
        }
    )
    assert not validate_objections(payload, supported)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "count_mode,identity",
    [("total", "supported"), ("per_group", "supported"), ("total", "unknown")],
)
async def test_different_counts_or_unverified_identity_do_not_resolve_ambiguity(
    count_mode, identity
):
    source = "Benefits: Fast Reliable Affordable\nOther: Fast"
    active, need = active_session(source)
    first = enumeration().groups[0].model_copy(update={"boundary_witness": source})
    second = first.model_copy(
        update={"label": "Other", "items": [first.items[0]], "boundary_witness": source}
    )
    draft = enumeration().model_copy(update={"count_mode": count_mode, "groups": [first, second]})

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return draft
        return QuantityAssessment(
            inputs="supported",
            coverage="complete",
            operation="ambiguous",
            entity_identity=identity,
            alternatives=["total", "distinct"],
            issues=[
                QuantityIssue(
                    kind="operation",
                    target="operation",
                    description="Occurrences or unique names",
                    source_ranges=[{"support_id": "E1.S1", "start_line": 1, "end_line": 2}],
                )
            ],
        )

    active.call = call
    assert await collect(active, need, repairs_left=0) is None
    record = next(iter(active.state.quantities.values()))
    assert not record.check.accepted and not record.values
    if count_mode == "total" and identity == "supported":
        assert record.ambiguity_results == {"total": ["4"], "distinct": ["3"]}
    else:
        assert not record.ambiguity_results


@pytest.mark.asyncio
async def test_budget_stop_keeps_finished_input_review_without_rewriting_answer():
    from app.llm.adaptive import ResearchClosed, finalize_research

    active, need = active_session()
    seen = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        seen.append(role)
        if role == "quantity_selector":
            return QuantitySource(available=True, support_ids=["E1.S1"])
        if role == "quantity_collector":
            return arithmetic()
        if seen.count("quantity_checker") == 1:
            return QuantityAssessment(inputs="supported", coverage="unknown", operation="supported")
        raise ResearchClosed("REQUEST_RESERVE")

    active.call = call
    with pytest.raises(ResearchClosed):
        await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert (
        record.provisional_values == ["10"] and len(record.assessments) == 1 and not record.values
    )
    result, _ = await finalize_research(active)
    assert result.abstain and "finalizer" not in seen


@pytest.mark.asyncio
async def test_checked_quantity_scope_uses_question_not_inferred_plan_as_extra_requirement():
    from app.llm.research_needs import NeedWorkflow
    from tests.test_adaptive_fast_path import line_scope
    from tests.test_quantities import fake_calls

    active, need = active_session(scope_validation_enabled=True)
    active.need_workflow = NeedWorkflow(active)
    active.compact_context = True
    fake_calls(active)
    prepared = await collect(active, need)
    active.model = FunctionModel(
        lambda messages, info: (line_scope(messages, info, "E1.S1", quote="North 3"))
    )
    actual_call = type(active).call.__get__(active, type(active))

    async def call(role, output_type, instructions, data, **kwargs):
        assert "evidence_requirements" not in data
        assert data["question"] == active.state.task.question
        return await actual_call(role, output_type, instructions, data, **kwargs)

    active.call = call
    result, receipt = await active.verify(prepared)
    assert receipt.accepts(
        active.state.task.question, result.raw_answer(), active.deps.ledger.units
    )


def inventory_parent():
    return QuantityRecord(
        id="parent",
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual",
        document_version="v1",
        pages=[],
        modality="text",
        draft=arithmetic(),
        provisional_values=["10"],
        assessments=[
            QuantityAssessment(
                inputs="supported",
                coverage="complete",
                operation="ambiguous",
                alternatives=["total", "distinct"],
                issues=[
                    QuantityIssue(
                        kind="operation",
                        target="operation",
                        description="Need entity overlap",
                        evidence_kind="entity_inventory",
                        source_ranges=[{"support_id": "E1.S1", "start_line": 1, "end_line": 2}],
                    )
                ],
            )
        ],
    )


def test_inventory_contract_requires_items_without_reinterpreting_per_group():
    from app.llm.quantity_review import repair_requirement
    from app.llm.quantity_state import EntityInventoryDraft, TextEntityInventoryDraft

    parent = inventory_parent()
    assert repair_requirement(parent).evidence_kind == "entity_inventory"
    for schema in (EntityInventoryDraft, TextEntityInventoryDraft):
        raw = arithmetic().model_dump()
        for operand in raw["operands"]:
            operand.update(
                witness="",
                source_ranges=[
                    {
                        "support_id": "E1.S1",
                        "start_line": 1,
                        "end_line": 2,
                    }
                ],
            )
        with pytest.raises(ValueError, match="REQUIRES_ENTITY_INVENTORY"):
            schema.model_validate(raw)
    assert parent.assessments[0].alternatives == ["total", "distinct"]
    assert parent.provisional_values == ["10"]


@pytest.mark.asyncio
async def test_inventory_repair_rejects_unchanged_source_before_extraction():
    active, need = active_session()
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        assert data["repair_requirement"]["evidence_kind"] == "entity_inventory"
        return QuantitySource(available=True, support_ids=["E1.S1"])

    active.call = call
    with pytest.raises(ValueError, match="REUSED_INSUFFICIENT_SOURCE"):
        await collect(active, need, parent=inventory_parent(), repairs_left=0)
    assert roles == ["quantity_selector"]


@pytest.mark.asyncio
async def test_inventory_repair_reads_new_source_and_keeps_original_numbers():
    from app.llm.quantity_state import TextEntityInventoryDraft
    from tests.test_adaptive import block

    active, need = active_session()
    active.deps.ledger.add([block("North: Alpha Beta\nSouth: Gamma", id="names", page_number=2)])
    parent = inventory_parent()
    active.state.quantities[parent.id] = parent
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            assert data["candidates"][0]["support_id"] == "E2.S1"
            return QuantitySource(available=True, support_ids=["E2.S1"])
        if role == "quantity_collector":
            assert output_type is TextEntityInventoryDraft
            assert not data["preserve_other_inputs"]
            groups = []
            for line, (label, names) in enumerate(
                [
                    ("North", ["Alpha", "Beta"]),
                    ("South", ["Gamma"]),
                ],
                1,
            ):
                ref = [{"support_id": "E2.S1", "start_line": line, "end_line": line}]
                groups.append(
                    {
                        "label": label,
                        "complete": True,
                        "boundary_ranges": ref,
                        "items": [
                            {"text": name, "position": i, "source_ranges": ref}
                            for i, name in enumerate(names, 1)
                        ],
                    }
                )
            return output_type.model_validate(
                {
                    "mode": "count",
                    "count_mode": "total",
                    "complete": True,
                    "groups": groups,
                }
            )
        return good()

    active.call = call
    result = await collect(active, need, parent=parent, repairs_left=0)
    assert result.answer_parts[0].text == "3"
    assert active.state.quantities[parent.id].provisional_values == ["10"]
    child = next(r for r in active.state.quantities.values() if r.parent_id)
    assert child.support_ids == ["E2.S1"] and child.values == ["3"]
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]


def test_image_schema_requires_page_and_explicit_completeness_before_handoff():
    from app.llm.quantity_state import ImageQuantityDraft

    schema = ImageQuantityDraft.model_json_schema()
    assert "page" in schema["$defs"]["ImageQuantityItem"]["required"]
    assert "page" in schema["$defs"]["ImageQuantityOperand"]["required"]
    assert "complete" in schema["$defs"]["ImageQuantityGroup"]["required"]
    raw = enumeration().model_dump()
    for group in raw["groups"]:
        for item in group["items"]:
            item.pop("page", None)
    with pytest.raises(ValueError, match="page"):
        ImageQuantityDraft.model_validate(raw)
    raw = enumeration().model_dump()
    raw["groups"][0].pop("complete")
    with pytest.raises(ValueError, match="complete"):
        ImageQuantityDraft.model_validate(raw)
    draft = ImageQuantityDraft.model_validate(enumeration().model_dump())
    assert draft.groups[0].items[0].page == 1 and draft.groups[0].complete


def test_entity_evidence_repair_can_change_representation_without_losing_parent():
    parent = inventory_parent()
    review = parent.assessments[0].model_copy(
        update={
            "operation": "supported",
            "coverage": "unknown",
            "alternatives": [],
            "issues": [
                QuantityIssue(
                    kind="unreadable",
                    target="operand",
                    index=0,
                    description="Need individual entity identities to bind this input",
                    evidence_kind="entity_inventory",
                )
            ],
        }
    )
    parent = parent.model_copy(update={"assessments": [review]})
    assert merge_repair(parent, enumeration()).mode == "count"
    assert parent.draft.mode == "arithmetic" and parent.provisional_values == ["10"]
