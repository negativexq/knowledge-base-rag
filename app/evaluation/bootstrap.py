import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapCI:
    metric: str
    subset: str
    observed_delta: float
    lower: float
    upper: float
    seed: int
    iterations: int

    def excludes_zero(self) -> bool:
        return self.lower > 0 or self.upper < 0


def paired_bootstrap_ci(
    values_a: list[float],
    values_b: list[float],
    metric: str,
    subset: str,
    seed: int,
    iterations: int = 5000,
    confidence: float = 0.95,
) -> BootstrapCI:
    """Paired bootstrap confidence interval for the mean delta (a - b)
    over a per-question metric — "paired" because every question in this
    benchmark is scored by BOTH configs being compared, so each bootstrap
    resample draws the SAME question indices for both sides rather than
    resampling a and b independently (which would overstate variance by
    ignoring that per-question difficulty correlates between configs).

    Deterministic: a random.Random(seed) instance owns all randomness —
    no global random state touched, no dependency on call order, so the
    same (values_a, values_b, seed, iterations) always produces the
    exact same interval. Sprint 20's own rule (see docs/sprint-20-plan.md):
    "bootstrap implementasyonu deterministic ve unit-testable olsun."
    """
    if len(values_a) != len(values_b):
        raise ValueError(
            f"paired_bootstrap_ci requires equal-length paired samples, got "
            f"{len(values_a)} and {len(values_b)}"
        )
    n = len(values_a)
    if n == 0:
        raise ValueError("paired_bootstrap_ci requires at least one paired observation")

    rng = random.Random(seed)
    deltas = [a - b for a, b in zip(values_a, values_b)]
    observed_delta = sum(deltas) / n

    resample_means = []
    for _ in range(iterations):
        indices = [rng.randrange(n) for _ in range(n)]
        resample = [deltas[i] for i in indices]
        resample_means.append(sum(resample) / n)

    resample_means.sort()
    alpha = 1 - confidence
    lower_index = int((alpha / 2) * iterations)
    upper_index = int((1 - alpha / 2) * iterations) - 1
    upper_index = min(upper_index, iterations - 1)

    return BootstrapCI(
        metric=metric,
        subset=subset,
        observed_delta=observed_delta,
        lower=resample_means[lower_index],
        upper=resample_means[upper_index],
        seed=seed,
        iterations=iterations,
    )
