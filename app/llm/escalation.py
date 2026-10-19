"""Classic-first answering: the agent is an escalation, not the entry point.

The fixed path (one structured call, then the operand resolver and visual
reading when enabled) answers first. Only a withheld answer escalates to the
research agent, which starts from the same evidence and is told the fixed
path's code-generated reason. An agent that runs out of budget or time after
admitting new evidence gets one fixed-path answer over that evidence instead of
an empty abstention. Every released answer still passes the release validators
of the path that produced it; nothing is merged across paths.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.forensic_capture import current_capture
from app.retrieval.hybrid_search import SearchResult

# Budget and time are the failures more evidence-backed generation can recover
# from; validator, scope and access rejections are decisions, never retried here.
RECOVERABLE_AGENT_FAILURES = frozenset({"AGENT_BUDGET_EXCEEDED", "AGENT_TIMEOUT"})
# Progress shows that work is happening; it carries no draft text.
LIVE_EVENTS = frozenset({"research_progress"})

Events = AsyncIterator[dict[str, Any]]


@dataclass(frozen=True)
class ClassicOutcome:
    answered: bool
    failure_codes: tuple[str, ...] = ()
    gathered: list[SearchResult] = field(default_factory=list)


def outcome_of(events: list[dict[str, Any]]) -> ClassicOutcome:
    verdict = next((e for e in reversed(events) if e["type"] == "security_validation"), None)
    gathered: list[SearchResult] = next(
        (e["blocks"] for e in reversed(events) if e["type"] == "evidence_update"), []
    )
    if verdict is None:
        return ClassicOutcome(False, (), gathered)
    return ClassicOutcome(
        not verdict["abstain"] or bool(verdict.get("visual_answer")),
        tuple(verdict.get("validator_failure_codes") or ()),
        gathered,
    )


def _labelled(events: list[dict[str, Any]], escalation: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**e, "escalation": escalation} if e["type"] == "metadata" else e for e in events]


async def classic_first(
    blocks: list[SearchResult],
    classic: Callable[[list[SearchResult]], Events],
    agent: Callable[[ClassicOutcome | None], Events],
    *,
    direct: bool = False,
    authorize: Callable[[list[SearchResult]], list[SearchResult]] | None = None,
) -> Events:
    escalation: dict[str, Any] = {"mode": "direct" if direct else "escalate"}
    capture = current_capture()
    first: ClassicOutcome | None = None
    if not direct:
        # The fixed path produces no user-visible text before validation, so
        # holding its events back costs no latency when it succeeds.
        held = [event async for event in classic(blocks)]
        first = outcome_of(held)
        escalation.update(
            escalated=not first.answered,
            classic_outcome="answered" if first.answered else "withheld",
            classic_failure_codes=list(first.failure_codes),
        )
        if first.answered:
            if capture is not None:
                capture.stage("escalation", escalation)
            for event in _labelled(held, escalation):
                yield event
            return
    else:
        escalation["escalated"] = True
    held = []
    async for event in agent(first):
        if event["type"] in LIVE_EVENTS:
            yield event
        else:
            held.append(event)
    result = outcome_of(held)
    gathered = authorize(result.gathered) if authorize else result.gathered
    known = {str(b.id) for b in blocks}
    if (
        not result.answered
        and RECOVERABLE_AGENT_FAILURES.intersection(result.failure_codes)
        and any(str(b.id) not in known for b in gathered)
    ):
        fallback = [event async for event in classic(gathered)]
        if outcome_of(fallback).answered:
            escalation["fallback"] = "classic_over_gathered_evidence"
            escalation["agent_failure_codes"] = list(result.failure_codes)
            if capture is not None:
                capture.stage("escalation", escalation)
            # Sources are replaced before the citation map that refers to them.
            yield {"type": "evidence_update", "blocks": gathered}
            for event in _labelled(fallback, escalation):
                yield event
            return
    if capture is not None:
        capture.stage("escalation", escalation)
    for event in _labelled(held, escalation):
        yield event
