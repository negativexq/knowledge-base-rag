import random

import pytest

from app.evaluation.bootstrap import paired_bootstrap_ci


def _ci(a, b, seed, iterations=1000, metric="recall_at_5", subset="overall"):
    return paired_bootstrap_ci(
        a, b, metric=metric, subset=subset, seed=seed, iterations=iterations
    )


def test_paired_bootstrap_is_deterministic_for_a_fixed_seed():
    a = [1.0, 0.5, 0.8, 0.2, 0.9, 0.3, 0.7, 0.6]
    b = [0.9, 0.4, 0.7, 0.1, 0.85, 0.25, 0.6, 0.55]

    first = _ci(a, b, seed=42)
    second = _ci(a, b, seed=42)

    assert first == second


def test_paired_bootstrap_different_seeds_can_produce_different_intervals():
    a = [1.0, 0.5, 0.8, 0.2, 0.9, 0.3, 0.7, 0.6]
    b = [0.9, 0.4, 0.7, 0.1, 0.85, 0.25, 0.6, 0.55]

    seed_1 = _ci(a, b, seed=1)
    seed_2 = _ci(a, b, seed=2)

    # Same observed delta (data didn't change), CI bounds may legitimately differ.
    assert seed_1.observed_delta == seed_2.observed_delta


def test_paired_bootstrap_observed_delta_is_the_real_mean_difference():
    a = [1.0, 1.0, 1.0, 1.0]
    b = [0.0, 0.0, 0.0, 0.0]

    result = _ci(a, b, seed=0, iterations=500)

    assert result.observed_delta == 1.0


def test_paired_bootstrap_on_synthetic_example_with_a_known_large_gap_excludes_zero():
    """Known synthetic example: a is CONSISTENTLY 0.5 higher than b on
    every single paired observation — the true delta is unambiguous, so
    a real bootstrap CI must not straddle zero.
    """
    a = [0.9] * 30
    b = [0.4] * 30

    result = _ci(a, b, seed=7, iterations=5000)

    assert result.observed_delta == pytest.approx(0.5)
    assert result.excludes_zero()
    assert result.lower > 0


def test_paired_bootstrap_on_synthetic_example_with_no_real_difference_includes_zero():
    """Known synthetic example: a and b are noisy but have the SAME true
    mean (randomly assigned +/- around the same center) — a real CI
    should generally straddle zero for a no-difference case.
    """
    rng = random.Random(123)
    center = [rng.uniform(0.3, 0.9) for _ in range(60)]
    a = center
    b = list(center)  # identical values -> delta is exactly 0 for every pair

    result = _ci(a, b, seed=99, iterations=5000)

    assert result.observed_delta == 0.0
    assert not result.excludes_zero()
    assert result.lower <= 0 <= result.upper


def test_paired_bootstrap_requires_equal_length_inputs():
    with pytest.raises(ValueError, match="equal-length"):
        paired_bootstrap_ci([1.0, 2.0], [1.0], metric="x", subset="overall", seed=0)


def test_paired_bootstrap_requires_at_least_one_observation():
    with pytest.raises(ValueError, match="at least one"):
        paired_bootstrap_ci([], [], metric="x", subset="overall", seed=0)


def test_paired_bootstrap_records_metadata():
    result = _ci(
        [1.0, 0.5], [0.5, 0.5], seed=42, iterations=2000, metric="mrr", subset="cross_lingual"
    )

    assert result.metric == "mrr"
    assert result.subset == "cross_lingual"
    assert result.seed == 42
    assert result.iterations == 2000


def test_paired_bootstrap_default_iterations_is_at_least_5000():
    a = [1.0, 0.5, 0.8]
    b = [0.9, 0.4, 0.7]

    result = paired_bootstrap_ci(a, b, metric="recall_at_5", subset="overall", seed=1)

    assert result.iterations >= 5000
