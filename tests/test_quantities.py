"""Source bindings, deterministic results and checkpoints without provider calls."""

import hashlib
import json

import fitz
import pytest
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import ResearchClosed, finalize_research, run_adaptive_agent
from app.llm.agentic import AgentAnswer
from app.llm.answer_repair import AnswerPatch, AnswerRepair
from app.llm.quantities import candidate, collect, execute
from app.llm.quantity_state import QuantityCheck, QuantityDraft, QuantitySource
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import answer, deps, payload, reply, session


def arithmetic():
    return QuantityDraft.model_validate(
        {
            "mode": "arithmetic",
            "complete": True,
            "expression": "a + b",
            "decimals": 0,
            "operands": [
                {"name": "a", "label": "North", "value": "3", "witness": "North 3"},
                {"name": "b", "label": "South", "value": "7", "witness": "South 7"},
            ],
        }
    )


def enumeration():
    return QuantityDraft.model_validate(
        {
            "mode": "count",
            "complete": True,
            "groups": [
                {
                    "label": "Benefits",
                    "complete": True,
                    "boundary_witness": "Benefits until Risks on page 2",
                    "items": [
                        {"text": "Fast", "witness": "Fast", "page": 1, "position": 1},
                        {"text": "Reliable", "witness": "Reliable", "page": 1, "position": 2},
                        {"text": "Affordable", "witness": "Affordable", "page": 2, "position": 1},
                    ],
                }
            ],
        }
    )


def text_arithmetic():
    data = arithmetic().model_dump()
    for operand in data["operands"]:
        operand.update(
            witness="", source_ranges=[{"support_id": "E1.S1", "start_line": 1, "end_line": 2}]
        )
    return data


def active_session(text="North 3\nSouth 7", **kwargs):
    active = session(deps(text, question="What is the total?", derived_answers=True, **kwargs))
    need = active.state.add_need(
        EvidenceNeedSpec(
            description="Source inputs for total",
            operation="calculate",
            constraints=[NeedConstraint(dimension="metric", value="total", question_quote="total")],
        )
    )
    active.state.need_planning = "ready"
    return active, need.id


def fake_calls(active, draft=None, selection=None, check=None, interrupt=False):
    roles = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        roles.append(role)
        if role == "quantity_selector":
            return selection or QuantitySource(support_ids=["E1.S1"], available=True)
        if role == "quantity_collector":
            return draft or arithmetic()
        assert role == "quantity_checker"
        if interrupt:
            raise ResearchClosed("REQUEST_RESERVE")
        return check or QuantityCheck(accepted=True, complete=True, reason="supported")

    active.call = call
    return roles


def test_application_totals_inputs_without_model_result():
    assert execute(arithmetic()) == (["10"], "3 + 7")
    assert execute(enumeration()) == (["3"], "")
    bad = arithmetic().model_copy(update={"expression": "a + unknown"})
    with pytest.raises(ValueError, match="UNKNOWN_OPERAND"):
        execute(bad)
    for expression in ["__import__('os')", "a ** b", "a / (b-b)"]:
        with pytest.raises(ValueError):
            execute(arithmetic().model_copy(update={"expression": expression}))


def test_incomplete_and_duplicate_source_occurrences_are_not_counted():
    d = enumeration()
    with pytest.raises(ValueError, match="INCOMPLETE"):
        execute(d.model_copy(update={"complete": False}))
    group = d.groups[0]
    duplicate = group.model_copy(update={"items": [group.items[0], group.items[0]]})
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_OCCURRENCE"):
        execute(d.model_copy(update={"groups": [duplicate]}))
    # Identical printed labels at separate positions remain separate occurrences.
    repeated = group.model_copy(
        update={"items": [group.items[0], group.items[0].model_copy(update={"position": 2})]}
    )
    assert execute(d.model_copy(update={"groups": [repeated]}))[0] == ["2"]


@pytest.mark.asyncio
async def test_checked_inputs_are_retained_before_evidence_admission():
    active, need = active_session()
    fake_calls(active)
    active.deps.ledger._budget = active.deps.ledger._used
    result = await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert record.values == ["10"] and not record.proof_support_ids
    assert result.answer_parts[0].calculation.result == "10"
    # A checkpoint round-trip retains successful maths, not an LLM summary.
    restored = type(active.state).model_validate_json(active.state.model_dump_json())
    assert next(iter(restored.quantities.values())).values == ["10"]


@pytest.mark.asyncio
async def test_rejected_relationship_is_not_released_even_when_numbers_exist():
    active, need = active_session()
    fake_calls(active, check=QuantityCheck(accepted=False, complete=True, reason="wrong_binding"))
    assert await collect(active, need) is None
    record = next(iter(active.state.quantities.values()))
    assert not record.values and not record.proof_support_ids
    with pytest.raises(ValueError, match="NOT_CHECKED"):
        candidate(record)


@pytest.mark.asyncio
async def test_draft_survives_checker_budget_stop_without_becoming_evidence():
    active, need = active_session()
    fake_calls(active, interrupt=True)
    before = len(active.units())
    with pytest.raises(ResearchClosed, match="REQUEST_RESERVE"):
        await collect(active, need)
    record = next(iter(active.state.quantities.values()))
    assert record.check is None and not record.values and len(active.units()) == before


@pytest.mark.asyncio
async def test_fabricated_witness_and_unknown_support_never_reach_checker():
    active, need = active_session()
    roles = fake_calls(
        active,
        draft=arithmetic().model_copy(
            update={
                "operands": [
                    arithmetic().operands[0].model_copy(update={"witness": "Invented 3"}),
                    arithmetic().operands[1],
                ]
            }
        ),
    )
    with pytest.raises(ValueError, match="WITNESS_NOT_LITERAL"):
        await collect(active, need)
    assert "quantity_checker" not in roles
    active, need = active_session()
    fake_calls(active, selection=QuantitySource(support_ids=["E99.S1"], available=True))
    with pytest.raises(ValueError, match="UNKNOWN_OR_REVOKED"):
        await collect(active, need)


@pytest.mark.asyncio
async def test_finalization_reuses_successful_result_without_another_answer_model():
    active, need = active_session()
    fake_calls(active)
    await collect(active, need)
    active.state.research_stop = "RESEARCH_TURN_LIMIT"
    # fake_calls rejects any finalizer/reader call; saved arithmetic suffices.
    result, receipt = await finalize_research(active)
    assert result.answer_parts[0].text == "10" and receipt is None


@pytest.mark.asyncio
async def test_multipage_count_uses_original_images_and_continuation_items(tmp_path):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30, 30), "Benefits\nFast\nReliable")
        pdf.new_page().insert_text((30, 30), "Affordable\nRisks\nCost")
        pdf.save(path)
    active, need = active_session(
        "Benefits (continues)", visual_answers=True, render_page=PdfPages(str(tmp_path))
    )
    parent = active.deps.ledger.blocks[0]
    parent.payload.update(
        source_id="manual_pdf",
        page_end=2,
        document_version=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    active.deps.ledger.source_ids = frozenset({"manual_pdf"})
    seen = []

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(
                available=True, support_ids=["E1.S1"], modality="image", pages=[1, 2]
            )
        assert len(images) == 2 and all(x.startswith(b"\x89PNG") for x in images)
        assert data["physical_pages"] == [1, 2]
        seen.append(role)
        if role == "quantity_collector":
            return enumeration()
        return QuantityCheck(accepted=True, complete=True, reason="supported")

    active.call = call
    result = await collect(active, need)
    assert seen == ["quantity_collector", "quantity_checker"]
    assert result.answer_parts[0].text == "[3] (Benefits)"
    assert not active.deps.validation(result).failure_codes
    record = next(iter(active.state.quantities.values()))
    assert record.pages == [1, 2] and record.proof_support_ids
    # Tampering with the PDF invalidates versioned reads in a new session.
    path.write_bytes(path.read_bytes() + b" ")
    active.deps.pdf_structures.clear()
    with pytest.raises(Exception, match="VERSION_MISMATCH"):
        await collect(active, need)


def test_part_patch_cannot_overwrite_valid_claims():
    parts = AgentAnswer.model_validate(
        {
            "abstain": False,
            "answer_parts": [
                {"text": "North 3", "support_ids": ["E1.S1"]},
                {"text": "South 9", "support_ids": ["E1.S1"]},
            ],
        }
    ).answer_parts
    record = AnswerRepair(parts=parts, failed_indexes=[1], failure_codes=["CONFLICT"])
    patch = AnswerPatch.model_validate(
        {"replacements": [{"index": 1, "part": {"text": "South 7", "support_ids": ["E1.S1"]}}]}
    )
    assert record.apply(patch)[0] is parts[0]
    with pytest.raises(ValueError, match="ONLY_FAILED"):
        record.apply(
            patch.model_copy(
                update={"replacements": [patch.replacements[0].model_copy(update={"index": 0})]}
            )
        )


@pytest.mark.asyncio
async def test_partial_validation_repairs_only_failed_claim_and_revalidates():
    active, _ = active_session()
    roles = []

    def model(messages, info):
        data = payload(messages)
        assert data["repair"]["failed_indexes"] == [1]
        roles.append("patch")
        return reply(
            info,
            {"replacements": [{"index": 1, "part": {"text": "South 7", "support_ids": ["E1.S1"]}}]},
        )

    active.model = FunctionModel(model)
    initial = AgentAnswer.model_validate(
        {
            "abstain": False,
            "answer_parts": [
                {"text": "North 3", "support_ids": ["E1.S1"]},
                {"text": "South 99", "support_ids": ["E1.S1"]},
            ],
        }
    )
    result, _ = await active.verify(initial)
    assert roles == ["patch"] and result.answer_parts[0] is initial.answer_parts[0]
    assert result.answer_parts[1].text == "South 7"
    assert len(active.state.answer_repairs) == 1


@pytest.mark.asyncio
async def test_plain_text_success_does_not_invoke_quantity_collection():
    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "pages" not in props and "mode" not in props
        if "missing" in props:
            return reply(
                info,
                {
                    "answer": {
                        "answer_parts": [
                            {"text": "The service uses TLS.", "support_ids": ["E1.S1"]}
                        ]
                    }
                },
            )
        return reply(info, {"action": "answer", "answer": answer()})

    result = await run_adaptive_agent(FunctionModel(model), deps(), fast_path=True)
    assert result.failure_code is None and result.telemetry["tool_calls"] == 0


@pytest.mark.asyncio
async def test_failed_fast_answer_dispatches_typed_collection_then_application_answer():
    from app.llm.research_state import ResearchState, TaskSpec

    dependencies = deps("North 3\nSouth 7", question="What is the total?", derived_answers=True)
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="ready")
    state.add_need(
        EvidenceNeedSpec(
            description="Total",
            operation="calculate",
            constraints=[NeedConstraint(dimension="metric", value="total", question_quote="total")],
        )
    )
    seen = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "missing" in props:
            seen.append("fast")
            return reply(
                info, {"answer": {"answer_parts": [{"text": "999", "support_ids": ["E1.S1"]}]}}
            )
        if "modality" in props:
            seen.append("select")
            return reply(
                info, {"available": True, "support_ids": ["E1.S1"], "context_support_ids": []}
            )
        if "operands" in props:
            seen.append("collect")
            return reply(info, text_arithmetic())
        if "inputs" in props:
            seen.append("check")
            return reply(
                info, {"inputs": "supported", "coverage": "complete", "operation": "supported"}
            )
        pytest.fail(
            f"Unexpected model call; seen={seen}; needs={state.needs}; stop={state.research_stop}"
        )

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert seen == ["fast", "select", "collect", "check"]
    assert result.failure_code is None and json.loads(result.raw)["answer_parts"][0]["text"] == "10"
    assert result.telemetry["tool_calls"] == 1


@pytest.mark.asyncio
async def test_collection_rechecks_authorization_after_model_call():
    active, need = active_session()

    async def call(role, output_type, instructions, data, *, research, images=None):
        if role == "quantity_selector":
            return QuantitySource(support_ids=["E1.S1"], available=True)
        if role == "quantity_collector":
            active.deps.ledger.blocks[0].payload["tenant_id"] = "different-tenant"
            return arithmetic()
        pytest.fail("Revoked input must not reach checker or application math")

    active.call = call
    with pytest.raises(ValueError, match="UNKNOWN_OR_REVOKED"):
        await collect(active, need)
    assert not active.state.quantities


@pytest.mark.asyncio
async def test_count_requests_inventory_before_fast_answer_and_checks_completeness():
    from app.llm.research_state import ResearchState, TaskSpec

    dependencies = deps(
        "Benefits: Fast, Reliable", question="How many benefits?", derived_answers=True
    )
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="ready")
    state.add_need(
        EvidenceNeedSpec(
            description="Count benefits",
            operation="count",
            constraints=[
                NeedConstraint(dimension="metric", value="benefits", question_quote="benefits")
            ],
        )
    )
    seen = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        assert "missing" not in props, "A subset count must not bypass inventory validation"
        if "modality" in props and "available" in props:
            seen.append("select")
            return reply(
                info, {"available": True, "support_ids": ["E1.S1"], "context_support_ids": []}
            )
        if "operands" in props:
            seen.append("collect")
            return reply(
                info,
                {
                    "mode": "count",
                    "complete": True,
                    "groups": [
                        {
                            "label": "Benefits",
                            "complete": True,
                            "boundary_witness": "",
                            "boundary_ranges": [
                                {"support_id": "E1.S1", "start_line": 1, "end_line": 1}
                            ],
                            "items": [
                                {
                                    "text": "Fast",
                                    "witness": "",
                                    "position": 1,
                                    "source_ranges": [
                                        {"support_id": "E1.S1", "start_line": 1, "end_line": 1}
                                    ],
                                },
                                {
                                    "text": "Reliable",
                                    "witness": "",
                                    "position": 2,
                                    "source_ranges": [
                                        {"support_id": "E1.S1", "start_line": 1, "end_line": 1}
                                    ],
                                },
                            ],
                        }
                    ],
                },
            )
        if "inputs" in props:
            seen.append("check")
            return reply(
                info, {"inputs": "supported", "coverage": "complete", "operation": "supported"}
            )
        pytest.fail("No answer model required after successful inventory")

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert seen == ["select", "collect", "check"]
    assert result.failure_code is None
    assert json.loads(result.raw)["answer_parts"][0]["text"] == "[2] (Benefits)"


@pytest.mark.parametrize(
    "count_mode, expected", [("per_group", ["3", "2"]), ("total", ["5"]), ("distinct", ["3"])]
)
def test_category_counts_total_and_unique_union_are_different_operations(count_mode, expected):
    first = enumeration().groups[0]
    second = first.model_copy(update={"label": "Other", "items": first.items[:2]})
    draft = enumeration().model_copy(update={"groups": [first, second], "count_mode": count_mode})
    assert execute(draft)[0] == expected


@pytest.mark.asyncio
async def test_aggregate_count_is_computed_and_validated_from_source_item_counts():
    active, need = active_session("North: Fast Reliable\nSouth: Affordable")
    draft = QuantityDraft.model_validate(
        {
            "mode": "count",
            "count_mode": "total",
            "complete": True,
            "groups": [
                {
                    "label": "North",
                    "complete": True,
                    "boundary_witness": "North: Fast Reliable",
                    "items": [
                        {"text": "Fast", "witness": "Fast", "position": 1},
                        {"text": "Reliable", "witness": "Reliable", "position": 2},
                    ],
                },
                {
                    "label": "South",
                    "complete": True,
                    "boundary_witness": "South: Affordable",
                    "items": [{"text": "Affordable", "witness": "Affordable", "position": 1}],
                },
            ],
        }
    )
    fake_calls(active, draft=draft)
    result = await collect(active, need)
    assert result.answer_parts[0].text == "3"
    assert not active.deps.validation(result).failure_codes
    # A later model cannot detach the proof from its original source.
    proof = next(iter(active.state.quantities.values())).proof_support_ids
    detached = result.model_copy(
        update={"answer_parts": [result.answer_parts[0].model_copy(update={"support_ids": proof})]}
    )
    verified, _ = await active.verify(detached)
    assert "E1.S1" in verified.answer_parts[0].support_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("page, accepted", [(1, True), (2, False)])
async def test_text_page_provenance_is_allowed_without_requesting_images(page, accepted):
    active, need = active_session()
    roles = fake_calls(
        active,
        selection=QuantitySource(
            available=True, support_ids=["E1.S1"], pages=[page], modality="text"
        ),
    )
    if accepted:
        result = await collect(active, need)
        assert result.answer_parts[0].text == "10"
        assert next(iter(active.state.quantities.values())).pages == [1]
        assert roles == ["quantity_selector", "quantity_collector", "quantity_checker"]
    else:
        with pytest.raises(ValueError, match="PAGE_OUTSIDE_SOURCE"):
            await collect(active, need)
        assert roles == ["quantity_selector"]


def test_application_resolves_text_references_without_model_quote_copying():
    from app.llm.quantities import resolve_draft
    from app.llm.quantity_state import SourceRange

    source = "North 3\nSouth 7"
    draft = arithmetic().model_copy(
        update={
            "operands": [
                o.model_copy(
                    update={
                        "witness": "...",
                        "source_ranges": [
                            SourceRange(support_id="E1.S1", start_line=1, end_line=2)
                        ],
                    }
                )
                for o in arithmetic().operands
            ]
        }
    )
    resolved = resolve_draft(draft, {"E1.S1": source})
    assert all(o.witness == source for o in resolved.operands)
    assert execute(resolved)[0] == ["10"]
    bad = draft.operands[0].model_copy(
        update={"source_ranges": [SourceRange(support_id="E99.S1", start_line=1, end_line=1)]}
    )
    with pytest.raises(ValueError, match="REFERENCE_OUTSIDE_SOURCE"):
        resolve_draft(
            draft.model_copy(update={"operands": [bad, draft.operands[1]]}), {"E1.S1": source}
        )


def test_text_collection_schema_cannot_return_a_shortened_quotation():
    from pydantic import ValidationError

    from app.llm.quantity_state import TextQuantityDraft

    data = text_arithmetic()
    assert TextQuantityDraft.model_validate(data).operands[0].witness == ""
    data["operands"][0]["witness"] = "North ... 3"
    with pytest.raises(ValidationError):
        TextQuantityDraft.model_validate(data)


@pytest.mark.asyncio
async def test_question_driven_collection_survives_invalid_optional_plan():
    from app.llm.research_state import ResearchState, TaskSpec

    dependencies = deps("North 3\nSouth 7", question="What is the total?", derived_answers=True)
    state = ResearchState(task=TaskSpec(question=dependencies.question), need_planning="failed")
    seen = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "missing" in props:
            return reply(info, {"answer": None, "missing": ["Need to total source inputs"]})
        if "available" in props:
            assert payload(messages)["need"] is None
            assert payload(messages)["question"] == dependencies.question
            seen.append("select")
            return reply(
                info, {"available": True, "support_ids": ["E1.S1"], "context_support_ids": []}
            )
        if "operands" in props:
            seen.append("inputs")
            return reply(info, text_arithmetic())
        if "inputs" in props:
            seen.append("check")
            return reply(
                info, {"inputs": "supported", "coverage": "complete", "operation": "supported"}
            )
        pytest.fail("No need-plan repair or answer rewriting is required")

    result = await run_adaptive_agent(
        FunctionModel(model), dependencies, state=state, fast_path=True
    )
    assert result.failure_code is None and seen == ["select", "inputs", "check"]
    assert json.loads(result.raw)["answer_parts"][0]["text"] == "10"
    assert state.need_planning == "failed" and not state.evidence_needs
