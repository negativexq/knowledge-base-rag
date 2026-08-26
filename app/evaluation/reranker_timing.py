"""Pure helpers for controlled reranker timing and input equivalence."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
import time
from collections.abc import Callable, Sequence


def candidate_text_fingerprint(
    query: str, texts: Sequence[str], token_lengths: Sequence[int] | None = None
) -> dict:
    measured_lengths = (
        list(token_lengths) if token_lengths is not None else [len(text) for text in texts]
    )
    payload = {"query": query, "texts": list(texts)}
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return {
        "sha256": digest,
        "candidate_count": len(texts),
        "text_lengths": [len(text) for text in texts],
        "token_lengths": measured_lengths,
    }


def balanced_config_order(configs: Sequence[str], repetitions: int, seed: int) -> list[str]:
    """Return a deterministic, balanced order with one permutation per round."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    result: list[str] = []
    for round_number in range(repetitions):
        round_configs = list(configs)
        random.Random(seed + round_number).shuffle(round_configs)
        result.extend(round_configs)
    return result


def timed_call(call: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    result = call()
    return result, (time.perf_counter() - started) * 1000


def summarize_latencies(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean_ms": None,
            "median_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
            "stddev_ms": None,
        }
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return {
        "count": len(values),
        "mean_ms": round(statistics.mean(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
        "stddev_ms": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
    }
