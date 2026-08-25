import math
from dataclasses import dataclass

from app.evaluation.bootstrap import BootstrapCI

# One-sided z critical values for common alpha/power levels — used by
# power_analysis() below. A tiny lookup rather than pulling in scipy for
# two numbers; only the levels this sprint actually needs are covered.
_Z_ALPHA_ONE_SIDED = {0.05: 1.6449, 0.025: 1.9600}
_Z_POWER = {0.80: 0.8416, 0.90: 1.2816}


@dataclass(frozen=True)
class NonInferiorityResult:
    """delta convention is ALWAYS `quality_large - quality_small`
    (Sprint 21: quality_4B - quality_0.6B) — positive delta means the
    larger/more-expensive config scored higher. This is the opposite
    sign from Sprint 20's bootstrap report (which used small - large);
    Sprint 21 deliberately flips it because non-inferiority testing
    conventionally frames the question as "how much worse is the
    candidate than the reference," and reference-minus-candidate keeps
    that quantity positive when the candidate is worse — see
    docs/sprint-21-plan.md for the full worked example. Getting this
    backwards silently flips the verdict, which is exactly the mistake
    this sprint was asked to guard against in code and docs.
    """

    metric: str
    margin: float
    observed_delta: float  # large - small
    ci_lower: float
    ci_upper: float
    is_non_inferior: bool  # True iff ci_upper < margin (worst case for small still within margin)
    seed: int
    iterations: int


def evaluate_non_inferiority(ci: BootstrapCI, margin: float) -> NonInferiorityResult:
    """Non-inferiority verdict from a bootstrap CI of (large - small).

    CORRECT direction, spelled out so it can't be misread: `small` is
    judged non-inferior to `large` only if we can be CONFIDENT the true
    gap (large - small) does NOT exceed the margin — i.e. even the most
    PESSIMISTIC plausible value for the gap (the CI's UPPER bound, since
    a bigger "large - small" means small did worse) still comes in under
    the margin. That is `ci.upper < margin`, NOT `ci.lower < margin`
    (which would almost always be true and would wrongly declare
    non-inferiority any time the average case looks fine, ignoring the
    downside tail — the exact "wrong-direction CI interpretation" this
    sprint was told to avoid).

    Worked example: margin=0.04, ci=[0.01, 0.03] -> upper (0.03) < 0.04
    -> non-inferior (even the worst case within the CI is a small gap).
    ci=[0.01, 0.06] -> upper (0.06) >= 0.04 -> NOT non-inferior (the
    worst case within the CI exceeds the tolerated gap), even though the
    lower bound and the point estimate both look fine.
    """
    return NonInferiorityResult(
        metric=ci.metric,
        margin=margin,
        observed_delta=ci.observed_delta,
        ci_lower=ci.lower,
        ci_upper=ci.upper,
        is_non_inferior=ci.upper < margin,
        seed=ci.seed,
        iterations=ci.iterations,
    )


@dataclass(frozen=True)
class PowerAnalysisResult:
    current_n: int
    margin: float
    observed_paired_stddev: float
    required_n_80_power: int
    required_n_90_power: int
    method: str
    limitations: str


def paired_delta_stddev(values_large: list[float], values_small: list[float]) -> float:
    if len(values_large) != len(values_small):
        raise ValueError("paired_delta_stddev requires equal-length paired samples")
    n = len(values_large)
    if n < 2:
        raise ValueError("paired_delta_stddev requires at least 2 paired observations")
    deltas = [a - b for a, b in zip(values_large, values_small)]
    mean = sum(deltas) / n
    variance = sum((d - mean) ** 2 for d in deltas) / (n - 1)
    return math.sqrt(variance)


def required_sample_size(stddev: float, margin: float, power: float, alpha: float = 0.05) -> int:
    """Normal-approximation sample size for a one-sided non-inferiority
    test: n = ((z_alpha + z_power) * sigma / margin)^2, rounded up.

    APPROXIMATE, explicitly: per-question Recall@5 here is a
    binary/near-binary paired outcome (each question has exactly one
    expected location), not a continuous normal variable — treating the
    paired-difference stddev as if it fed a normal-approximation formula
    is a common, standard approximation for this kind of proportions-like
    paired test, but it is NOT an exact power calculation. Stated as a
    limitation in every report this function's output appears in.
    """
    if margin <= 0:
        raise ValueError("required_sample_size requires margin > 0")
    if stddev <= 0:
        raise ValueError("required_sample_size requires stddev > 0")
    z_alpha = _Z_ALPHA_ONE_SIDED[alpha]
    z_power = _Z_POWER[power]
    n = ((z_alpha + z_power) * stddev / margin) ** 2
    return math.ceil(n)


def power_analysis(
    values_large: list[float], values_small: list[float], margin: float, alpha: float = 0.05
) -> PowerAnalysisResult:
    stddev = paired_delta_stddev(values_large, values_small)
    return PowerAnalysisResult(
        current_n=len(values_large),
        margin=margin,
        observed_paired_stddev=stddev,
        required_n_80_power=required_sample_size(stddev, margin, power=0.80, alpha=alpha),
        required_n_90_power=required_sample_size(stddev, margin, power=0.90, alpha=alpha),
        method=(
            "Normal approximation for a one-sided non-inferiority test: "
            "n = ((z_alpha + z_power) * sigma / margin)^2, using the OBSERVED "
            "paired per-question delta standard deviation as sigma."
        ),
        limitations=(
            "Per-question Recall@5 is a near-binary paired outcome, not continuous — "
            "this is a standard but approximate normal-approximation formula, not an "
            "exact binomial/McNemar power calculation. The observed stddev is itself a "
            "single-sample estimate (its own uncertainty is not propagated). Treat the "
            "required-n figures as an order-of-magnitude guide, not a precise target."
        ),
    )


def production_decision(
    non_inferiority_result: NonInferiorityResult,
    material_margin: float,
    small_label: str,
    large_label: str,
) -> dict:
    """Sprint 21's exactly-3-verdict production decision, deterministic:

        if 0.6B (small) is non-inferior to 4B (large):
            ADOPT small
        elif 4B's advantage is BOTH statistically confident (CI lower
             bound of (large - small) > 0, i.e. the interval doesn't
             touch/cross zero) AND practically material (observed delta
             > material_margin):
            ADOPT large
        else:
            NEED_MORE_DATA
    """
    if non_inferiority_result.is_non_inferior:
        return {
            "verdict": f"ADOPT_{_slug(small_label)}",
            "reason": (
                f"{small_label} is non-inferior to {large_label} on "
                f"{non_inferiority_result.metric} — the bootstrap CI's upper bound "
                f"({non_inferiority_result.ci_upper:.4f}) stays under the pre-committed "
                f"margin ({non_inferiority_result.margin})."
            ),
        }

    statistically_confident = non_inferiority_result.ci_lower > 0
    practically_material = non_inferiority_result.observed_delta > material_margin
    if statistically_confident and practically_material:
        return {
            "verdict": f"ADOPT_{_slug(large_label)}",
            "reason": (
                f"{large_label}'s advantage over {small_label} on {non_inferiority_result.metric} "
                f"is both statistically confident (CI lower bound "
                f"{non_inferiority_result.ci_lower:.4f} > 0) and practically material "
                f"(observed delta {non_inferiority_result.observed_delta:.4f} > {material_margin})."
            ),
        }

    return {
        "verdict": "NEED_MORE_DATA",
        "reason": (
            f"{small_label} is not confirmed non-inferior to {large_label} on "
            f"{non_inferiority_result.metric} (CI upper bound "
            f"{non_inferiority_result.ci_upper:.4f} >= margin {non_inferiority_result.margin}), "
            "but the advantage is not both statistically confident and practically material "
            "enough to confidently adopt the larger config either."
        ),
    }


def _slug(label: str) -> str:
    return label.replace("@", "_").replace(".", "_").replace("-", "_").upper()
