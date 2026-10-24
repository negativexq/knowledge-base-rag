"""Missing inputs, conditional joins and empty inventories retain source authority."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.evidence.documents import DocumentResult
from app.llm.adaptive import finalize_research
from app.llm.quantities import collect, execute
from app.llm.quantity_contracts import bind_collection, collection_contract
from app.llm.quantity_review import grounded_issues, merge_repair, repair_requirement
from app.llm.quantity_sources import bind_gap_source, complete_sources, fresh_source_view
from app.llm.quantity_state import QuantityAssessment, QuantityDraft, QuantityIssue, QuantityRecord
from tests.test_adaptive import block
from tests.test_quantities import active_session, arithmetic


def lookup():
    # The entity with the larger comparison score has the SMALLER output value.
    return QuantityDraft(
        mode="lookup",
        complete=True,
        select_mode="maximum",
        operands=[
            dict(name=name, label=name, value=value, unit="%", witness=f"{name} {value}")
            for name, value in [
                ("a_one", "20"),
                ("a_two", "30"),
                ("a_output", "80"),
                ("b_one", "25"),
                ("b_two", "35"),
                ("b_output", "70"),
            ]
        ],
        choices=[
            dict(label="A", score_expression="a_one + a_two", value_operand="a_output"),
            dict(label="B", score_expression="b_one + b_two", value_operand="b_output"),
        ],
    )


def missing_record():
    return QuantityRecord(
        id="parent",
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual",
        document_version="v1",
        pages=[1],
        modality="text",
        draft=arithmetic(),
        assessments=[
            QuantityAssessment(
                inputs="supported",
                coverage="incomplete",
                operation="supported",
                issues=[
                    QuantityIssue(
                        kind="missing_item",
                        target="operand",
                        index=1,
                        description="The lease total needs a source breakdown",
                        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                        needed_evidence="Current and noncurrent lease liabilities in the note",
                    )
                ],
            )
        ],
    )


def test_conditional_lookup_computes_prerequisites_instead_of_maximizing_output():
    assert execute(lookup()) == (["70"], "")
    tied = lookup()
    tied = tied.model_copy(
        update={
            "operands": [
                o.model_copy(update={"value": "25", "witness": "a_one 25"})
                if o.name == "a_one"
                else o.model_copy(update={"value": "35", "witness": "a_two 35"})
                if o.name == "a_two"
                else o
                for o in tied.operands
            ]
        }
    )
    assert execute(tied)[0] == ["80", "70"]


def test_lookup_rejects_unknown_or_self_referential_comparison():
    for expression in ["missing", "b_output", "a_one ** 2", "a_one + 17"]:
        draft = lookup()
        choices = [
            draft.choices[0],
            draft.choices[1].model_copy(update={"score_expression": expression}),
        ]
        with pytest.raises(ValueError):
            execute(draft.model_copy(update={"choices": choices}))


def test_numeric_coverage_gap_is_grounded_and_routes_to_source_research():
    parent = missing_record()
    issues, errors = grounded_issues(
        parent.assessments[0], parent.draft, {"E1.S1": "North 3\nSouth 7"}, [], "Total?"
    )
    assert issues and not errors
    assert repair_requirement(parent).evidence_kind == "scope_research"


@pytest.mark.asyncio
async def test_missing_input_searches_same_snapshot_and_retains_parent_receipt():
    active, _ = active_session()
    parent = missing_record()
    active.state.quantities[parent.id] = parent
    calls = []

    async def read(request):
        calls.append(request)
        assert request.document.source_id == "manual"
        assert request.document.document_version == "v1"
        assert request.action == "search" and request.search_mode == "ranked"
        assert "lease" in request.query and request.limit == 3
        return DocumentResult(
            blocks=[block("Lease liabilities 12", id="note", page_number=8)],
            outline=[],
            has_more=True,
        )

    active.deps.documents = SimpleNamespace(read=read)
    await complete_sources(active, parent)
    assert len(calls) == 1 and active.deps.observations.tool_calls == 1
    assert any(u.page_number == 8 for u in active.units().values())
    assert active.state.quantities[parent.id] is parent
    assert active.state.search_evidence[-1].admitted_support_ids
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert restored.search_evidence[-1].query == calls[0].query
    # Hard tool limits also apply to application-dispatched search.
    active.deps.observations.tool_calls = active.policy.max_tool_attempts
    await complete_sources(active, parent)
    assert len(calls) == 1


def test_empty_list_requires_inspected_absence_and_can_replace_rejected_items():
    with pytest.raises(ValidationError):
        QuantityDraft(mode="list", items=[], complete=True)
    empty = QuantityDraft(
        mode="list",
        items=[],
        complete=True,
        absence=dict(source_object="Functions", witness="All boxes are blue"),
    )
    assert execute(empty) == ([], "")
    parent = missing_record().model_copy(
        update={
            "draft": QuantityDraft(
                mode="list", complete=True, items=[dict(position=1, text="Alpha", witness="Alpha")]
            ),
            "assessments": [
                QuantityAssessment(
                    inputs="mismatch",
                    coverage="complete",
                    operation="supported",
                    issues=[
                        QuantityIssue(
                            kind="wrong_binding",
                            target="item",
                            index=0,
                            description="The box has a different color",
                        )
                    ],
                )
            ],
        }
    )
    assert merge_repair(parent, empty).absence is not None
    assert parent.draft.items[0].text == "Alpha"


@pytest.mark.asyncio
async def test_empty_inventory_is_reviewed_and_survives_independent_finalization():
    active, need = active_session("The entire figure contains blue and green boxes.")
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return output_type(
                available=True, operation_kind="list", support_ids=["E1.S1"], context_support_ids=[]
            )
        if role == "quantity_collector":
            return output_type.model_validate(
                dict(
                    mode="list",
                    complete=True,
                    items=[],
                    list_order="ascending",
                    list_unique=True,
                    absence=dict(
                        source_object="Entire figure",
                        source_ranges=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                    ),
                )
            )
        assert data["draft"]["absence"]["witness"]
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need)
    assert result.answer_parts[0].text == "[]"
    receipt = next(iter(active.state.quantities.values()))
    assert receipt.has_result and receipt.execution_status == "completed" and not receipt.values
    assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]

    async def verify(answer):
        assert json.loads(answer.answer_parts[0].text) == []
        return answer, None

    active.verify = verify
    active.state.research_stop = "REQUEST_LIMIT"
    finalized, _ = await finalize_research(active)
    assert finalized.answer_parts[0].text == "[]" and len(roles) == 3


def test_empty_image_inventory_is_bound_to_application_image_identity():
    from tests.test_quantity_contracts import binding

    schema = collection_contract("list", [binding()], ["E1.S1"])
    raw = dict(
        mode="list",
        complete=True,
        items=[],
        list_order="source",
        list_unique=True,
        absence=dict(
            source_object="Figure 1",
            witness="All function boxes have other colors",
            image_ids=["image_1"],
        ),
    )
    draft = bind_collection(schema.model_validate(raw), [binding()], {})
    assert draft.absence.page == 16
    raw["absence"]["image_ids"] = ["unknown"]
    with pytest.raises(ValidationError):
        schema.model_validate(raw)


def test_switching_existing_input_to_context_is_not_fresh_evidence():
    from app.llm.quantity_state import QuantitySource

    active, _ = active_session()
    active.admit([block("Definitions for the same table", id="definition")])
    parent = missing_record().model_copy(update={"support_ids": ["E1.S1", "E2.S1"]})
    selection = QuantitySource(available=True, support_ids=["E1.S1"], context_support_ids=["E2.S1"])
    assert not fresh_source_view(active, parent, selection)
    active.admit([block("North 3\nSouth 7", id="alias")])
    assert not fresh_source_view(
        active, parent, selection.model_copy(update={"support_ids": ["E3.S1"]})
    )


@pytest.mark.asyncio
async def test_source_gap_candidate_is_consumed_even_when_selector_repeats_old_view():
    from app.llm.quantity_state import QuantitySource

    active, need = active_session("North 3")
    parent = missing_record().model_copy(update={"need_id": need})
    active.state.quantities[parent.id] = parent

    async def read(request):
        assert active.state.task.question in request.query
        return DocumentResult(blocks=[block("South 7", id="missing", page_number=8)], outline=[])

    active.deps.documents = SimpleNamespace(read=read)
    calls = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        calls.append(role)
        if role == "quantity_selector":
            assert data["completion_search"]["parent_id"] == parent.id
            # Deliberately ignore the newly found candidate, reproducing the handoff bug.
            return QuantitySource(available=True, support_ids=["E1.S1"])
        assert any("South 7" in str(s) for s in data["source"])
        if role == "quantity_collector":
            return arithmetic()
        return QuantityAssessment(inputs="supported", coverage="complete", operation="supported")

    active.call = call
    result = await collect(active, need, parent=parent, repairs_left=0)
    assert result.answer_parts[0].text == "10"
    gap = active.state.quantity_gap_searches[parent.id]
    assert gap.status == "resolved" and "E2.S1" in gap.inspected_support_ids
    assert active.state.quantities[parent.id] is parent
    assert calls == ["quantity_selector", "quantity_collector", "quantity_checker"]


def test_gap_binding_adds_fresh_page_without_growing_source_window():
    from app.llm.quantity_state import QuantityGapSearch, QuantitySource

    active, _ = active_session()
    active.admit([block("Second paragraph", id="second", page_number=1)])
    active.admit([block("Output table", id="output", page_number=3)])
    active.admit([block("Comparison and its population", id="fresh", page_number=1, page_end=2)])
    parent = missing_record().model_copy(
        update={
            "support_ids": ["E1.S1", "E2.S1", "E3.S1"],
            "pages": [1, 3],
            "modality": "image",
        }
    )
    selection = QuantitySource(
        available=True, support_ids=parent.support_ids, pages=[1, 3], modality="image"
    )
    gap = QuantityGapSearch(
        parent_id=parent.id,
        requirements=parent.assessments[-1].issues,
        query="Missing comparison",
        candidate_support_ids=["E4.S1"],
    )
    chosen = bind_gap_source(active, parent, selection, gap)
    assert chosen.support_ids == ["E4.S1", "E3.S1"]
    assert chosen.pages == [1, 2, 3] and fresh_source_view(active, parent, chosen)


def test_lookup_population_series_and_period_survive_checkpoint():
    from app.llm.quantity_contracts import review_contract
    from tests.test_quantity_contracts import binding, operand

    schema = collection_contract("lookup", [binding()], ["E1.S1"])
    values = [
        operand() | dict(name="score", population="All surveyed adults", series="A", period="2024"),
        operand()
        | dict(name="output", population="Registered voters in A", series="A", period="2024"),
    ]
    raw = dict(
        mode="lookup",
        complete=True,
        operands=values,
        select_mode="maximum",
        choices=[
            dict(label="A", score_expression="score", value_operand="output"),
            dict(label="B", score_expression="score", value_operand="output"),
        ],
    )
    draft = bind_collection(schema.model_validate(raw), [binding()], {})
    restored = QuantityDraft.model_validate_json(draft.model_dump_json())
    assert restored.operands[0].population == "All surveyed adults"
    assert restored.operands[1].population == "Registered voters in A"
    assert restored.operands[0].period == "2024"
    # An output population may differ legitimately; matching is judged per role.
    assert "population" in str(restored.model_dump())
    assert (
        review_contract(restored)
        .model_validate(dict(inputs="supported", coverage="complete", operation="supported"))
        .operation
        == "supported"
    )


def test_image_alias_on_same_page_does_not_count_as_new_inspection():
    from app.llm.quantity_state import QuantitySource

    active, _ = active_session()
    active.admit([block("Another paragraph on an already inspected page", id="alias")])
    parent = missing_record().model_copy(update={"modality": "image"})
    assert not fresh_source_view(
        active,
        parent,
        QuantitySource(available=True, support_ids=["E2.S1"], modality="image", pages=[1]),
    )


def test_gap_binding_keeps_hard_page_limit():
    from app.llm.quantity_state import QuantityGapSearch, QuantitySource

    active, _ = active_session()
    active.admit([block("A long candidate section", id="broad", page_number=2, page_end=6)])
    parent = missing_record().model_copy(update={"modality": "image"})
    selection = QuantitySource(available=True, support_ids=["E1.S1"], pages=[1], modality="image")
    gap = QuantityGapSearch(
        parent_id=parent.id,
        requirements=parent.assessments[-1].issues,
        query="Missing input",
        candidate_support_ids=["E2.S1"],
    )
    assert bind_gap_source(active, parent, selection, gap) is selection
    assert not fresh_source_view(active, parent, selection)


def test_gap_window_prioritizes_new_pages_over_reencoding_old_pages_and_keeps_checked_inputs():
    from app.llm.quantity_state import QuantityGapSearch, QuantitySource

    active, _ = active_session()
    for page in [2, 3, 7]:
        active.admit([block(f"Page {page} source", id=f"source-{page}", page_number=page)])
    parent = missing_record()
    first = parent.draft.operands[0].model_copy(update={"page": 1})
    parent = parent.model_copy(
        update={
            "support_ids": ["E1.S1", "E2.S1", "E3.S1"],
            "pages": [1, 2, 3],
            "modality": "text",
            "supported_operand_indexes": [0],
            "draft": parent.draft.model_copy(
                update={"operands": [first, parent.draft.operands[1]]}
            ),
        }
    )
    active.state.quantities[parent.id] = parent
    selection = QuantitySource(
        available=True,
        support_ids=parent.support_ids,
        pages=parent.pages,
        modality="image",
    )
    gap = QuantityGapSearch(
        parent_id=parent.id,
        requirements=parent.assessments[-1].issues,
        query="Missing input",
        candidate_support_ids=["E1.S1", "E4.S1"],
    )
    chosen = bind_gap_source(active, parent, selection, gap)
    assert chosen.pages == [1, 7]
    assert chosen.support_ids == ["E4.S1", "E1.S1"]
    assert active.state.quantities[parent.id] is parent
    assert parent.draft.operands[0].value == "3"
    assert fresh_source_view(active, parent, chosen)


def test_new_window_cannot_drop_a_checked_prerequisite_outside_its_limit():
    from app.llm.quantity_state import QuantityGapSearch, QuantitySource, SourceRange

    active, _ = active_session()
    active.admit([block("All prerequisites", id="wide", page_number=1, page_end=3)])
    active.admit([block("New missing input", id="new", page_number=7)])
    parent = missing_record()
    first = parent.draft.operands[0].model_copy(
        update={
            "source_ranges": [SourceRange(support_id="E2.S1", start_line=1, end_line=1)],
        }
    )
    parent = parent.model_copy(
        update={
            "support_ids": ["E2.S1"],
            "pages": [1, 2, 3],
            "modality": "image",
            "supported_operand_indexes": [0],
            "draft": parent.draft.model_copy(
                update={"operands": [first, parent.draft.operands[1]]}
            ),
        }
    )
    selection = QuantitySource(
        available=True,
        support_ids=parent.support_ids,
        pages=parent.pages,
        modality="image",
    )
    gap = QuantityGapSearch(
        parent_id=parent.id,
        requirements=parent.assessments[-1].issues,
        query="Missing input",
        candidate_support_ids=["E3.S1"],
    )
    assert bind_gap_source(active, parent, selection, gap) is selection


def test_a_checked_lookup_reaches_scope_review_with_its_original_sources():
    # MMLongBench 212: an accepted image lookup was left out of the projection,
    # so the scope check saw only the generated proof and could not ground the
    # question's population in the original page.
    from app.llm.quantities import candidate
    from app.llm.quantity_scope import semantic_scope_projection
    from app.llm.quantity_state import QuantityCheck
    from app.llm.scope_validation import scope_payload

    active, _ = active_session("a_one 20; a_two 30; a_output 80; b_one 25; b_two 35; b_output 70")
    draft = lookup()
    values, expression = execute(draft)
    record = missing_record().model_copy(
        update={
            "id": "lookup",
            "draft": draft,
            "assessments": [],
            "check": QuantityCheck(accepted=True, complete=True, reason="supported"),
            "execution_status": "completed",
            "values": values,
            "expression": expression,
        }
    )
    answer = candidate(record)
    payload = scope_payload(
        active.state.task.question, answer.raw_answer(), active.deps.ledger.units
    )
    projected, verified = semantic_scope_projection(payload, [record])
    assert verified == ["lookup"]
    operation = projected["verified_operations"][0]
    assert operation["operation"] == "lookup" and operation["source_support_ids"] == ["E1.S1"]
    assert [c["label"] for c in operation["choices"]] == ["A", "B"]
