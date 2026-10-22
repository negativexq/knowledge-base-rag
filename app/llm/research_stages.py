"""User-facing research stages derived from the workflow's own operation spans.

Stage messages are fixed application text keyed by stage and reason code; no
model output, prompt, argument or exception message reaches them.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

Status = Literal["running", "completed", "retrying", "failed"]

STAGE_MESSAGES = {
    "retrieval": "Searching the relevant documents",
    "answer_check": "Checking whether the evidence found already answers the question",
    "evidence_planning": "Working out what information the answer needs",
    "source_selection": "Selecting the relevant pages and tables",
    "source_reading": "Reading the selected pages",
    "extraction": "Extracting evidence from the documents",
    "input_review": "Checking the extracted values are correct and complete",
    "calculation": "Calculating from the checked values",
    "scope_validation": "Checking the result matches the question's scope",
    "evidence_repair": "Looking for the missing evidence",
    "finalization": "Writing up the verified result",
}

REASON_MESSAGES = {
    "scope_mismatch": "Result did not match the question's scope; re-checking the source",
    "input_check_failed": "An extracted value needs another look; re-reading its source",
    "incomplete_coverage": "Coverage is incomplete; inspecting more of the source",
    "missing_input": "An input is missing; locating it in the source",
    "no_new_evidence": "The last read added nothing new; trying another part of the document",
}

# Span name prefixes (most specific first) -> (stage, reason). Names not listed
# are wrappers or model calls and keep the current stage.
_STAGES: tuple[tuple[str, str, str | None], ...] = (
    ("quantity.repair.scope", "evidence_repair", "scope_mismatch"),
    ("quantity.repair.inputs", "evidence_repair", "input_check_failed"),
    ("quantity.repair", "evidence_repair", None),
    ("answer.repair", "evidence_repair", "incomplete_coverage"),
    ("inventory.coverage.followup", "evidence_repair", "incomplete_coverage"),
    ("quantity.inventory.progress", "evidence_repair", "incomplete_coverage"),
    ("quantity.gap.bind", "evidence_repair", "missing_input"),
    ("research.read_recovery", "evidence_repair", "no_new_evidence"),
    ("research.collection.resume", "evidence_repair", None),
    ("tool.search", "retrieval", None),
    ("tool.find_documents", "retrieval", None),
    ("research.requirements", "evidence_planning", None),
    ("research.prepare", "evidence_planning", None),
    ("research.decide", "evidence_planning", None),
    ("evidence.need.select", "evidence_planning", None),
    ("inventory.plan", "evidence_planning", None),
    ("quantity.contract", "evidence_planning", None),
    ("quantity.source.open", "source_reading", None),
    ("quantity.source.paginate", "source_reading", None),
    ("quantity.source.native", "source_reading", None),
    ("quantity.source.inspect", "source_reading", None),
    ("research.acquire.visual", "source_reading", None),
    ("document.read", "source_reading", None),
    ("tool.read", "source_reading", None),
    ("tool.inspect", "source_reading", None),
    ("quantity.source.complete", "extraction", None),
    ("quantity.source", "source_selection", None),
    ("quantity.context.bind", "source_selection", None),
    ("evidence.search", "source_selection", None),
    ("inventory.window", "source_selection", None),
    ("quantity.lookup", "extraction", None),
    ("quantity.normalize", "extraction", None),
    ("quantity.inventory.observe", "extraction", None),
    ("quantity.evidence.retain", "extraction", None),
    ("tool.extract", "extraction", None),
    ("quantity.review", "input_review", None),
    ("quantity.gap.review", "input_review", None),
    ("quantity.inventory.validate", "input_review", None),
    ("quantity.operation.correct", "input_review", None),
    ("quantity.notation.correct", "input_review", None),
    ("inventory.review", "input_review", None),
    ("evidence.extract.validate", "input_review", None),
    ("evidence.need.coverage", "input_review", None),
    ("research.disposition.admit", "input_review", None),
    ("quantity.execute", "calculation", None),
    ("calculation", "calculation", None),
    ("tool.calculate", "calculation", None),
    ("answer.scope", "scope_validation", None),
    ("answer.scope_validate", "scope_validation", None),
    ("answer.validate", "scope_validation", None),
    ("research.finalize", "finalization", None),
    ("research.fast_answer", "answer_check", None),
    ("evidence.need.present", "finalization", None),
)


def stage_for(name: str) -> tuple[str, str | None] | None:
    for prefix, stage, reason in _STAGES:
        if name == prefix or name.startswith(prefix + "."):
            return stage, reason
    return None


def stage_event(
    id: str,
    stage: str,
    status: Status,
    *,
    reason: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": id,
        "kind": "stage",
        "stage": stage,
        "status": status,
        "message": REASON_MESSAGES.get(reason or "", STAGE_MESSAGES[stage]),
    }
    if reason:
        event["reason"] = reason
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    return event


def _failure_reason(exc: BaseException) -> str:
    return "timeout" if isinstance(exc, TimeoutError) else "check_failed"


class StageTracker:
    """One request's stage timeline. Spans may close in worker threads."""

    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._count = 0
        self._current: dict[str, Any] | None = None

    def _close(self, status: Status) -> None:
        current, self._current = self._current, None
        if current is None:
            return
        failure = current["failure"]
        if failure is not None and status == "completed":
            # The workflow went on after this stage failed: it is being retried.
            status = "retrying"
        self._emit(
            stage_event(
                current["id"],
                current["stage"],
                status,
                reason=failure or current["reason"],
                duration_ms=round((time.monotonic() - current["started"]) * 1000),
            )
        )

    def enter(self, stage: str, reason: str | None) -> None:
        with self._lock:
            current = self._current
            if current is not None and current["stage"] == stage and current["failure"] is None:
                return
            self._close("completed")
            self._count += 1
            self._current = {
                "id": f"stage-{self._count}",
                "stage": stage,
                "reason": reason,
                "failure": None,
                "started": time.monotonic(),
            }
            self._emit(stage_event(self._current["id"], stage, "running", reason=reason))

    def fail(self, stage: str, exc: BaseException) -> None:
        with self._lock:
            if self._current is not None and self._current["stage"] == stage:
                self._current["failure"] = _failure_reason(exc)

    def finish(self, exc: BaseException | None = None) -> None:
        with self._lock:
            self._close("completed" if exc is None else "failed")


_tracker: ContextVar[StageTracker | None] = ContextVar("research_stage_tracker", default=None)
# Per-task stack of the enclosing stages, so a nested stage hands back to its parent.
_stack: ContextVar[tuple[tuple[str, str | None], ...]] = ContextVar(
    "research_stage_stack", default=()
)


@contextmanager
def tracking(tracker: StageTracker) -> Iterator[None]:
    token = _tracker.set(tracker)
    try:
        yield
    finally:
        _tracker.reset(token)


@contextmanager
def observe(name: str) -> Iterator[None]:
    tracker = _tracker.get()
    mapped = stage_for(name) if tracker is not None else None
    if tracker is None or mapped is None:
        yield
        return
    parent = _stack.get()
    _stack.set((*parent, mapped))
    tracker.enter(*mapped)
    resume = bool(parent)
    try:
        yield
    except asyncio.CancelledError:
        resume = False
        raise
    except Exception as exc:
        tracker.fail(mapped[0], exc)
        raise
    finally:
        # Restore rather than reset: an async generator can exit this span in
        # another context than the one that entered it.
        _stack.set(parent)
        if resume:
            tracker.enter(*parent[-1])
