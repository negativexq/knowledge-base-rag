"""The visual path (app/llm/visual_answer.py). Parsed text carries no colors,
figures or layout, so 10 answerable luna questions about them were abstained
(385, 393, 511, 636, 637, 661, 662, 663, 732, 829). When the text answer is
withheld and the question refers to something visual, the top retrieved pages
are rendered and read by an image-capable model; a second, independent call
checks the candidate against the same pages. The answer is marked as read from
a page image, with its page, and never passes as text-validated."""

import json

import fitz
import pytest

from app.evidence.support_units import build_support_units
from app.llm.visual_answer import (
    asks_visual,
    candidate_pages,
    page_messages,
    render_pdf_page,
)
from app.retrieval.hybrid_search import SearchResult


def test_questions_that_refer_to_something_visual():
    for question in (
        "What is the word written in the Orange box on page 17?",
        "How many lines are highlighted in yellow on the first page?",
        "What does the figure on page 3 show between steps 2 and 3?",
        "In the chart on page 9, which group is largest?",
        "What color is the logo?",
        "How many pictures are on the cover?",
        "What are the words written in the first rectangle on the top of page two?",
        "What are the top two texts of the red words in the document?",
    ):
        assert asks_visual(question), question
    for question in (
        "What is Costco's total debt in FY2021?",
        "Who wrote the white paper?",
        "How many appendices are there?",
    ):
        assert not asks_visual(question), question


def _blocks(*pages):
    return [
        SearchResult(
            score=1.0,
            id=f"c{index}",
            payload={
                "evidence_id": f"E{index}",
                "evidence_block_id": f"b{index}",
                "source_id": source,
                "document_version": "v",
                "tenant_id": "t",
                "heading_path": ["S"],
                "contributing_chunk_ids": [f"c{index}"],
                "page_number": page,
                "text": f"text on page {page}",
            },
        )
        for index, (source, page) in enumerate(pages, 1)
    ]


def test_candidate_pages_are_the_distinct_top_pages_in_rank_order():
    units = build_support_units(_blocks(("doc", 17), ("doc", 17), ("doc", 3), ("doc", 9), ("x", 1)))

    assert candidate_pages(units, limit=3) == [("doc", 17), ("doc", 3), ("doc", 9)]


def test_page_messages_carry_each_page_as_an_image_with_its_number():
    messages = page_messages("What is in the orange box?", [("doc", 17, b"PNG")], "INSTR")

    assert messages[0] == {"role": "system", "content": "INSTR"}
    content = messages[1]["content"]
    assert content[0]["type"] == "input_text" and "orange box" in content[0]["text"]
    assert content[1] == {"type": "input_text", "text": "Page 17 of doc:"}
    assert content[2]["type"] == "input_image"
    assert content[2]["image_url"].startswith("data:image/png;base64,")


def test_a_pdf_page_renders_to_png(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    path = tmp_path / "one.pdf"
    doc.save(path)

    assert render_pdf_page(str(path), 1)[:8] == b"\x89PNG\r\n\x1a\n"
    assert render_pdf_page(str(path), 5) is None


class _Provider:
    supports_images = True

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        return json.dumps(self.outputs.pop(0))


ABSTAIN = {"answer_parts": [], "abstain": True}
READ = {
    "answer": "Start new search",
    "page": 17,
    "observation": "An orange box reads 'Start new search'.",
    "abstain": False,
}
YES = {"supported": True}
NO = {"supported": False}


async def _run(
    provider, question="What is the word written in the Orange box on page 17?", **kwargs
):
    from app.llm.structured_output import stream_support_unit_answer

    events = [
        event
        async for event in stream_support_unit_answer(
            question,
            _blocks(("doc", 17), ("doc", 18)),
            provider,
            model="m",
            derived_answers=True,
            visual_answers=kwargs.get("visual_answers", True),
            render_page=kwargs.get("render_page", lambda source, page: b"PNG"),
        )
    ]
    answer = "".join(event["content"] for event in events if event["type"] == "token")
    validation = next(event for event in events if event["type"] == "security_validation")
    return answer, validation


@pytest.mark.asyncio
async def test_a_withheld_visual_question_is_read_from_the_page_and_checked():
    provider = _Provider(ABSTAIN, READ, YES)
    answer, validation = await _run(provider)

    assert validation["abstain"] is False and validation["visual_answer"] is True
    assert answer == "Start new search [page 17, read from the page image]"
    assert len(provider.calls) == 3
    # The check sees the candidate, not the first call's reasoning.
    assert "Start new search" in json.dumps(provider.calls[2])
    assert "observation" not in json.dumps(provider.calls[2])


@pytest.mark.asyncio
async def test_an_unconfirmed_reading_leaves_the_abstention():
    answer, validation = await _run(_Provider(ABSTAIN, READ, NO))

    assert validation["abstain"] is True


@pytest.mark.asyncio
async def test_a_reading_from_a_page_that_was_not_shown_is_dropped():
    answer, validation = await _run(_Provider(ABSTAIN, {**READ, "page": 40}, YES))

    assert validation["abstain"] is True


@pytest.mark.asyncio
async def test_a_text_question_or_a_disabled_path_makes_no_visual_call():
    provider = _Provider(ABSTAIN, READ, YES)
    await _run(provider, question="What is Costco's total debt in FY2021?")
    assert len(provider.calls) == 1

    provider = _Provider(ABSTAIN, READ, YES)
    await _run(provider, visual_answers=False)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_a_provider_without_images_makes_no_visual_call():
    provider = _Provider(ABSTAIN, READ, YES)
    provider.supports_images = False
    answer, validation = await _run(provider)

    assert validation["abstain"] is True and len(provider.calls) == 1


def test_a_renderer_finds_a_pdf_by_its_source_id(tmp_path):
    from app.llm.visual_answer import pdf_page_renderer

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(tmp_path / "COSTCO 2021 10K.pdf")
    render = pdf_page_renderer(str(tmp_path))

    assert render("COSTCO_2021_10K_pdf", 1)[:4] == b"\x89PNG"
    assert render("missing_pdf", 1) is None


def test_candidate_pages_skip_units_the_caller_may_not_see():
    blocks = _blocks(("doc", 4), ("doc", 5))
    blocks[0].payload["authorized"] = False
    units = build_support_units(blocks)

    assert candidate_pages(units) == [("doc", 5)]
