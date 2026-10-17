"""740 asks for dates as YYYY-MM-DD; the units print "24 March 2015" and
"March 25, 2015", so the answer's ISO dates were INDETERMINATE. A date with a
month name is unambiguous: when the answer writes ISO dates, each such date
in the cited units is restated as ISO in a derived evidence line (as verified
calculations and counts are). Numeric dates ("03/04/2015") are ambiguous and
are not restated."""

import json

from app.evidence.support_units import build_support_units
from app.llm.dates import iso_date_facts
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

CRASH = "Germanwings Flight 9525 crashed on 24 March 2015."
REPORT = "The interim report was published March 25, 2015 (Wednesday)."


def test_month_name_dates_are_restated_as_iso():
    assert iso_date_facts([CRASH, REPORT]) == [
        "24 March 2015 = 2015-03-24",
        "March 25, 2015 = 2015-03-25",
    ]
    assert iso_date_facts(["Filed Sept. 3 2014 and 1 Feb. 2016."]) == [
        "Sept. 3 2014 = 2014-09-03",
        "1 Feb. 2016 = 2016-02-01",
    ]


def test_numeric_and_impossible_dates_are_not_restated():
    assert iso_date_facts(["Filed 03/04/2015.", "On 31 February 2015."]) == []


def _validate(text: str):
    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="c",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "b",
                    "source_id": "report",
                    "document_version": "v",
                    "tenant_id": "t",
                    "heading_path": ["Timeline"],
                    "contributing_chunk_ids": ["c"],
                    "text": f"{CRASH}\n\n{REPORT}",
                },
            )
        ]
    )
    part = {"text": text, "support_ids": [unit.support_unit_id for unit in units]}
    answer = parse_support_unit_answer(json.dumps({"answer_parts": [part], "abstain": False}))
    return validate_support_unit_answer(answer, units)


def test_iso_dates_restating_the_units_pass():
    validation = _validate("Incident date: 2015-03-24. Report date: 2015-03-25.")

    assert validation.failure_codes == []


def test_an_iso_date_the_units_do_not_print_is_still_blocked():
    validation = _validate("Incident date: 2015-03-26.")

    assert validation.application_abstain is True
