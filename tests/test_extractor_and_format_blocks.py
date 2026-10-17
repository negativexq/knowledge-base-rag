"""Blocks the luna counts rerun traced to extraction and format, with the cited
units' text in hand:

- 373: "Rs. 1,767.80 lacs" was read as "767.80" (the thousands group was cut
  off), so it conflicted with a unit printing "1767.80". A grouped decimal is
  one literal, compared like its ungrouped form.
"""

from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_validator_runtime import audit_critical_value


def _literals(text: str) -> list[tuple[str, str, str]]:
    return [
        (o.raw_literal, o.normalized_value, o.lexical_type)
        for o in extract_critical_occurrences(text)
    ]


def test_a_grouped_decimal_is_one_literal_like_its_ungrouped_form():
    grouped = _literals("Rs. 1,767.80 lacs versus Rs. 1,923.78 lacs")
    plain = _literals("Proposed dividend 1767.80 1923.78")

    assert [raw for raw, _, _ in grouped] == ["1,767.80", "1,923.78"]
    assert [(value, kind) for _, value, kind in grouped] == [
        (value, kind) for _, value, kind in plain
    ]


def test_a_grouped_decimal_is_supported_by_its_ungrouped_form():
    claim = "The dividend was Rs. 1,767.80 lacs in 2002 versus Rs. 1,923.78 lacs in 2001."
    row = "Proposed dividend | 2002 | 2001 | 1767.80 | 1923.78"

    assert audit_critical_value(claim, [row])["validator_outcome"] == "PASS"
    assert (
        audit_critical_value(claim, [row.replace("1767.80", "1767.90")])["validator_outcome"]
        != "PASS"
    )


# - 223, 227: survey tables print percentages as bare cells with significance
#   letters glued on ("$75,000+ 92 42", "College graduate (n=537) 87ab"), so a
#   correct "42%" or "87%" met a NUMBER or nothing. In a unit that prints no
#   "%", a cell 0-100 standing alone (line end, "|" or another number next)
#   is restated as a percentage; a number followed by a word is not a cell.

from app.llm.percent_cells import percent_cell_facts  # noqa: E402


def test_bare_table_cells_are_restated_as_percentages():
    assert percent_cell_facts(["$75,000+ 92 42", "d $75,000+ (n=274) 39abc"]) == [
        "table cell 92 = 92%",
        "table cell 42 = 42%",
        "table cell 39abc = 39%",
    ]
    assert percent_cell_facts(["Subtask | 2 | 5 | 2"]) == [
        "table cell 2 = 2%",
        "table cell 5 = 5%",
        "table cell 2 = 2%",
    ]


def test_counts_sizes_and_units_that_print_percentages_are_not_cells():
    assert percent_cell_facts(["The team has 42 employees."]) == []
    assert percent_cell_facts(["College graduate (n=537) 87ab and 31% overall"]) == []
    assert percent_cell_facts(["Flight 4u9525 at 140 knots"]) == []


def test_a_survey_answer_citing_bare_cells_passes():
    units = ["$75,000+ 92 42", "d $75,000+ (n=274) 39abc"]
    claim = (
        "Among seniors earning $75,000+, 92% own a cell phone, 42% a smartphone and 39% a tablet."
    )

    assert audit_critical_value(claim, units + percent_cell_facts(units))["validator_outcome"] == (
        "PASS"
    )
    assert (
        audit_critical_value(claim.replace("39%", "38%"), units + percent_cell_facts(units))[
            "validator_outcome"
        ]
        != "PASS"
    )


def test_the_support_unit_path_restates_cells_for_a_percentage_answer():
    import json

    from app.evidence.support_units import build_support_units
    from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
    from app.retrieval.hybrid_search import SearchResult

    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="c",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "b",
                    "source_id": "survey",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Tablets"],
                    "contributing_chunk_ids": ["c"],
                    "text": "c College graduate (n=537) 87ab\n\nc College graduate (n=537) 31ab",
                },
            )
        ]
    )
    part = {
        "text": "Among college graduates, 87% own a cell phone and 31% own a tablet.",
        "support_ids": [unit.support_unit_id for unit in units],
    }
    answer = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))

    assert validate_support_unit_answer(answer, units).failure_codes == []
