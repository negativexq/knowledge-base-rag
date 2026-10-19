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
