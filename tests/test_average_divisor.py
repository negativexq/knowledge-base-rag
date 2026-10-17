"""luna resolver 1073: an average equity, "(3020 + 2795) / 2", was rejected
(CALCULATION_OPERAND_UNSUPPORTED): 2 is printed in no unit. Dividing a sum of
n terms by n is an average; that n needs no citation. Any other uncited
number still fails."""

from app.llm.calculation import Calculation, verify_calculation

UNITS = ["Total equity | January 28, 2023: 2,795 | January 29, 2022: 3,020", "Net earnings 1,419"]


def test_a_sum_divided_by_its_term_count_is_an_average():
    calculation = Calculation("1419 / ((3020 + 2795) / 2) * 100", "48.80")

    assert verify_calculation(calculation, UNITS, "Return on average equity: 48.80%.") == []


def test_other_uncited_divisors_still_fail():
    for expression, result in (
        ("(3020 + 2795) / 3", "1938.33"),
        ("3020 / 2", "1510"),
        ("(3020 + 2795 + 1419) / 2", "3617"),
    ):
        assert verify_calculation(Calculation(expression, result), UNITS, f"It is {result}.") == [
            "CALCULATION_OPERAND_UNSUPPORTED"
        ]
