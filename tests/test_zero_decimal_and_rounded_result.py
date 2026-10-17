"""Two answerable rows the full luna run still blocked on format:

- 221: "12 percentage points (float format: 12.0)": "12.0" was typed VERSION,
  so it met the support's "12" as INDETERMINATE. A decimal whose fraction is
  all zeros, with no version word before it, is the whole number.
- 741: "10 / 24 * 100 = 41.6666666667", stated as "about 42%": the answer may
  state the result rounded to its own precision.
"""

from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_validator_runtime import audit_critical_value
from app.llm.calculation import Calculation, verify_calculation


def _typed(text: str) -> list[tuple[str, str]]:
    return [(o.normalized_value, o.lexical_type) for o in extract_critical_occurrences(text)]


def test_a_zero_fraction_decimal_is_the_whole_number():
    assert _typed("a gap of 12.0 points") == _typed("a gap of 12 points")
    assert _typed("a gap of 12.00 points") == _typed("a gap of 12 points")


def test_versions_and_real_decimals_keep_their_type():
    assert _typed("upgrade to version 12.0")[0][1] == "VERSION"
    assert _typed("release 2.0 ships")[0][1] == "VERSION"
    assert _typed("a gap of 12.5 points") != _typed("a gap of 12 points")


def test_the_221_answer_passes_against_its_calculation():
    claim = "The percentage gap is 12 percentage points (float format: 12.0)."
    support = ["Smartphone owners 65", "Tablet owners 53", "65 - 53 = 12"]

    assert audit_critical_value(claim, support)["validator_outcome"] == "PASS"
    assert audit_critical_value(claim.replace("12.0", "13.0"), support)["validator_outcome"] != (
        "PASS"
    )


TWEETS = ["Of the 24 focused tweets, 10 were in English."]


def test_a_result_rounded_to_the_answers_precision_is_stated():
    calculation = Calculation("10 / 24 * 100", "41.6666666667")

    for text in ("which is about 42%.", "which is 41.7%.", "which is 41.67%."):
        assert verify_calculation(calculation, TWEETS, text) == []
    assert verify_calculation(calculation, TWEETS, "which is about 43%.") == [
        "CALCULATION_RESULT_NOT_IN_ANSWER"
    ]
    assert verify_calculation(calculation, TWEETS, "which is 41.2%.") == [
        "CALCULATION_RESULT_NOT_IN_ANSWER"
    ]


def test_the_fact_line_writes_the_rounded_result_as_stated():
    calculation = Calculation("10 / 24 * 100", "41.6666666667")

    assert calculation.fact("which is about 42%.") == "10 / 24 * 100 = 42%"


def test_the_741_answer_passes_with_its_fact_line():
    claim = "Germanwings posted 10 tweets in English out of 24 focused tweets, which is about 42%."
    fact = Calculation("10 / 24 * 100", "41.6666666667").fact(claim)

    assert audit_critical_value(claim, [*TWEETS, fact])["validator_outcome"] == "PASS"
