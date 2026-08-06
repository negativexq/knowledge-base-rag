import asyncio

import pytest

from app.sync.models import TRIGGER_SCHEDULED
from app.sync.scheduler import SyncScheduler


class _SpySyncManager:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def trigger_sync(self, source_type: str, trigger: str):
        self.calls.append((source_type, trigger))


@pytest.mark.asyncio
async def test_scheduler_triggers_sync_repeatedly_at_the_configured_interval():
    spy = _SpySyncManager()
    scheduler = SyncScheduler(spy, intervals={"filesystem": 0.05})

    scheduler.start()
    await asyncio.sleep(0.23)
    await scheduler.stop()

    assert len(spy.calls) >= 3
    assert all(call == ("filesystem", TRIGGER_SCHEDULED) for call in spy.calls)


@pytest.mark.asyncio
async def test_scheduler_uses_a_separate_interval_per_connector():
    spy = _SpySyncManager()
    scheduler = SyncScheduler(spy, intervals={"fast": 0.03, "slow": 0.12})

    scheduler.start()
    await asyncio.sleep(0.2)
    await scheduler.stop()

    fast_calls = [c for c in spy.calls if c[0] == "fast"]
    slow_calls = [c for c in spy.calls if c[0] == "slow"]
    assert len(fast_calls) > len(slow_calls)
    assert len(slow_calls) >= 1


@pytest.mark.asyncio
async def test_stop_prevents_further_triggers():
    spy = _SpySyncManager()
    scheduler = SyncScheduler(spy, intervals={"filesystem": 0.03})

    scheduler.start()
    await asyncio.sleep(0.1)
    await scheduler.stop()
    count_after_stop = len(spy.calls)
    await asyncio.sleep(0.15)

    assert len(spy.calls) == count_after_stop


@pytest.mark.asyncio
async def test_a_failing_trigger_does_not_kill_the_loop():
    class _FlakySyncManager:
        def __init__(self):
            self.attempts = 0

        async def trigger_sync(self, source_type, trigger):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("boom")

    flaky = _FlakySyncManager()
    scheduler = SyncScheduler(flaky, intervals={"filesystem": 0.03})

    scheduler.start()
    await asyncio.sleep(0.13)
    await scheduler.stop()

    assert flaky.attempts >= 2  # kept going after the first failure


@pytest.mark.asyncio
async def test_start_is_idempotent_does_not_spawn_duplicate_loops():
    spy = _SpySyncManager()
    scheduler = SyncScheduler(spy, intervals={"filesystem": 0.05})

    scheduler.start()
    scheduler.start()  # must not create a second concurrent loop
    await asyncio.sleep(0.12)
    await scheduler.stop()

    # a single loop at 0.05s interval over ~0.12s fires ~2 times; two
    # overlapping loops would fire ~4 times
    assert len(spy.calls) <= 3
