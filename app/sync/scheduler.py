import asyncio
import logging

from app.shared.config import Settings
from app.sync.manager import SyncManager
from app.sync.models import TRIGGER_SCHEDULED

logger = logging.getLogger(__name__)


def sync_intervals_from_settings(settings: Settings) -> dict[str, float]:
    """Builds the generic dict[str, float] SyncScheduler needs from
    Settings' per-connector fields — only includes a connector if it's
    actually configured (Notion's interval is meaningless without an API
    key), so a caller can pass this straight to SyncScheduler without
    special-casing which connectors are active.
    """
    intervals = {"filesystem": settings.filesystem_sync_interval_seconds}
    if settings.notion_api_key:
        intervals["notion"] = settings.notion_sync_interval_seconds
    return intervals


class SyncScheduler:
    """Runs SyncManager.trigger_sync() for each connector on its own fixed
    interval — a plain asyncio loop, not APScheduler (see
    docs/sprint-07-plan.md for why: no cron expressions, persistent job
    stores, or misfire handling are needed for "every N seconds", and a
    hand-rolled loop is trivially testable with short real intervals).

    A scheduled tick that lands while a sync is already running (manual or
    from this same loop, though the loop itself can't overlap with itself)
    is simply rejected by SyncManager, exactly like a manual trigger would
    be — the scheduler doesn't need its own overlap handling.
    """

    def __init__(self, sync_manager: SyncManager, intervals: dict[str, float]):
        self._sync_manager = sync_manager
        self._intervals = intervals
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self) -> None:
        for source_type, interval in self._intervals.items():
            if source_type in self._tasks:
                continue
            self._tasks[source_type] = asyncio.create_task(self._loop(source_type, interval))

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _loop(self, source_type: str, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self._sync_manager.trigger_sync(source_type, TRIGGER_SCHEDULED)
            except Exception:
                # A scheduled tick failing must not kill the loop — the
                # next tick should still fire. SyncManager already records
                # ingest failures to history; this only guards against a
                # failure in the trigger call itself (e.g. an unknown
                # connector misconfigured at construction time).
                logger.exception("Scheduled sync failed for source_type=%s", source_type)
