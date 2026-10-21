"""Checked arithmetic, notation repair and relationship uncertainty are distinct."""

import copy
import json
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.evidence.documents import DocumentResult
from app.llm.quantities import bounded_context, candidate, collect, execute
from app.llm.quantity_contracts import collection_contract
from app.llm.quantity_numbers import apply_notation_corrections, normalize_inputs
from app.llm.quantity_scope import semantic_scope_projection
from app.llm.quantity_sources import complete_sources, relationship_context
from app.llm.quantity_state import (
    QuantityAssessment,
    QuantityCheck,
    QuantityDraft,
    QuantityNumericOperand,
)
from app.llm.scope_diagnostics import DiagnosticScopeJudgment
from app.llm.scope_validation import scope_payload
from tests.test_adaptive import block
from tests.test_quantities import active_session, fake_calls
from tests.test_quantity_completion import lookup, missing_record


def supported(**extra):
    return QuantityAssessment(
        inputs="supported", coverage="complete", operation="supported", **extra
    )


def invalid_notation():
    return QuantityDraft(
        mode="arithmetic",
        complete=True,
        expression="a + b",
        decimals=0,
        operands=[
            dict(name="a", label="A", value="4,321", number_format="canonical", unit="items"),
            dict(name="b", label="B", value="7", number_format="canonical", unit="items"),
        ],
    )


def test_source_reviewer_corrects_only_invalid_notation_without_value_or_formula_changes():
    original = invalid_notation()
    review = supported(notation_corrections=[dict(index=0, number_format="decimal_point")])
    repaired = apply_notation_corrections(original, review)
    assert normalize_inputs(original)[0].errors == ["NUMERIC_NOTATION_INVALID"]
    assert execute(repaired)[0] == ["4328"]
    assert repaired.operands[0].value == original.operands[0].value
    assert repaired.expression == original.expression
    assert original.operands[0].number_format == "canonical"
    assert apply_notation_corrections(repaired, review) == repaired


@pytest.mark.parametrize(
    "changes",
    [
        [dict(index=2, number_format="decimal_point")],
        [dict(index=0, number_format="decimal_point")] * 2,
        [dict(index=0, number_format="space_grouped")],
    ],
)
def test_invalid_notation_correction_never_executes(changes):
    with pytest.raises(ValueError):
        apply_notation_corrections(invalid_notation(), supported(notation_corrections=changes))


def test_review_cannot_reinterpret_an_already_valid_numeric_display():
    draft = invalid_notation()
    draft = draft.model_copy(
        update={
            "operands": [
                draft.operands[0].model_copy(update={"number_format": "decimal_comma"}),
                draft.operands[1],
            ]
        }
    )
    with pytest.raises(ValueError, match="ALREADY_VALID"):
        apply_notation_corrections(
            draft, supported(notation_corrections=[dict(index=0, number_format="decimal_point")])
        )


@pytest.mark.asyncio
async def test_notation_metadata_correction_uses_existing_checker_and_checkpoints_receipt():
    active, need = active_session(text="A 4,321\nB 7")
    seen = []

    async def call(role, output_type, instructions, data, **kwargs):
        seen.append(role)
        if role == "quantity_selector":
            return output_type(
                available=True, support_ids=["E1.S1"], context_support_ids=[], modality="text"
            )
        if role == "quantity_collector":
            draft = invalid_notation().model_dump(
                include={
                    "mode",
                    "complete",
                    "expression",
                    "decimals",
                    "result_unit",
                    "interpretation",
                    "operands",
                }
            )
            for index, operand in enumerate(draft["operands"], 1):
                for key in ("witness", "page", "image_ids"):
                    operand.pop(key, None)
                operand["source_ranges"] = [
                    dict(support_id="E1.S1", start_line=index, end_line=index)
                ]
            return output_type.model_validate(draft)
        assert role == "quantity_checker" and data["numeric_inputs"][0]["errors"]
        return supported(notation_corrections=[dict(index=0, number_format="decimal_point")])

    active.call = call
    result = await collect(active, need)
    assert result.answer_parts[0].calculation.result == "4328"
    assert seen == ["quantity_selector", "quantity_collector", "quantity_checker"]
    record = next(iter(active.state.quantities.values()))
    assert record.numeric_inputs[0].canonical_value == "4321"
    assert record.draft.operands[0].value == "4,321"


def test_ambiguous_display_survives_schema_but_never_executes():
    wire = collection_contract("arithmetic", [], ["source"])
    result = wire.model_validate(
        dict(
            mode="arithmetic",
            complete=False,
            expression="a",
            decimals=0,
            result_unit="items",
            interpretation="Uncertain digit",
            operands=[
                dict(
                    name="a",
                    label="A",
                    value="12",
                    value_status="ambiguous",
                    unit="items",
                    source_ranges=[dict(support_id="source", start_line=1, end_line=1)],
                )
            ],
        )
    )
    assert result.operands[0].value == "12"
    draft = QuantityDraft(
        mode="arithmetic",
        complete=True,
        expression="a",
        operands=[
            QuantityNumericOperand(name="a", label="A", value="12", value_status="ambiguous")
        ],
    )
    assert normalize_inputs(draft)[0].value_status == "ambiguous"
    with pytest.raises(ValueError, match="UNRESOLVED"):
        execute(draft)


def test_readable_lookup_cell_cannot_execute_an_unknown_entity_join():
    draft = lookup()
    operands = [o.model_dump() for o in draft.operands]
    for operand in operands:
        operand["binding_status"] = "unknown"
    draft = QuantityDraft.model_validate({**draft.model_dump(), "operands": operands})
    assert all(o.value is not None for o in draft.operands)
    with pytest.raises(ValueError, match="ENTITY_BINDING_UNRESOLVED"):
        execute(draft)


@pytest.mark.asyncio
async def test_relationship_gap_search_is_scoped_and_does_not_certify_aliases():
    active, _ = active_session()
    parent = missing_record()
    parent.assessments[0].issues[0] = (
        parent.assessments[0]
        .issues[0]
        .model_copy(
            update={
                "kind": "wrong_binding",
                "evidence_kind": "entity_inventory",
                "needed_evidence": "Source relationship between Dataset-Q and Dataset-Q-small",
            }
        )
    )
    queries = []

    async def read(request):
        queries.append(request)
        return DocumentResult(
            blocks=[block("Dataset-Q-small is the textual subset.", id="definition")],
            outline=[],
            has_more=False,
        )

    active.deps.documents = SimpleNamespace(read=read)
    receipt = await complete_sources(active, parent)
    assert queries[0].document.document_version == parent.document_version
    assert "Dataset-Q-small" in queries[0].query
    assert receipt.status == "located" and receipt.candidate_support_ids
    assert not parent.check  # Finding a relationship passage is not its certification.


@pytest.mark.asyncio
async def test_only_exact_checked_application_result_gets_semantic_projection():
    active, need = active_session()
    fake_calls(active)
    answer = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    original = scope_payload(
        active.state.task.question, answer.raw_answer(), active.deps.ledger.units
    )
    saved = copy.deepcopy(original)
    projected, ids = semantic_scope_projection(original, [record])
    assert ids == [record.id] and original == saved
    assert "calculation" not in projected["claims"][0]["claim"]
    assert projected["claims"][0]["claim"]["text"] == original["claims"][0]["claim"]["text"]
    assert all(
        u["support_unit_id"] not in record.proof_support_ids
        for u in projected["claims"][0]["cited_evidence"]
    )
    assert projected["verified_operations"][0]["formula"] == "a + b"
    for changed in [
        record.model_copy(update={"values": ["11"]}),
        record.model_copy(update={"expression": "3 * 7"}),
        record.model_copy(update={"execution_status": "pending"}),
        record.model_copy(update={"draft": record.draft.model_copy(update={"result_unit": "km"})}),
    ]:
        assert semantic_scope_projection(original, [changed]) == (original, [])
    mutated = copy.deepcopy(original)
    mutated["claims"][0]["claim"]["text"] += " invented context"
    assert semantic_scope_projection(mutated, [record]) == (mutated, [])


@pytest.mark.asyncio
@pytest.mark.parametrize("reject", [False, True])
async def test_semantic_projection_still_needs_positive_scope_and_original_release_fingerprint(
    reject,
):
    active, need = active_session(scope_validation_enabled=True)
    active.compact_context = True
    fake_calls(active)
    answer = await collect(active, need)

    async def scope(role, output_type, instructions, data, **kwargs):
        assert role == "scope_validator" and data["verified_operations"]
        assert "calculation" not in data["claims"][0]["claim"]
        assert data["claims"][0]["claim"]["text"] == answer.answer_parts[0].text
        if reject:
            return DiagnosticScopeJudgment.model_validate(
                dict(
                    checks=[dict(claim_index=0, verdict="mismatch", reason="PERIOD_MISMATCH")],
                    objections=[
                        dict(
                            claim_index=0,
                            description="Wrong period",
                            question_start=1,
                            question_end=1,
                            source_locations=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                        )
                    ],
                )
            )
        return DiagnosticScopeJudgment.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[dict(support_id="E1.S1", start_line=1, end_line=1)],
                    )
                ]
            )
        )

    active.call = scope
    if reject:
        with pytest.raises(ValueError, match="PERIOD_MISMATCH"):
            await active.verify(answer)
    else:
        result, receipt = await active.verify(answer)
        assert receipt.accepts(
            active.state.task.question, result.raw_answer(), active.deps.ledger.units
        )
        changed = candidate(next(iter(active.state.quantities.values())))
        changed.answer_parts[0].text += " unsupported"
        assert not receipt.accepts(
            active.state.task.question, changed.raw_answer(), active.deps.ledger.units
        )


def test_rounding_control_uses_decimal_authority():
    value = Decimal("27123") / Decimal("38917")
    assert value.quantize(Decimal("0.001")) == Decimal("0.697")


def test_required_context_survives_full_prior_closure_and_large_search_hits():
    active, _ = active_session()
    unit = active.units()["E1.S1"]
    units = {"required": replace(unit, text="Requested relationship page")}
    units.update({f"old{i}": replace(unit, text=f"Prior closure {i}") for i in range(6)})
    units["large"] = replace(unit, text="x" * 6000)
    ids = bounded_context(["required"], ["large", *[f"old{i}" for i in range(6)]], units)
    assert ids[0] == "required" and "large" not in ids and len(ids) == 6
    with pytest.raises(ValueError, match="REQUIRED_CONTEXT_TOO_LARGE"):
        bounded_context(["required", "large"], [], units)


def test_local_relationship_context_finds_definitions_but_does_not_assert_equivalence():
    active, _ = active_session()
    parent = missing_record()
    parent.assessments[0].issues[0] = (
        parent.assessments[0]
        .issues[0]
        .model_copy(
            update={
                "kind": "wrong_binding",
                "evidence_kind": "entity_inventory",
                "needed_evidence": "A definition relating DataAlpha and DataAlpha-Small",
            }
        )
    )
    unit = active.units()["E1.S1"]
    definition = replace(unit, text="We call the selected DataAlpha subset DataAlpha-Small.")
    distinction = replace(
        unit, text="DataAlpha-Small is a subset; DataAlpha also includes other cases."
    )
    units = {
        "definition": definition,
        "distinction": distinction,
        "table": replace(unit, text="DataAlpha-Small 55.1"),
        "foreign": replace(definition, document_version="other"),
        "hidden": replace(definition, model_visible=False),
        "denied": replace(definition, authorized=False),
    }
    assert set(relationship_context(parent, units)) == {"definition", "distinction"}
    assert parent.check is None
    # Optional model diagnostic tags cannot disable lookup relationship recovery.
    parent = parent.model_copy(update={"draft": lookup()})
    parent.assessments[0].issues[0] = (
        parent.assessments[0].issues[0].model_copy(update={"evidence_kind": "unspecified"})
    )
    assert set(relationship_context(parent, units)) == {"definition", "distinction"}


@pytest.mark.asyncio
async def test_lookup_relationship_dispatch_does_not_depend_on_model_tag_or_selector_approval():
    draft = lookup()
    active, need = active_session(text="\n".join(f"{o.label} {o.value}" for o in draft.operands))
    active.deps.ledger.add(
        [block("We call the DataAlpha subset DataAlpha-Small.", id="definition")]
    )
    parent = missing_record().model_copy(update={"draft": draft})
    parent.assessments[0].issues[0] = (
        parent.assessments[0]
        .issues[0]
        .model_copy(
            update={
                "kind": "wrong_binding",
                "evidence_kind": "unspecified",
                "index": 5,
                "needed_evidence": "A definition relating DataAlpha and DataAlpha-Small",
            }
        )
    )
    parent.assessments[0] = parent.assessments[0].model_copy(
        update={
            "inputs": "unknown",
            "coverage": "complete",
            "operation": "supported",
        }
    )
    seen = []

    async def call(role, output_type, instructions, data, **kwargs):
        seen.append(role)
        assert role != "quantity_selector"
        assert any("DataAlpha-Small" in json.dumps(source) for source in data["context_sources"])
        if role == "quantity_checker":
            return supported(entity_identity="supported")
        raw = dict(
            mode="lookup",
            complete=True,
            operands=[
                dict(
                    name=o.name,
                    label=o.label,
                    value=o.value,
                    unit=o.unit,
                    number_format="canonical",
                    population="",
                    series="",
                    period="",
                    source_ranges=[dict(support_id="E1.S1", start_line=i, end_line=i)],
                )
                for i, o in enumerate(draft.operands, 1)
            ],
        )
        return output_type.model_validate(raw)

    active.call = call
    result = await collect(active, need, parent=parent, repairs_left=0)
    assert "70" in result.answer_parts[0].text
    assert seen == ["quantity_collector", "quantity_checker"]
    assert next(iter(active.state.quantities.values())).context_support_ids == ["E2.S1"]


def test_requested_lookup_precision_changes_only_published_display():
    draft = lookup()
    operands = [
        o.model_copy(update={"value": "70.26"}) if o.name == "b_output" else o
        for o in draft.operands
    ]
    draft = draft.model_copy(update={"operands": operands, "output_decimals": 1})
    values, expression = execute(draft)
    record = missing_record().model_copy(
        update={
            "draft": draft,
            "values": values,
            "expression": expression,
            "execution_status": "completed",
            "check": QuantityCheck(accepted=True, complete=True, reason="supported"),
        }
    )
    assert candidate(record).answer_parts[0].text == "70.3 %"
    assert record.values == ["70.26"] and record.draft.operands[-1].value == "70.26"
    unrounded = record.model_copy(
        update={"draft": draft.model_copy(update={"output_decimals": None})}
    )
    assert candidate(unrounded).answer_parts[0].text == "70.26 %"
