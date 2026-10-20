"""Negative evidence cannot replace missing coverage or discard successful work."""

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import (
    ResearchClosed,
    ResearchDecision,
    finalize_research,
    run_adaptive_agent,
)
from app.llm.agentic import AgentCandidate
from app.llm.quantities import checkpoint_review_evidence
from app.llm.quantity_numbers import normalize_inputs
from app.llm.quantity_state import QuantityAssessment, QuantityDraft, QuantityRecord
from app.llm.research_dispositions import (
    DispositionJudgment,
    DispositionProposal,
    ReviewedDisposition,
    admit_disposition,
    disposition_text,
)
from app.llm.research_state import ResearchState, TaskSpec
from app.llm.structured_output import stream_support_unit_answer
from tests.test_adaptive import answer, block, deps, payload, reply, session

QUESTION = "What is the 2020 observation?"
SOURCE = "Observations\n2013: 42\nEnd of observations"


def reviewed(kind="source_conflict", **updates):
    proposal = DispositionProposal(
        kind=kind,
        question_quote="2020",
        requested="the 2020 observation",
        source_object="observations table",
        scope="bounded_object",
        witnesses=[dict(support_id="E1.S1", quote="2013: 42", page=1)],
        boundaries=[dict(support_id="E1.S1", quote="End of observations", page=1)],
    ).model_copy(update=updates)
    return ReviewedDisposition(
        proposal=proposal,
        judgment=DispositionJudgment(
            question_binding="supported",
            object_identity="supported",
            scope_complete=True,
            alternatives_excluded=True,
        ),
    )


def active():
    return session(deps(SOURCE, question=QUESTION))


def receipt_for(active, value=None, **kwargs):
    return admit_disposition(value or reviewed(), QUESTION, active.units(), **kwargs)


def test_bound_reason_preserves_real_source_identity_and_exact_witness():
    receipt = receipt_for(active())
    assert receipt.verified and receipt.kind == "source_conflict"
    assert receipt.evidence[0].source_id == "manual"
    assert receipt.evidence[0].document_version == "v1"
    text = disposition_text(receipt)
    assert "2013: 42" in text and "2020" in text and "scope" in text


@pytest.mark.parametrize(
    "change",
    [
        {"question_binding": "unknown"},
        {"object_identity": "unknown"},
        {"scope_complete": False},
        {"alternatives_excluded": False},
        {"material_answer_available": True},
        {"remaining_candidates": ["E2.S1"]},
    ],
)
def test_uncertain_or_answerable_review_cannot_certify_absence(change):
    value = reviewed("not_reported_in_scope")
    value = value.model_copy(update={"judgment": value.judgment.model_copy(update=change)})
    receipt = receipt_for(active(), value)
    assert not receipt.verified and receipt.kind == "insufficient_evidence"
    assert disposition_text(receipt) is None


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "document"},
        {"scope": "inspected_material"},
        {"boundaries": []},
        {"question_quote": "unasked constraint"},
        {"question_quote": " "},
    ],
)
def test_local_read_or_unbound_question_cannot_be_promoted_to_closed_source(change):
    assert not receipt_for(active(), reviewed(**change)).verified


@pytest.mark.parametrize(
    "support,page,quote",
    [
        ("E99.S1", 1, "2013: 42"),
        ("E1.S1", 2, "2013: 42"),
        ("E1.S1", 1, "invented value"),
        ("E1.S1", 1, " "),
    ],
)
def test_witness_must_bind_to_an_available_source_and_actual_page(support, page, quote):
    value = reviewed().proposal.model_dump()
    value["witnesses"] = [dict(support_id=support, page=page, quote=quote)]
    r = reviewed().model_copy(update={"proposal": DispositionProposal.model_validate(value)})
    assert not receipt_for(active(), r).verified


def test_unread_candidate_prevents_strong_negative_even_after_checker_approval():
    receipt = receipt_for(active(), pending_support_ids=["continuation"])
    assert receipt.pending_support_ids == ["continuation"] and not receipt.verified


def test_image_witness_requires_that_exact_immutable_page_in_the_checker_input():
    value = reviewed().proposal.model_dump()
    value["witnesses"][0]["quote"] = "Visible table heading missing from parser"
    r = reviewed().model_copy(update={"proposal": DispositionProposal.model_validate(value)})
    assert not receipt_for(active(), r).verified
    assert not receipt_for(active(), r, image_pages={("manual", "other", 1)}).verified
    receipt = receipt_for(active(), r, image_pages={("manual", "v1", 1)})
    assert receipt.verified
    assert receipt.evidence[0].authority == "independently_checked_image"


def test_receipt_does_not_survive_new_evidence_or_changed_authorization():
    a = active()
    a.state.source_dispositions.append(receipt_for(a))
    assert a.current_disposition() is not None
    a.deps.ledger.add([block("2020: 71", id="continuation", page_number=2)])
    assert a.current_disposition() is None
    # The immutable receipt is retained for audit instead of being rewritten.
    assert a.state.source_dispositions[0].verified


def test_known_success_remains_authoritative_over_a_negative_receipt():
    a = active()
    a.state.source_dispositions.append(receipt_for(a))
    from tests.test_research_state import prepared

    ready, plan = prepared()
    a.state.computations.update({"ready": ready.calculate(plan)})
    assert a.current_disposition() is None


def test_disposition_is_only_a_stop_proposal_and_not_a_tool_argument():
    proposal = reviewed().proposal
    with pytest.raises(ValidationError):
        ResearchDecision(action="search", query="2020", disposition=proposal)
    decision = ResearchDecision(action="stop", disposition=proposal)
    assert decision.tool_arguments() == {}


@pytest.mark.asyncio
async def test_verified_reason_finalizes_without_another_model_request():
    a = active()
    a.state.source_dispositions.append(receipt_for(a))

    async def forbidden(*args, **kwargs):
        raise AssertionError("Already checked reason must not ask a finalizer")

    a.call = forbidden
    a.state.research_stop = "TOOL_ATTEMPT_LIMIT"
    result, scope = await finalize_research(a)
    assert result.abstain and scope is None
    assert a.state.source_dispositions[0].verified
    assert a.state.terminal_assessments[-1].outcome == "source_conflict"


@pytest.mark.asyncio
async def test_reader_abstention_does_not_open_another_finalizer_or_review_loop():
    calls = []

    def model(messages, info):
        calls.append(1)
        return reply(info, {"action": "answer", "answer": {"abstain": True}})

    result = await run_adaptive_agent(FunctionModel(model), deps(SOURCE, question=QUESTION))
    assert len(calls) == 1 and result.failure_code is None
    assert json.loads(result.raw)["abstain"]


def test_an_independently_checked_partial_fact_does_not_imply_the_question_is_answered():
    from app.llm.research_state import DataExtraction, EvidenceRef, ObservedValue

    a = active()
    a.state.add_facts(
        DataExtraction(values=[ObservedValue(category="2013", value="42", witness="2013: 42")]),
        EvidenceRef(support_id="E1.S1", source_id="manual", document_version="v1"),
        "text_witness",
    )
    a.state.source_dispositions.append(receipt_for(a))
    # The question asks for 2020; one retained 2013 observation is not its answer.
    assert a.state.facts and a.current_disposition() is not None


@pytest.mark.asyncio
async def test_unavailable_finalization_preserves_partial_work_without_a_review_loop():
    a = active()
    record = partial_record().model_copy(update={"supported_operand_indexes": [0]})
    a.state.quantities[record.id] = record
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        assert kwargs["research"] is False
        raise ResearchClosed("REQUEST_RESERVE")

    a.call = call
    answer, receipt = await finalize_research(a)
    assert answer.abstain and receipt is None and calls == ["finalizer"]
    assert a.state.quantities[record.id] == record
    terminal = a.state.terminal_assessments[-1]
    assert terminal.outcome == "insufficient_evidence"
    assert terminal.partial_quantity_ids == [record.id]
    assert terminal.diagnostic_errors == ["REQUEST_RESERVE"]


@pytest.mark.asyncio
async def test_reader_proposal_uses_one_independent_check_and_no_finalizer():
    roles = []

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "action" in props:
            roles.append("reader")
            return reply(info, dict(action="stop", disposition=reviewed().proposal.model_dump()))
        assert "object_identity" in props
        roles.append("checker")
        data = payload(messages)
        assert data["disposition_evidence"][0]["text"] == SOURCE
        return reply(info, reviewed().judgment.model_dump())

    state = ResearchState(task=TaskSpec(question=QUESTION))
    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(SOURCE, question=QUESTION),
        state=state,
    )
    assert roles == ["reader", "checker"]
    assert result.source_disposition.verified
    assert state.research_stop == "VERIFIED_SOURCE_DISPOSITION"
    assert json.loads(result.raw)["abstain"]


@pytest.mark.asyncio
async def test_rejected_early_absence_keeps_research_open_for_later_observation():
    roles = []

    async def retrieve(query):
        return [block("2020: 71", id="later", page_number=2)]

    def model(messages, info):
        props = info.output_tools[0].parameters_json_schema["properties"]
        if "object_identity" in props:
            roles.append("checker")
            return reply(
                info,
                reviewed()
                .judgment.model_copy(
                    update={
                        "scope_complete": False,
                        "alternatives_excluded": False,
                        "remaining_candidates": ["unread continuation"],
                    }
                )
                .model_dump(),
            )
        data = payload(messages)
        if not roles:
            roles.append("early stop")
            return reply(info, dict(action="stop", disposition=reviewed().proposal.model_dump()))
        if roles[-1] == "checker":
            roles.append("search")
            assert "insufficient_evidence" in str(data["source_dispositions"])
            return reply(info, dict(action="search", query="2020 observation"))
        roles.append("answer")
        return reply(info, dict(action="answer", answer=answer("2020: 71", "E2.S1")))

    state = ResearchState(task=TaskSpec(question=QUESTION))
    result = await run_adaptive_agent(
        FunctionModel(model),
        deps(SOURCE, question=QUESTION, retrieve=retrieve),
        state=state,
    )
    assert roles == ["early stop", "checker", "search", "answer"]
    assert "71" in result.raw and not json.loads(result.raw)["abstain"]
    assert result.source_disposition is None


def partial_record():
    draft = QuantityDraft.model_validate(
        dict(
            mode="arithmetic",
            complete=False,
            expression="a - b",
            operands=[
                dict(
                    name="a",
                    label="Company A tweets",
                    value="24",
                    unit="tweets",
                    witness="Company A 24",
                ),
                dict(
                    name="b",
                    label="Company B tweets",
                    value=None,
                    value_status="not_found",
                    unit="tweets",
                    witness="No Company B row",
                ),
            ],
        )
    )
    return QuantityRecord(
        id="partial",
        need_id="",
        support_ids=["E1.S1"],
        source_id="manual",
        document_version="v1",
        pages=[1],
        modality="text",
        draft=draft,
        numeric_inputs=normalize_inputs(draft),
    )


def test_partial_operand_is_retained_and_exposed_without_executing_missing_formula():
    a = active()
    record = partial_record()
    review = QuantityAssessment(
        inputs="unknown",
        coverage="incomplete",
        operation="supported",
        supported_operand_indexes=[0, 1, 999],
    )
    record = checkpoint_review_evidence(a, record, review, [], a.units(), [])
    assert record.supported_operand_indexes == [0]
    assert not record.has_result and record.values == []
    context = a.context(finalizing=True)
    assert context["checked_partial_inputs"][0]["inputs"][0]["value"] == "24"
    restored = ResearchState.model_validate_json(a.state.model_dump_json())
    assert restored.quantities["partial"].draft.operands[0].value == "24"


@pytest.mark.asyncio
async def test_partial_input_reaches_finalizer_even_when_every_source_has_failed_collection():
    a = active()
    record = partial_record().model_copy(update={"supported_operand_indexes": [0]})
    a.state.quantities[record.id] = record
    seen = []

    async def call(role, output_type, instructions, data, **kwargs):
        seen.append(role)
        assert data["checked_partial_inputs"][0]["inputs"][0]["value"] == "24"
        return output_type(abstain=True)

    a.call = call
    result, _ = await finalize_research(a)
    assert result.abstain and seen == ["finalizer"]
    assert a.state.quantities[record.id].draft.operands[0].value == "24"


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked", [False, True])
async def test_user_visible_explanation_requires_current_authorized_provenance(revoked):
    a = active()
    receipt = receipt_for(a)

    async def generate(*args):
        return AgentCandidate(
            raw='{"abstain":true,"answer_parts":[]}',
            blocks=list(a.deps.ledger.blocks),
            telemetry={
                "pipeline_version": "pipeline_adaptive_v1",
                "abstention_reason": "INSUFFICIENT_EVIDENCE",
            },
            source_disposition=receipt,
        )

    if revoked:
        # Different source identity cannot release an old explanation.
        receipt = receipt.model_copy(
            update={
                "evidence": [receipt.evidence[0].model_copy(update={"document_version": "revoked"})]
            }
        )
    events = [
        event
        async for event in stream_support_unit_answer(
            QUESTION,
            [],
            None,
            model="fake",
            candidate_generator=generate,
        )
    ]
    text = "".join(e["content"] for e in events if e["type"] == "token")
    if revoked:
        assert text == "I could not obtain enough evidence to answer this question."
    else:
        assert "2013: 42" in text and "2020" in text
    security = next(e for e in events if e["type"] == "security_validation")
    assert security["abstain"]


@pytest.mark.asyncio
async def test_missing_operand_reason_keeps_checked_value_and_needs_no_second_checker():
    question = "What is Company A minus Company B tweets?"
    a = session(deps("Company A 24\nOther Company 5\nEnd table", question=question))
    proposal = DispositionProposal(
        kind="not_reported_in_scope",
        question_quote="Company B",
        requested="Company B tweets",
        source_object="corporate tweet table",
        scope="bounded_object",
        witnesses=[dict(support_id="E1.S1", quote="Company A 24", page=1)],
        boundaries=[dict(support_id="E1.S1", quote="End table", page=1)],
    )
    review = QuantityAssessment(
        inputs="unknown",
        coverage="incomplete",
        operation="supported",
        supported_operand_indexes=[0],
        source_disposition=ReviewedDisposition(proposal=proposal, judgment=reviewed().judgment),
    )
    checkpoint_review_evidence(
        a,
        partial_record().model_copy(update={"assessments": [review]}),
        review,
        [],
        a.units(),
        [],
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("Use the existing independent assessment")

    a.call = forbidden
    result, _ = await finalize_research(a)
    assert result.abstain
    text = disposition_text(a.current_disposition())
    assert "Company A tweets: 24 tweets" in text
    assert "Company B tweets" in text and "not reported" in text
    assert "Other Company 5" not in text
    assert a.state.quantities["partial"].values == []


@pytest.mark.asyncio
async def test_reviewed_clarification_survives_research_budget_stop():
    a = active()
    value = reviewed("needs_clarification", clarification_question="Which observation year?")
    value = value.model_copy(
        update={
            "judgment": value.judgment.model_copy(
                update={
                    "scope_complete": False,
                    "alternatives_excluded": False,
                }
            )
        }
    )
    a.state.source_dispositions.append(receipt_for(a, value))
    a.state.research_stop = "REQUEST_RESERVE"
    result, _ = await finalize_research(a)
    assert result.abstain and result.clarification.question == "Which observation year?"


def test_source_checks_are_not_authorized_by_a_changed_document_version():
    a = active()
    receipt = receipt_for(a)
    changed = {key: replace(unit, document_version="v2") for key, unit in a.units().items()}
    # Admission always binds to the current version, never to a model-specified version.
    changed_receipt = admit_disposition(reviewed(), QUESTION, changed)
    assert receipt.evidence[0].document_version == "v1"
    assert changed_receipt.evidence[0].document_version == "v2"


@pytest.mark.asyncio
async def test_same_proposal_and_same_evidence_do_not_repeat_a_semantic_review():
    a = active()
    calls = []

    async def call(*args, **kwargs):
        calls.append(1)
        return reviewed().judgment.model_copy(update={"scope_complete": False})

    a.call = call
    first = await a.review_disposition(reviewed().proposal)
    again = await a.review_disposition(reviewed().proposal)
    assert first is again and len(calls) == 1 and not first.verified
    a.deps.ledger.add([block("An unread continuation", id="new", page_number=2)])
    await a.review_disposition(reviewed().proposal)
    assert len(calls) == 2


def test_a_later_assessment_cannot_reuse_an_earlier_quantity_disposition():
    a = active()
    record = partial_record()
    review = QuantityAssessment(
        inputs="unknown",
        coverage="incomplete",
        operation="supported",
        source_disposition=reviewed(),
    )
    record = record.model_copy(update={"assessments": [review]})
    checkpoint_review_evidence(a, record, review, [], a.units(), [])
    assert a.current_disposition() is not None
    a.state.quantities[record.id] = a.state.quantities[record.id].model_copy(
        update={
            "assessments": [
                review,
                QuantityAssessment(
                    inputs="unknown",
                    coverage="unknown",
                    operation="unknown",
                ),
            ],
        }
    )
    assert a.current_disposition() is None
