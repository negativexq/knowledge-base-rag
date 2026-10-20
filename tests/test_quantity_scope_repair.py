"""A grounded release objection repairs evidence instead of repeating a rejected answer."""

import pytest

from app.llm.adaptive import verify_prepared_quantity
from app.llm.agentic import AgentAnswer, AgentAnswerPart
from app.llm.quantities import candidate
from app.llm.quantity_state import QuantityCheck, QuantityDraft, QuantityRecord
from app.llm.scope_diagnostics import DiagnosticScopeJudgment, ScopeDiagnostic
from tests.test_quantities import active_session, arithmetic


def diagnostic(errors=None):
    return ScopeDiagnostic(
        diagnostic_errors=errors or [],
        judgment=DiagnosticScopeJudgment.model_validate(
            dict(
                checks=[
                    dict(claim_index=0, verdict="insufficient", reason="SCOPE_NOT_ESTABLISHED")
                ],
                objections=[
                    dict(
                        claim_index=0,
                        description="Committee is not a full roster",
                        question_start=1,
                        question_end=1,
                        needed_evidence="Full company roster",
                        source_locations=[
                            dict(support_id="E1.S1", field="text", start_line=1, end_line=1)
                        ],
                    )
                ],
            )
        ),
    )


def record():
    return QuantityRecord(
        id="original",
        need_id="need",
        support_ids=["E1.S1"],
        source_id="report",
        document_version="v1",
        pages=[1],
        modality="text",
        draft=QuantityDraft(
            mode="list", complete=True, items=[dict(text="Alpha", position=1, witness="Alpha")]
        ),
        values=["Alpha"],
        proof_support_ids=["proof"],
        check=QuantityCheck(accepted=True, complete=True, reason="supported"),
    )


@pytest.mark.asyncio
async def test_grounded_scope_objection_runs_one_source_repair_then_full_verification(monkeypatch):
    active, need = active_session()
    parent = record()
    active.state.quantities[parent.id] = parent
    prepared = candidate(parent)
    repaired = AgentAnswer(
        abstain=False, answer_parts=[AgentAnswerPart(text="Alpha, Beta", support_ids=["new-proof"])]
    )
    calls = []

    async def verify(answer):
        calls.append("verify")
        if answer is prepared:
            active.state.quantity_scope_diagnostics.append(diagnostic())
            raise ValueError("SCOPE_NOT_ESTABLISHED")
        assert answer is repaired
        return answer, None

    async def collect(session, need_id, *, parent, repairs_left):
        calls.append("collect")
        assert need_id == need and repairs_left == 0
        assert parent.scope_diagnostic == diagnostic()
        assert parent.values == ["Alpha"]
        return repaired

    active.verify = verify
    monkeypatch.setattr("app.llm.adaptive.collect_quantities", collect)
    result = await verify_prepared_quantity(active, prepared, need, allow_scope_repair=True)
    assert result[0] is repaired
    assert calls == ["verify", "collect", "verify"]
    assert active.state.quantity_repairs == 1
    assert active.state.quantities[parent.id].values == ["Alpha"]
    assert active.state.quantities[parent.id].scope_diagnostic is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "errors,allow_repair", [([], False), (["SCOPE_OBJECTION_SOURCE_INVALID"], True)]
)
async def test_invalid_or_closed_repair_cannot_approve_answer(monkeypatch, errors, allow_repair):
    active, need = active_session()
    parent = record()
    active.state.quantities[parent.id] = parent

    async def verify(answer):
        active.state.quantity_scope_diagnostics.append(diagnostic(errors))
        raise ValueError("SCOPE_NOT_ESTABLISHED")

    async def collect(*args, **kwargs):
        pytest.fail("Closed or ungrounded repair must not call a model")

    active.verify = verify
    monkeypatch.setattr("app.llm.adaptive.collect_quantities", collect)
    if errors:
        with pytest.raises(ValueError, match="SCOPE_NOT_ESTABLISHED"):
            await verify_prepared_quantity(
                active, candidate(parent), need, allow_scope_repair=allow_repair
            )
    else:
        assert (
            await verify_prepared_quantity(
                active, candidate(parent), need, allow_scope_repair=allow_repair
            )
            is None
        )
    assert not active.state.quantity_repairs


def test_application_answer_displays_reviewed_interpretation_and_unit():
    draft = arithmetic().model_copy(
        update={
            "result_unit": "percentage points",
            "interpretation": "Absolute difference",
        }
    )
    result = candidate(
        record().model_copy(
            update={
                "draft": draft,
                "values": ["12"],
                "expression": "65 - 53",
            }
        )
    )
    assert result.answer_parts[0].text == "12 percentage points (Absolute difference)"
    assert result.answer_parts[0].calculation.result == "12"


@pytest.mark.asyncio
async def test_application_result_check_reserves_one_final_scope_request():
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import UsageLimits

    from app.llm.adaptive import ResearchClosed
    from app.llm.quantity_state import QuantityAssessment
    from tests.test_adaptive import reply

    active, _ = active_session()
    active.model = FunctionModel(
        lambda messages, info: reply(
            info,
            dict(
                inputs="supported",
                coverage="complete",
                operation="supported",
            ),
        )
    )
    active.usage.requests = 8
    active.limits = UsageLimits(request_limit=10)
    result = await active.call(
        "quantity_checker",
        QuantityAssessment,
        "Review inputs",
        {},
        research=True,
    )
    assert result.operation == "supported" and active.usage.requests == 9
    active.deps.scope_validation_enabled = True
    with pytest.raises(ResearchClosed, match="REQUEST_RESERVE"):
        await active.call(
            "quantity_checker", QuantityAssessment, "Review inputs", {}, research=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["source_binding", "interpretation", "unit_transform", "presentation"]
)
async def test_existing_source_scope_repair_skips_selector_but_rechecks_inputs(kind):
    from app.llm.quantities import collect
    from app.llm.quantity_review import repair_requirement
    from app.llm.quantity_state import QuantityAssessment
    from tests.test_quantities import fake_calls

    active, need = active_session()
    parent = record().model_copy(
        update={
            "need_id": need,
            "draft": arithmetic(),
            "values": ["10"],
            "assessments": [
                QuantityAssessment(inputs="supported", coverage="complete", operation="supported")
            ],
            "scope_diagnostic": diagnostic().model_copy(
                update={
                    "judgment": diagnostic().judgment.model_copy(
                        update={
                            "objections": [
                                diagnostic()
                                .judgment.objections[0]
                                .model_copy(update={"repair_kind": kind})
                            ]
                        }
                    )
                }
            ),
        }
    )
    active.state.quantities[parent.id] = parent
    roles = fake_calls(active)
    assert repair_requirement(parent).evidence_kind == "existing_scope"
    result = await collect(active, need, parent=parent, repairs_left=0)
    assert result is not None and result.answer_parts[0].text == "10"
    assert roles == ["quantity_collector", "quantity_checker"]
    child = list(active.state.quantities.values())[-1]
    assert child.check.accepted and child.support_ids == parent.support_ids
    assert active.state.quantities[parent.id].scope_diagnostic is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing_source", "mismatch"])
async def test_real_missing_source_or_mismatch_still_rejects_unchanged_view(kind):
    from app.llm.quantities import collect
    from app.llm.quantity_review import repair_requirement
    from app.llm.quantity_state import QuantityAssessment
    from tests.test_quantities import fake_calls

    active, need = active_session()
    parent = record().model_copy(
        update={
            "need_id": need,
            "draft": arithmetic(),
            "pages": [],
            "assessments": [
                QuantityAssessment(inputs="supported", coverage="complete", operation="supported")
            ],
            "scope_diagnostic": diagnostic().model_copy(
                update={
                    "judgment": diagnostic().judgment.model_copy(
                        update={
                            "objections": [
                                diagnostic()
                                .judgment.objections[0]
                                .model_copy(update={"repair_kind": kind})
                            ]
                        }
                    )
                }
            ),
        }
    )
    roles = fake_calls(active)
    assert repair_requirement(parent).evidence_kind == "scope_research"
    with pytest.raises(ValueError, match="REPAIR_REUSED_INSUFFICIENT_SOURCE"):
        await collect(active, need, parent=parent, repairs_left=0)
    assert roles == ["quantity_selector"]


def test_mixed_or_invalid_scope_objections_cannot_disable_freshness():
    from app.llm.quantity_review import repair_requirement

    d = diagnostic()
    local = d.judgment.objections[0].model_copy(update={"repair_kind": "presentation"})
    for objections, errors in [
        ([local, d.judgment.objections[0]], []),
        ([local], ["SCOPE_OBJECTION_SOURCE_INVALID"]),
        ([], []),
    ]:
        p = record().model_copy(
            update={
                "scope_diagnostic": d.model_copy(
                    update={
                        "diagnostic_errors": errors,
                        "judgment": d.judgment.model_copy(update={"objections": objections}),
                    }
                )
            }
        )
        assert repair_requirement(p).evidence_kind == "scope_research"


@pytest.mark.asyncio
async def test_same_source_repair_is_not_automatic_acceptance():
    from app.llm.quantities import collect
    from app.llm.quantity_state import QuantityAssessment, QuantityCheck
    from tests.test_quantities import fake_calls

    active, need = active_session()
    d = diagnostic()
    d = d.model_copy(
        update={
            "judgment": d.judgment.model_copy(
                update={
                    "objections": [
                        d.judgment.objections[0].model_copy(
                            update={"repair_kind": "unit_transform"}
                        )
                    ]
                }
            )
        }
    )
    parent = record().model_copy(
        update={
            "draft": arithmetic(),
            "values": ["10"],
            "scope_diagnostic": d,
            "assessments": [
                QuantityAssessment(inputs="supported", coverage="complete", operation="supported")
            ],
        }
    )
    roles = fake_calls(
        active, check=QuantityCheck(accepted=False, complete=False, reason="wrong_scope")
    )
    assert await collect(active, need, parent=parent, repairs_left=0) is None
    assert roles == ["quantity_collector", "quantity_checker"]
    child = list(active.state.quantities.values())[-1]
    assert not child.check.accepted and not child.values
