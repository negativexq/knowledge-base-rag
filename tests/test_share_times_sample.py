"""206, 219, 225, 227 ask how many people; the survey prints shares and a
sample size. A prompt rule asking for share × sample size (PR #57) gained none
of them on the full luna run (the model said the size was not given) and came
with counts dropped (513, 835) and financial ratios abstained (1015, 1021,
1024), so it was reverted. The calculation check itself handles such a
calculation when the model writes one."""

from app.llm.calculation import Calculation, verify_calculation
from app.llm.structured_output import DERIVED_ANSWER_INSTRUCTIONS


def test_the_share_times_sample_rule_stays_out_of_the_instructions():
    assert "how many people" not in DERIVED_ANSWER_INSTRUCTIONS
    assert "36 / 100 * 1503" not in DERIVED_ANSWER_INSTRUCTIONS


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
