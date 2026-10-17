"""471, 635 (unanswerable) and 634 ask about a color ("the yellow color", "with
grey background"). The text layer carries no colors, so the answers named items
from units that never mention the color. A question that picks things out by
color is answerable from text only when the cited units name that color; an
answer part whose cited units do not is rejected."""

import json

from app.evidence.support_units import build_support_units
from app.llm.premise import unsupported_colors
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

MILK = (
    "Color Milk temperature • green very cold milk (up to 8 °C) • white chilled milk "
    "(8 to 16 °C) • caramel uncooled milk (above 16 °C)"
)


def test_a_color_the_units_do_not_name_is_unsupported():
    question = "What temperature does the yellow color of the coffee machine represent?"

    assert unsupported_colors(question, [MILK]) == ["yellow"]
    assert unsupported_colors(question.replace("yellow", "green"), [MILK]) == []


def test_color_phrasings_and_grey_spellings():
    assert unsupported_colors("Which names have a grey background?", ["a gray box"]) == []
    assert unsupported_colors("Which lines are highlighted in yellow?", ["text"]) == ["yellow"]
    assert unsupported_colors("What is written in the Orange box?", ["Start"]) == ["orange"]
    assert unsupported_colors("When does the red bar start?", ["09:00"]) == ["red"]
    assert unsupported_colors("Which are the red words?", ["LONG, HEALTHY"]) == ["red"]


def test_color_words_that_are_not_colors_are_ignored():
    assert unsupported_colors("What share of Black adults use Twitter?", ["16"]) == []
    assert unsupported_colors("Who wrote the white paper?", ["Smith"]) == []
    assert unsupported_colors("What is the Green Bay office address?", ["Main St"]) == []


def _validate(question: str, unit_text: str, answer: str):
    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="c",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "b",
                    "source_id": "manual",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Milk"],
                    "contributing_chunk_ids": ["c"],
                    "text": unit_text,
                },
            )
        ]
    )
    part = {"text": answer, "support_ids": [unit.support_unit_id for unit in units]}
    parsed = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))
    return validate_support_unit_answer(parsed, units, question=question)


def test_an_answer_to_a_color_its_units_do_not_name_is_blocked():
    validation = _validate(
        "What temperature does the yellow color of the coffee machine represent for the milk?",
        MILK,
        "Green is very cold milk (up to 8 °C); white is chilled milk (8 to 16 °C).",
    )

    assert "QUERY_COLOR_NOT_IN_SUPPORT" in validation.failure_codes
    assert validation.application_abstain is True


def test_an_answer_to_a_color_its_units_name_passes():
    validation = _validate(
        "What temperature does the green color of the coffee machine represent for the milk?",
        MILK,
        "Green means very cold milk, up to 8 °C.",
    )

    assert validation.failure_codes == []
