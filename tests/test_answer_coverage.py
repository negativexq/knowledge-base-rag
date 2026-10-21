"""Coverage repair needs a concrete omission; concise supported answers remain valid."""

import pytest

from app.llm.adaptive import _finalize
from app.llm.agentic import AgentAnswer, AgentAnswerPart
from app.llm.answer_coverage import CoverageScopeJudgment, locate_omissions
from app.llm.research_budget import ResearchPolicy
from app.llm.scope_validation import scope_payload
from tests.test_adaptive import deps, session

SOURCE = (
    "Term B activities\nInterview a shop owner.\nCompare supplier requirements.\n"
    "Term C\nWrite a diary."
)


def candidate(text="Interview a shop owner."):
    return AgentAnswer(
        abstain=False, answer_parts=[AgentAnswerPart(text=text, support_ids=["E1.S1"])]
    )


def omission(**changes):
    value = dict(
        description="The requested supplier comparison is missing.",
        question_start=1,
        question_end=1,
        missing_locations=[dict(support_id="E1.S1", start_line=3, end_line=3)],
        scope_locations=[dict(support_id="E1.S1", start_line=1, end_line=1)],
    )
    value.update(changes)
    return value


def checks(count=1, *, reject_added=False):
    return [
        dict(
            claim_index=i,
            verdict="mismatch" if reject_added and i else "supported",
            reason="ENTITY_MISMATCH" if reject_added and i else "NONE",
            witnesses=[]
            if reject_added and i
            else [dict(support_id="E1.S1", start_line=1, end_line=3)],
        )
        for i in range(count)
    ]


def active_session(question="What activities are required in Term B?"):
    active = session(deps(SOURCE, question=question, scope_validation_enabled=True))
    active.compact_context = True
    return active


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,text",
    [
        ("What should I compare?", "Supplier requirements."),
        (
            "What activities are required in Term B?",
            "Interview the owner and compare supplier criteria.",
        ),
        ("What is the interview activity?", "Interview a shop owner."),
    ],
)
async def test_short_scalar_specific_or_paraphrased_collection_needs_no_repair(question, text):
    active = active_session(question)
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        assert role == "scope_validator"
        return output_type.model_validate(dict(checks=checks(), material_omissions=[]))

    active.call = call
    result, receipt = await active.verify(candidate(text))
    assert result.answer_parts[0].text == text
    assert not receipt.failure_codes and not active.state.answer_repairs
    assert calls == ["scope_validator"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repeat_omission,reject_added", [(False, False), (True, False), (False, True)]
)
async def test_completion_is_append_only_bounded_and_independently_rechecked(
    repeat_omission, reject_added
):
    active = active_session()
    original = candidate()
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        if role == "answer_repair":
            assert data["supported_parts"] == [p.model_dump() for p in original.answer_parts]
            assert data["missing_content"][0]["missing_locations"][0]["start_line"] == 3
            assert active.state.answer_repairs[0].omissions[0].missing_evidence[0].quote == (
                "Compare supplier requirements.\n"
            )
            return output_type.model_validate(
                dict(
                    additions=[
                        dict(
                            text="Compare supplier requirements.",
                            support_ids=["E1.S1"],
                        )
                    ]
                )
            )
        assert role == "scope_validator"
        count = len(data["claims"])
        return output_type.model_validate(
            dict(
                checks=checks(count, reject_added=reject_added),
                material_omissions=[omission()] if count == 1 or repeat_omission else [],
            )
        )

    active.call = call
    if repeat_omission or reject_added:
        with pytest.raises(ValueError, match="SCOPE_MATERIAL_OMISSION|SCOPE_ENTITY_MISMATCH"):
            await active.verify(original)
    else:
        result, receipt = await active.verify(original)
        assert result.answer_parts[:1] == original.answer_parts
        assert len(result.answer_parts) == 2
        assert receipt.accepts(active.deps.question, result.raw_answer(), active.deps.ledger.units)
    assert calls == ["scope_validator", "answer_repair", "scope_validator"]
    checkpoint = active.state.answer_repairs[0]
    assert checkpoint.parts == original.answer_parts and not checkpoint.failed_indexes


@pytest.mark.asyncio
async def test_no_repair_budget_preserves_supported_draft_without_another_call():
    active = active_session()
    active.policy = ResearchPolicy(max_validation_repairs=0)
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        return output_type.model_validate(dict(checks=checks(), material_omissions=[omission()]))

    active.call = call
    with pytest.raises(ValueError, match="SCOPE_MATERIAL_OMISSION"):
        await active.verify(candidate())
    assert calls == ["scope_validator"]
    assert active.state.answer_repairs[0].parts == candidate().answer_parts
    assert active.context(finalizing=True)["supported_answer_drafts"][0]["complete"] is False


@pytest.mark.parametrize(
    "change,generated",
    [
        (dict(question_end=3), set()),
        (dict(missing_locations=[dict(support_id="E99.S1", start_line=1, end_line=1)]), set()),
        (dict(missing_locations=[dict(support_id="E1.S1", start_line=100, end_line=101)]), set()),
        (dict(scope_locations=[dict(support_id="E99.S1", start_line=1, end_line=1)]), set()),
        ({}, {"E1.S1"}),
        (dict(description="   "), set()),
    ],
)
def test_omission_needs_original_missing_item_scope_and_question_locations(change, generated):
    active = active_session()
    payload = scope_payload(
        active.deps.question, candidate().raw_answer(), active.deps.ledger.units
    )
    judgment = CoverageScopeJudgment.model_validate(
        dict(checks=checks(), material_omissions=[omission(**change)])
    )
    with pytest.raises(ValueError, match="SCOPE_COVERAGE"):
        locate_omissions(payload, judgment, generated)


@pytest.mark.asyncio
async def test_malformed_omission_cannot_trigger_completion():
    active = active_session()
    calls = []

    async def call(role, output_type, instructions, data, **kwargs):
        calls.append(role)
        return output_type.model_validate(
            dict(
                checks=checks(),
                material_omissions=[omission(question_end=99)],
            )
        )

    active.call = call
    with pytest.raises(ValueError, match="SCOPE_COVERAGE_LOCATION_INVALID"):
        await active.verify(candidate())
    assert calls == ["scope_validator"] and not active.state.answer_repairs


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_again", [False, True])
async def test_timeout_preserves_completed_patch_and_resumes_check_without_regeneration(
    timeout_again,
):
    active = active_session()
    calls = []
    scope_calls = 0

    async def call(role, output_type, instructions, data, **kwargs):
        nonlocal scope_calls
        calls.append(role)
        if role == "answer_repair":
            return output_type.model_validate(
                dict(
                    additions=[
                        dict(
                            text="Compare supplier requirements.",
                            support_ids=["E1.S1"],
                        )
                    ]
                )
            )
        assert role == "scope_validator"
        scope_calls += 1
        if scope_calls == 1:
            return output_type.model_validate(
                dict(checks=checks(), material_omissions=[omission()])
            )
        assert data["coverage_followup"]["preserved_claim_indexes"] == [0]
        assert data["coverage_followup"]["added_claim_indexes"] == [1]
        if scope_calls == 2 or timeout_again:
            raise TimeoutError()
        return output_type.model_validate(dict(checks=checks(2), material_omissions=[]))

    active.call = call
    with pytest.raises(TimeoutError):
        await active.verify(candidate())
    pending = active.state.answer_repairs[0]
    assert pending.completion_status == "pending" and len(pending.candidate_parts) == 2
    result, receipt = await _finalize(active)
    if timeout_again:
        assert result.abstain and receipt is None
    else:
        assert result.answer_parts == pending.candidate_parts and not receipt.failure_codes
        assert active.state.answer_repairs[0].completion_status == "verified"
    assert calls == ["scope_validator", "answer_repair", "scope_validator", "scope_validator"]
