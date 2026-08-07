"""Sprint 14: proves embed_texts_concurrently() actually runs embed_fn
calls in parallel, bounded by the configured concurrency — not just that
it finishes fast. A wall-clock-only assertion can't tell real bounded
parallelism apart from an accidentally-unbounded gather or a no-op
semaphore, so these track the actual number of in-flight calls.
"""

import asyncio

import pytest

from app.ingestion.ingest import embed_texts_concurrently


def _tracking_embed_fn(delay: float = 0.02):
    """Returns (embed_fn, get_max_concurrent) — embed_fn increments an
    in-flight counter on entry, records the running max, sleeps, then
    decrements on exit.
    """
    in_flight = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def embed_fn(text: str) -> list[float]:
        nonlocal in_flight, max_concurrent
        async with lock:
            in_flight += 1
            max_concurrent = max(max_concurrent, in_flight)
        await asyncio.sleep(delay)
        async with lock:
            in_flight -= 1
        return [float(len(text))]

    return embed_fn, lambda: max_concurrent


@pytest.mark.asyncio
async def test_respects_the_configured_concurrency_limit_exactly():
    embed_fn, get_max_concurrent = _tracking_embed_fn()
    texts = [f"chunk {i}" for i in range(12)]

    await embed_texts_concurrently(texts, embed_fn, concurrency=4)

    assert get_max_concurrent() == 4


@pytest.mark.asyncio
async def test_concurrency_one_is_effectively_sequential():
    embed_fn, get_max_concurrent = _tracking_embed_fn()
    texts = [f"chunk {i}" for i in range(6)]

    await embed_texts_concurrently(texts, embed_fn, concurrency=1)

    assert get_max_concurrent() == 1


@pytest.mark.asyncio
async def test_concurrency_higher_than_input_size_caps_at_input_size():
    embed_fn, get_max_concurrent = _tracking_embed_fn()
    texts = [f"chunk {i}" for i in range(3)]

    await embed_texts_concurrently(texts, embed_fn, concurrency=8)

    assert get_max_concurrent() == 3


@pytest.mark.asyncio
async def test_preserves_input_order_regardless_of_completion_order():
    # Earlier texts sleep LONGER than later ones, so if order weren't
    # preserved by construction, the naturally-first-to-complete (later,
    # shorter) results would come back out of order.
    async def variable_delay_embed(text: str) -> list[float]:
        index = int(text.split()[-1])
        await asyncio.sleep(0.03 - index * 0.005)
        return [float(index)]

    texts = [f"chunk {i}" for i in range(5)]

    results = await embed_texts_concurrently(texts, variable_delay_embed, concurrency=5)

    assert results == [[0.0], [1.0], [2.0], [3.0], [4.0]]


@pytest.mark.asyncio
async def test_a_failing_embed_call_propagates():
    async def flaky_embed(text: str) -> list[float]:
        if text == "bad":
            raise RuntimeError("simulated embed failure")
        return [0.1]

    with pytest.raises(RuntimeError, match="simulated embed failure"):
        await embed_texts_concurrently(["good", "bad", "good"], flaky_embed, concurrency=2)


@pytest.mark.asyncio
async def test_empty_input_returns_empty_list():
    async def embed_fn(text: str) -> list[float]:
        raise AssertionError("should never be called")

    assert await embed_texts_concurrently([], embed_fn, concurrency=4) == []
