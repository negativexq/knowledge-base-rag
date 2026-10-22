"""Request-local progress channel with cancellation propagation and no model drafts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from app.llm.research_stages import StageTracker, tracking

_emitter: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "research_progress_emitter", default=None
)


def publish(event: dict[str, Any]) -> None:
    emit = _emitter.get()
    if emit is not None:
        emit(event)


async def with_progress(work: Awaitable[Any]) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
    loop = asyncio.get_running_loop()

    def emit(event: dict[str, Any]) -> None:
        # Sync tool/validator callbacks can execute in worker threads.
        def enqueue() -> None:
            if not queue.full():
                queue.put_nowait(event)

        loop.call_soon_threadsafe(enqueue)

    tracker = StageTracker(emit)

    async def run() -> Any:
        try:
            result = await work
        except BaseException as exc:
            if not isinstance(exc, asyncio.CancelledError):
                tracker.finish(exc)
            raise
        tracker.finish()
        return result

    token = _emitter.set(emit)
    with tracking(tracker):
        task = asyncio.ensure_future(run())
    _emitter.reset(token)
    pending: asyncio.Task[dict[str, Any]] | None = None
    try:
        while not task.done() or not queue.empty():
            pending = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({task, pending}, return_when=asyncio.FIRST_COMPLETED)
            if pending in done:
                yield {"type": "research_progress", **pending.result()}
            else:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            pending = None
        yield {"type": "candidate", "candidate": await task}
    finally:
        if pending is not None:
            pending.cancel()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, *([pending] if pending else []), return_exceptions=True)
