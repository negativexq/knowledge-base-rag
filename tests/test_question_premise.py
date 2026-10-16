"""A question that pins a year the evidence never mentions ("revised in
May 2018" when the documents say 2016) has a false premise. Answering it
from nearby content is wrong, so an answer is turned into an application
abstention. Questions whose years appear in the evidence are unaffected."""

import json

import pytest

from app.llm.premise import missing_question_years
from app.llm.structured_output import stream_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

EVIDENCE = "Strategic plan, Version 1.3, revised May 2016. Produced by the Records Office."


def test_years_absent_from_the_evidence_are_reported():
    assert missing_question_years("Who produced the plan revised in May 2018?", [EVIDENCE]) == [
        "2018"
    ]


def test_years_present_in_the_evidence_pass():
    assert missing_question_years("Who produced the plan revised in May 2016?", [EVIDENCE]) == []


def test_questions_without_years_pass():
    assert missing_question_years("Who produced the plan?", [EVIDENCE]) == []


def test_numbers_that_are_not_years_are_ignored():
    assert missing_question_years("What are pins 10 to 13 used for?", [EVIDENCE]) == []
    assert missing_question_years("How many of the 12500 users replied?", [EVIDENCE]) == []


def _block() -> SearchResult:
    return SearchResult(
        score=0.9,
        id="chunk-1",
        payload={
            "text": EVIDENCE,
            "source_type": "filesystem",
            "source_id": "plan",
            "page_number": 2,
            "paragraph_index": 0,
            "tenant_id": "tenant-a",
            "authorized": True,
            "model_visible": True,
        },
    )


class _Provider:
    async def chat_json(self, messages, **kwargs):
        return json.dumps(
            {
                "answer_parts": [{"text": "The Records Office.", "support_ids": ["E1.S1"]}],
                "abstain": False,
            }
        )


async def _ask(question: str) -> tuple[str, dict]:
    answer, validation = "", {}
    async for event in stream_support_unit_answer(
        question, [_block()], _Provider(), model="m", validator_version="baseline"
    ):
        if event["type"] == "token":
            answer += event["content"]
        elif event["type"] == "security_validation":
            validation = event
    return answer, validation


@pytest.mark.asyncio
async def test_an_answer_to_a_false_premise_becomes_an_abstention():
    answer, validation = await _ask("Who produced the plan that was revised in May 2018?")

    assert "Records Office" not in answer
    assert validation["abstain"] is True
    assert validation["application_forced_abstention"] is True
    assert "QUESTION_PREMISE_NOT_IN_EVIDENCE" in validation["validator_failure_codes"]


@pytest.mark.asyncio
async def test_an_answer_whose_premise_is_in_the_evidence_is_kept():
    answer, validation = await _ask("Who produced the plan that was revised in May 2016?")

    assert "Records Office" in answer
    assert validation["abstain"] is False
