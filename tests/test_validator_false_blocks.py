"""Two ways the critical-value validator blocked correct answers (luna scoped
40/14 trace, 39 validator_blocked rows):

- The locale guard flagged a grouped number whenever its digits were in the
  support, even written identically: "$1,874 million" citing "1,874" was
  INDETERMINATE (1013, 1071, 1076, 1078, 1082). Only the same digits under a
  different separator ("1.874" vs "1,874") are ambiguous.
- Values the answer repeats from the question were validated as claims: "FY
  2021" or "65+" is not in the cited table row, so the claim conflicted (1014,
  1019, 1022, 221, 225, ...). A question value that the evidence also holds
  is a grounded premise and is not validated, as long as the answer part
  states another value that is; an answer made only of question values (a
  yes/no confirmation) is still validated in full."""

import json

from app.evaluation.critical_validator_runtime import audit_critical_value
from app.evaluation.critical_values import _v3_ambiguous_locale_pair
from app.evidence.support_units import build_support_units
from app.llm.structured_output import parse_support_unit_answer, validate_support_unit_answer
from app.retrieval.hybrid_search import SearchResult

CASH_CLAIM = "Cash and cash equivalents were $1,874 million as of January 28, 2023."
CASH_ROW = "Cash and cash equivalents | January 28, 2023: $ | 1,874 | January 29, 2022: $ | 2,936"


def test_a_grouped_number_written_as_in_the_support_is_not_ambiguous():
    assert not _v3_ambiguous_locale_pair(CASH_CLAIM, CASH_ROW)
    assert audit_critical_value(CASH_CLAIM, [CASH_ROW])["validator_outcome"] == "PASS"


def test_the_same_digits_under_another_separator_stay_ambiguous():
    support = "Cash and cash equivalents | January 28, 2023 | 1.874"

    assert _v3_ambiguous_locale_pair(CASH_CLAIM, support)
    assert audit_critical_value(CASH_CLAIM, [support])["validator_outcome"] == "INDETERMINATE"


QUESTION = "What is total liabilities for COSTCO in FY 2021?"
HEADER = "CONSOLIDATED BALANCE SHEETS | August 29, 2021 | August 30, 2020"
ROW = "TOTAL LIABILITIES | 41,190 | 36,851"


def _units():
    return build_support_units(
        [
            SearchResult(
                score=1.0,
                id="chunk-1",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "block-1",
                    "source_id": "costco",
                    "document_version": "v1",
                    "tenant_id": "tenant-a",
                    "heading_path": ["Balance sheet"],
                    "contributing_chunk_ids": ["chunk-1"],
                    "text": f"{HEADER}\n\n{ROW}",
                },
            )
        ]
    )


def _validate(text: str, question: str | None = QUESTION):
    units = _units()
    row_id = next(unit.support_unit_id for unit in units if unit.text == ROW)
    answer = parse_support_unit_answer(
        json.dumps({"answer_parts": [{"text": text, "support_ids": [row_id]}], "abstain": False})
    )
    return validate_support_unit_answer(answer, units, question=question)


def _outcome(validation) -> str:
    return validation.validator_telemetry["critical_inputs"][0]["audit"]["validator_outcome"]


def test_a_question_value_the_evidence_holds_is_not_validated_as_a_claim():
    validation = _validate("Costco's total liabilities in FY 2021 were $41,190 million.")

    assert _outcome(validation) == "PASS"
    assert validation.application_abstain is False
    audit = validation.validator_telemetry["critical_inputs"][0]["audit"]
    assert audit["skip_query_echo_count"] == 1
    assert validation.validator_telemetry["skip_query_echo_count"] == 1


def test_a_wrong_answer_value_still_conflicts():
    validation = _validate("Costco's total liabilities in FY 2021 were $40,000 million.")

    assert _outcome(validation) == "REJECT"


def test_a_question_value_the_evidence_lacks_is_still_validated():
    question = "What is total liabilities for COSTCO in FY 2019?"
    validation = _validate("Costco's total liabilities in FY 2019 were $41,190 million.", question)

    assert _outcome(validation) == "REJECT"


def test_an_answer_made_only_of_question_values_is_validated_in_full():
    question = "Were Costco's total liabilities 36,851 in FY 2021?"
    validation = _validate("Yes, total liabilities in FY 2021 were 36,851.", question)

    assert _outcome(validation) != "PASS"


def test_without_a_question_every_value_is_validated_as_before():
    validation = _validate("Costco's total liabilities in FY 2021 were $41,190 million.", None)

    assert _outcome(validation) == "REJECT"


TRACE_QUESTION = (
    "How to resolve the StaleConnectionException? My trace shows "
    "java.sql.SQLException: ORA-02396: exceeded maximum idle time"
)
POOL_TEXT = "Set Minimum connections to 0 so idle pooled connections are not retained."


def _validate_text(text: str, support: str, question: str, *, scope_reviewed: bool):
    units = build_support_units(
        [
            SearchResult(
                score=1.0,
                id="chunk-1",
                payload={
                    "evidence_id": "E1",
                    "evidence_block_id": "block-1",
                    "source_id": "technote",
                    "document_version": "v1",
                    "tenant_id": "tenant-a",
                    "heading_path": ["Technote"],
                    "contributing_chunk_ids": ["chunk-1"],
                    "text": support,
                },
            )
        ]
    )
    answer = parse_support_unit_answer(
        json.dumps(
            {
                "answer_parts": [{"text": text, "support_ids": [units[0].support_unit_id]}],
                "abstain": False,
            }
        )
    )
    return validate_support_unit_answer(
        answer, units, question=question, question_scope_reviewed=scope_reviewed
    )


def test_a_question_value_the_evidence_lacks_is_a_premise_when_scope_review_follows():
    # TechQA Q252: the answer repeats the user's own Oracle error code, which
    # the cited technote never prints; the pool setting is still checked.
    text = "Your trace shows ORA-02396, so set Minimum connections to 0."

    reviewed = _validate_text(text, POOL_TEXT, TRACE_QUESTION, scope_reviewed=True)
    unreviewed = _validate_text(text, POOL_TEXT, TRACE_QUESTION, scope_reviewed=False)

    assert _outcome(reviewed) == "PASS"
    assert _outcome(unreviewed) == "REJECT"


def test_an_answer_value_outside_the_question_is_validated_when_scope_review_follows():
    text = "Your trace shows ORA-02396, so set Minimum connections to 5."

    assert _outcome(_validate_text(text, POOL_TEXT, TRACE_QUESTION, scope_reviewed=True)) == (
        "REJECT"
    )


def test_an_answer_of_only_question_values_is_validated_when_scope_review_follows():
    question = "Were Costco's total liabilities 36,851 in FY 2019?"
    text = "Yes, total liabilities in FY 2019 were 36,851."

    validation = _validate_text(text, f"{HEADER}\n\n{ROW}", question, scope_reviewed=True)

    assert _outcome(validation) != "PASS"
