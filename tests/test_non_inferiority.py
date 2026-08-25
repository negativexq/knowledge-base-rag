import pytest

from app.evaluation.bootstrap import BootstrapCI
from app.evaluation.non_inferiority import (
    evaluate_non_inferiority,
    paired_delta_stddev,
    power_analysis,
    production_decision,
    required_sample_size,
)


def _ci(lower, upper, observed=None, metric="recall_at_5"):
    return BootstrapCI(
        metric=metric, subset="cross_lingual",
        observed_delta=observed if observed is not None else (lower + upper) / 2,
        lower=lower, upper=upper, seed=1, iterations=10000,
    )


# ---- direction correctness: the exact thing this sprint was told to guard ----


def test_non_inferior_when_ci_upper_bound_is_under_the_margin():
    """Worked example from the module docstring: ci=[0.01, 0.03],
    margin=0.04 -> non-inferior (even the CI's pessimistic upper bound
    stays under the margin).
    """
    result = evaluate_non_inferiority(_ci(lower=0.01, upper=0.03), margin=0.04)

    assert result.is_non_inferior


def test_not_non_inferior_when_ci_upper_bound_exceeds_the_margin_even_if_point_estimate_is_fine():
    """The exact "wrong-direction" trap: point estimate/lower bound look
    fine, but the CI's upper (pessimistic) bound exceeds the margin —
    must NOT be declared non-inferior.
    """
    result = evaluate_non_inferiority(_ci(lower=0.01, upper=0.06), margin=0.04)

    assert not result.is_non_inferior


def test_non_inferiority_is_not_determined_by_the_lower_bound():
    """A CI could have a NEGATIVE lower bound (small actually WON on some
    resamples) but if the upper bound still exceeds the margin, this is
    still not a confirmed non-inferior verdict — proves the function
    isn't accidentally keying off ci.lower.
    """
    result = evaluate_non_inferiority(_ci(lower=-0.10, upper=0.10), margin=0.04)

    assert not result.is_non_inferior


def test_evaluate_non_inferiority_records_the_margin_and_metric():
    result = evaluate_non_inferiority(_ci(lower=0.0, upper=0.02, metric="mrr"), margin=0.04)

    assert result.metric == "mrr"
    assert result.margin == 0.04


# ---- known synthetic cases ----


def test_known_synthetic_non_inferior_case():
    # Large barely beats small, tightly — real non-inferiority.
    result = evaluate_non_inferiority(_ci(lower=-0.01, upper=0.015), margin=0.04)

    assert result.is_non_inferior


def test_known_synthetic_inferior_case():
    # Large clearly and confidently beats small by a lot.
    result = evaluate_non_inferiority(_ci(lower=0.15, upper=0.25), margin=0.04)

    assert not result.is_non_inferior


# ---- production_decision: the 3 verdicts ----


def test_production_decision_adopts_small_when_non_inferior():
    ni = evaluate_non_inferiority(_ci(lower=0.01, upper=0.03), margin=0.04)

    decision = production_decision(ni, material_margin=0.04, small_label="qwen3-0.6b@768",
                                     large_label="qwen3-4b@1024")

    assert decision["verdict"] == "ADOPT_QWEN3_0_6B_768"


def test_production_decision_adopts_large_when_advantage_is_confident_and_material():
    ni = evaluate_non_inferiority(_ci(lower=0.10, upper=0.20, observed=0.15), margin=0.04)

    decision = production_decision(ni, material_margin=0.04, small_label="qwen3-0.6b@768",
                                     large_label="qwen3-4b@1024")

    assert decision["verdict"] == "ADOPT_QWEN3_4B_1024"


def test_production_decision_is_need_more_data_when_neither_condition_is_met():
    """Not non-inferior (upper bound exceeds margin), but also not
    confidently material (CI crosses zero) — Sprint 20's actual
    situation.
    """
    ni = evaluate_non_inferiority(_ci(lower=-0.01, upper=0.06, observed=0.02), margin=0.04)

    decision = production_decision(ni, material_margin=0.04, small_label="qwen3-0.6b@768",
                                     large_label="qwen3-4b@1024")

    assert decision["verdict"] == "NEED_MORE_DATA"


def test_production_decision_is_need_more_data_when_confident_but_not_material():
    """CI is entirely positive (statistically confident large > small)
    but the observed delta is tiny/below the material margin.
    """
    ni = evaluate_non_inferiority(_ci(lower=0.005, upper=0.06, observed=0.02), margin=0.04)

    decision = production_decision(ni, material_margin=0.04, small_label="qwen3-0.6b@768",
                                     large_label="qwen3-4b@1024")

    assert decision["verdict"] == "NEED_MORE_DATA"


# ---- power analysis ----


def test_paired_delta_stddev_of_identical_values_is_zero():
    a = [1.0, 1.0, 1.0]
    b = [1.0, 1.0, 1.0]

    assert paired_delta_stddev(a, b) == 0.0


def test_paired_delta_stddev_requires_equal_length():
    with pytest.raises(ValueError, match="equal-length"):
        paired_delta_stddev([1.0, 2.0], [1.0])


def test_paired_delta_stddev_requires_at_least_two_observations():
    with pytest.raises(ValueError, match="at least 2"):
        paired_delta_stddev([1.0], [1.0])


def test_required_sample_size_increases_as_margin_shrinks():
    large_margin_n = required_sample_size(stddev=0.3, margin=0.10, power=0.80)
    small_margin_n = required_sample_size(stddev=0.3, margin=0.02, power=0.80)

    assert small_margin_n > large_margin_n


def test_required_sample_size_increases_with_higher_power():
    n_80 = required_sample_size(stddev=0.3, margin=0.04, power=0.80)
    n_90 = required_sample_size(stddev=0.3, margin=0.04, power=0.90)

    assert n_90 > n_80


def test_required_sample_size_rejects_non_positive_margin():
    with pytest.raises(ValueError, match="margin"):
        required_sample_size(stddev=0.3, margin=0.0, power=0.80)


def test_power_analysis_reports_current_n_and_required_n_for_both_power_levels():
    values_large = [1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0]
    values_small = [1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0]

    result = power_analysis(values_large, values_small, margin=0.04)

    assert result.current_n == 8
    assert result.required_n_90_power >= result.required_n_80_power
    assert "approximat" in result.limitations.lower() or "approximat" in result.method.lower()


def test_power_analysis_is_deterministic():
    values_large = [1.0, 1.0, 0.0, 1.0, 1.0]
    values_small = [1.0, 0.0, 0.0, 1.0, 1.0]

    first = power_analysis(values_large, values_small, margin=0.04)
    second = power_analysis(values_large, values_small, margin=0.04)

    assert first == second
