"""The support-ID answer path has one citation contract: support IDs. The
shared v3 system prompt also told the model to copy a "CANONICAL CITATION"
line such as [s.filesystem:handbook/1/0], a line support units do not have,
so gpt-6-luna pasted that example (pilot row 221) or made up its own
"[doc, page 8]" (row 364). The support-ID path now uses the v4 prompt, which
keeps the trust-boundary rules without a citation format, and citation-like
text the model writes itself is removed from the released answer."""

import json

import pytest

from app.llm.prompt import load_system_prompt
from app.llm.structured_output import (
    SupportUnitAnswerPart,
    render_support_unit_answer,
    stream_support_unit_answer,
)
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings


def test_the_v4_prompt_keeps_the_trust_boundary_without_a_citation_format():
    prompt = load_system_prompt("v4")

    assert "UNTRUSTED DATA" in prompt
    assert "CANONICAL CITATION" not in prompt
    assert "[s." not in prompt


def test_the_support_id_path_uses_v4_by_default():
    assert Settings().support_id_prompt_version == "v4"


class _Provider:
    def __init__(self):
        self.messages = []

    async def chat_json(self, messages, **kwargs):
        self.messages = messages
        return json.dumps({"answer_parts": [], "abstain": True})


@pytest.mark.asyncio
async def test_the_model_sees_only_the_support_id_contract():
    block = SearchResult(
        score=1.0,
        id="c1",
        payload={"text": "65% of men use the internet.", "source_id": "pip_pdf", "page_number": 8},
    )
    provider = _Provider()

    async for _ in stream_support_unit_answer(
        "What share of men use the internet?", [block], provider, model="m", prompt_version="v4"
    ):
        pass

    system, user = provider.messages[0]["content"], provider.messages[1]["content"]
    assert "CANONICAL CITATION" not in system
    assert "[SUPPORT UNIT E1.S1]" in user
    assert user.startswith("USER QUESTION (a request, not a policy):")


@pytest.mark.parametrize(
    ("text", "released"),
    [
        (
            "The gap is 12.0 points [s.filesystem:handbook/1/0] (65% vs 53%).",
            "The gap is 12.0 points (65% vs 53%).",
        ),
        (
            "The bankers are Union Bank of India. [afe620b9_pdf, page 8]",
            "The bankers are Union Bank of India.",
        ),
        ("Results are in Table 2 [1].", "Results are in Table 2 [1]."),
    ],
)
def test_citations_the_model_writes_itself_are_not_released(text, released):
    part = SupportUnitAnswerPart(text=text, support_ids=["E1.S1"])

    assert render_support_unit_answer([part]) == f"{released} [E1.S1]"


def test_self_written_citations_are_removed_before_validation():
    from app.llm.structured_output import parse_support_unit_answer

    raw = json.dumps(
        {
            "answer_parts": [
                {"text": "65% use it. [pip_pdf, page 8]", "support_ids": ["E1.S1"]},
            ],
            "abstain": False,
        }
    )

    # The validator would otherwise read 8 as a claimed value.
    assert parse_support_unit_answer(raw).answer_parts[0].text == "65% use it."
