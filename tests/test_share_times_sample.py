"""206, 219, 225, 227 ask how many people; the survey prints shares ("36%") and
a sample size ("n=537", "1,503 adults"). luna restated the share. The derived
answer instructions now say a count of people is the share times the group's
printed size, written as a calculation, which verifies like any other."""

from app.llm.calculation import Calculation, verify_calculation
from app.llm.structured_output import DERIVED_ANSWER_INSTRUCTIONS


def test_the_instructions_ask_for_share_times_sample_size():
    assert "36 / 100 * 1503" in DERIVED_ANSWER_INSTRUCTIONS
    assert "how many people" in DERIVED_ANSWER_INSTRUCTIONS


def test_a_share_times_sample_calculation_verifies():
    units = ["The survey of 1,503 adults was conducted April 25 - May 1, 2018.", "Poor 36%"]
    calculation = Calculation("36 / 100 * 1503", "541")

    assert verify_calculation(calculation, units, "About 541 adults rated them poor.") == []


def test_a_gap_times_sample_calculation_verifies():
    units = ["College graduate (n=537) 87ab", "College graduate (n=537) 31ab"]
    calculation = Calculation("(87 - 31) / 100 * 537", "301")

    assert verify_calculation(calculation, units, "The gap is about 301 people.") == []
    assert verify_calculation(
        Calculation("(87 - 31) / 100 * 573", "321"), units, "about 321 people"
    ) == ["CALCULATION_OPERAND_UNSUPPORTED"]
