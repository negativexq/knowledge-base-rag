"""In-process sliding-window rate limiter for POST /chat.

Deliberately small: one deque of request timestamps per key, no external
store. Each uvicorn worker keeps its own counters, so with N workers the
effective limit is up to N times the configured one. A shared store (e.g.
Redis) is the upgrade path if the backend ever runs multi-worker.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive; disable the limiter instead")
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}

    def check(self, key: str) -> int | None:
        """Record a request for `key` if it is within the limit and return
        None; otherwise record nothing and return the whole seconds until a
        slot frees up (for a Retry-After header)."""
        now = self._clock()
        self._evict_idle_keys(now)
        timestamps = self._requests.setdefault(key, deque())
        cutoff = now - self._window
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self._limit:
            return max(1, math.ceil(timestamps[0] + self._window - now))
        timestamps.append(now)
        return None

    def tracked_keys(self) -> int:
        return len(self._requests)

    def _evict_idle_keys(self, now: float) -> None:
        cutoff = now - self._window
        idle = [key for key, ts in self._requests.items() if not ts or ts[-1] <= cutoff]
        for key in idle:
            del self._requests[key]
