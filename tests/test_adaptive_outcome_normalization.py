"""Useful semantic outcomes survive mixed transport fields without a model retry."""

import hashlib
import json

import fitz
import pytest
from pydantic import ValidationError
from pydantic_ai.models.function import FunctionModel

from app.llm.adaptive import AdaptiveAnswer, ResearchDecision, finalize_research, run_adaptive_agent
from app.llm.agentic import AgentAnswerPart, AgentCalculation
from app.llm.calculation_sources import calculation_inspection_targets
from app.llm.research_state import EvidenceNeedSpec, NeedConstraint, TextCalculationPlan
from app.llm.scope_requirements import RequiredScopeJudgment
from app.llm.visual_answer import PdfPages
from tests.test_adaptive import answer, block, deps, reply, session


@pytest.mark.asyncio
async def test_clarification_discards_answer_draft_without_requesting_another_model_call():
    calls = []

    def model(messages, info):
        calls.append(1)
        return reply(
            info,
            dict(
                **answer("Unsupported draft"),
                clarification={"question": "Which session do you mean?", "options": []},
            ),
        )

    result = await run_adaptive_agent(FunctionModel(model), deps(), max_tool_calls=0)
    assert len(calls) == 1 and result.failure_code is None
    assert result.clarification["question"] == "Which session do you mean?"
    assert json.loads(result.raw) == {"abstain": True, "answer_parts": []}
    assert "Unsupported" not in result.raw


@pytest.mark.asyncio
async def test_mixed_answer_and_prepared_plan_execute_the_plan_without_a_model_retry():
    a = session(deps("North 3; South 7", derived_answers=True))
    decision = ResearchDecision.model_validate(
        dict(
            action="answer",
            answer=answer("999"),
            text_calculation=dict(support_ids=["E1.S1"], expression="3 + 7", decimals=0),
        )
    )
    assert decision.action == "calculate" and decision.answer is None
    assert await a.execute(decision)
    assert next(iter(a.state.text_computations.values())).value == "10"
    assert a.usage.requests == 0


def test_two_prepared_plans_are_still_ambiguous_and_not_silently_selected():
    with pytest.raises(ValidationError):
        ResearchDecision.model_validate(
            dict(
                action="answer",
                answer=answer(),
                text_calculation=dict(support_ids=["E1.S1"], expression="3 + 7"),
                calculation=dict(expression="a", inputs=[dict(name="a", fact_id="F1")]),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("closed", [True, False])
async def test_same_scope_checker_can_return_a_negative_finding_without_positive_target_presence(
    closed,
):
    question = "Which entry corresponds to Gamma?"
    source = "Inventory:\nAlpha North\nBeta South\nEnd inventory"
    a = session(deps(source, question=question, scope_validation_enabled=True))
    a.state.add_need(
        EvidenceNeedSpec(
            description="Requested entry",
            constraints=[
                NeedConstraint(dimension="entity", value="Gamma", question_quote="Gamma"),
            ],
        )
    )
    a.state.need_planning = "ready"
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        assert output_type is RequiredScopeJudgment
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[
                            dict(support_id="E1.S1", field="text", start_line=2, end_line=3),
                        ],
                    )
                ],
                objections=[],
                requirement_bindings=[
                    dict(
                        requirement_index=0,
                        verdict="unknown",
                        binding_basis="unestablished",
                        claim_indexes=[0],
                        witnesses=[],
                    )
                ],
                source_disposition=dict(
                    proposal=dict(
                        kind="not_reported_in_scope",
                        question_quote="Gamma",
                        requested="Gamma entry",
                        source_object="inventory",
                        scope="bounded_object",
                        witnesses=[dict(support_id="E1.S1", start_line=2, end_line=3)],
                        boundaries=[dict(support_id="E1.S1", start_line=4, end_line=4)],
                    ),
                    judgment=dict(
                        question_binding="supported",
                        object_identity="supported",
                        scope_complete=closed,
                        alternatives_excluded=closed,
                    ),
                ),
            )
        )

    a.call = call
    proposed = AdaptiveAnswer.model_validate(
        answer("Gamma is not reported in the inventory. Alpha North and Beta South are listed.")
    )
    if closed:
        result, scope = await a.verify(proposed)
        assert result.abstain and scope is None
        assert a.current_disposition().kind == "not_reported_in_scope"
    else:
        with pytest.raises(ValueError):
            await a.verify(proposed)
        assert a.current_disposition() is None
    assert calls == ["scope_validator"]


@pytest.mark.asyncio
async def test_supported_answer_with_an_unproven_entity_is_released_with_the_source_scope_stated():
    # TechQA Q267: the source names the Tools & Utilities key; whether it covers
    # the asked-for Architect Floating license stays unknown. Say so, keep it.
    question = "How do I enable the reporter with an Architect Floating license?"
    source = "The reporter is enabled by the Tools and Utilities license key."
    a = session(deps(source, question=question, scope_validation_enabled=True))
    a.state.add_need(
        EvidenceNeedSpec(
            description="How to enable the reporter",
            constraints=[
                NeedConstraint(
                    dimension="entity",
                    value="Architect Floating license",
                    question_quote="Architect Floating license",
                ),
            ],
        )
    )
    a.state.need_planning = "ready"
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        assert output_type is RequiredScopeJudgment
        return output_type.model_validate(
            dict(
                checks=[
                    dict(
                        claim_index=0,
                        verdict="supported",
                        reason="NONE",
                        witnesses=[
                            dict(support_id="E1.S1", field="text", start_line=1, end_line=1),
                        ],
                    )
                ],
                objections=[],
                requirement_bindings=[
                    dict(
                        requirement_index=0,
                        verdict="unknown",
                        binding_basis="unestablished",
                        claim_indexes=[0],
                        witnesses=[],
                    )
                ],
            )
        )

    a.call = call
    proposed = AdaptiveAnswer.model_validate(
        answer("The reporter is enabled by the Tools and Utilities license key.")
    )
    result, receipt = await a.verify(proposed)
    assert calls == ["scope_validator"]
    assert receipt is not None and not receipt.failure_codes
    assert [p.answer_kind for p in result.answer_parts] == ["answer", "source_limitation"]
    note = result.answer_parts[1]
    assert note.support_ids == ["E1.S1"]
    assert '"Architect Floating license"' in note.text
    assert "do not establish" in note.text


@pytest.mark.asyncio
async def test_checked_text_computation_finalizes_from_its_canonical_proof_without_a_finalizer():
    a = session(deps("North 3; South 7", derived_answers=True))
    a.calculate_text(TextCalculationPlan(support_ids=["E1.S1"], expression="3 + 7", decimals=0))

    async def forbidden(*args, **kwargs):
        raise AssertionError("No model is needed to rewrite a completed application calculation")

    a.call = forbidden
    result, _ = await finalize_research(a)
    assert not result.abstain and result.answer_parts[0].calculation.result == "10"


@pytest.mark.asyncio
@pytest.mark.parametrize("native_matches", [True, False])
async def test_overlapping_page_hint_needs_complete_original_numeric_support(
    tmp_path, native_matches
):
    path = tmp_path / "manual.pdf"
    with fitz.open() as pdf:
        for i in range(6):
            text = (
                ("North 3; South 7" if native_matches else "North 2; South 7")
                if i == 0
                else "Context page"
            )
            if i == 5:
                text = "Additional amount 11"
            pdf.new_page().insert_text((30, 30), text)
        pdf.save(path)
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    a = session(deps("North 3; South 7", derived_answers=True, render_page=PdfPages(str(tmp_path))))
    a.deps.ledger.blocks[0].payload.update(
        source_id="manual_pdf",
        document_version=version,
        page_number=1,
        page_end=5,
        requested_page=1,
    )
    a.deps.ledger.source_ids = frozenset({"manual_pdf"})
    a.deps.ledger.add(
        [
            block(
                "Additional amount 11",
                id="other",
                source_id="manual_pdf",
                document_version=version,
                page_number=6,
            )
        ]
    )
    part = AgentAnswerPart(
        text="21",
        support_ids=["E1.S1", "E2.S1"],
        calculation=AgentCalculation(expression="3 + 7 + 11", result="21"),
    )
    original = [(["E1.S1"], []), (["E2.S1"], [])]
    targets = await calculation_inspection_targets(a, part, original)
    assert targets == ([(["E1.S1"], [1]), (["E2.S1"], [6])] if native_matches else original)
