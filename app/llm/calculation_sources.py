"""Bound quality inspection to explicit page-read hints, only with native proof."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry

from app.llm.agent_observability import operation
from app.llm.calculation import Calculation, verify_calculation

if TYPE_CHECKING:
    from app.llm.adaptive import AdaptiveSession
    from app.llm.agentic import AgentAnswerPart


async def calculation_inspection_targets(
    session: AdaptiveSession,
    part: AgentAnswerPart,
    targets: list[tuple[list[str], list[int]]],
) -> list[tuple[list[str], list[int]]]:
    """Do not mistake overlapping parser chunks for pages actually needed.

    A requested page is a location hint, not provenance for every value in an
    overlapping chunk. Use it only if original native pages independently carry
    ALL calculation inputs. Semantic scope and page-quality review still follow.
    Without that proof, retain the original conservative inspection contract.
    """
    if not part.calculation or not getattr(session.deps.render_page, "snapshot", None):
        return targets
    narrowed = []
    changed = False
    by_source: dict[tuple[str, str], tuple[str, set[int]]] = {}
    units = session.units()
    for ids, explicit in targets:
        pages = set(explicit)
        for key in ids:
            unit = units[key]
            if not unit.source_id or not unit.document_version or not unit.page_number:
                return targets
            allowed = set(range(unit.page_number, (unit.page_end or unit.page_number) + 1))
            if not explicit and len(allowed) > 3:
                parent = next(
                    b
                    for b in session.deps.ledger.blocks
                    if b.payload["evidence_id"] == unit.evidence_id
                )
                hint = parent.payload.get("requested_page")
                if not isinstance(hint, int) or hint not in allowed:
                    return targets
                pages.add(hint)
                changed = True
            elif not explicit:
                pages.update(allowed)
            if not pages <= allowed or len(pages) > 3:
                return targets
            identity = (unit.source_id, unit.document_version)
            by_source.setdefault(identity, (key, set()))[1].update(pages)
        narrowed.append((ids, sorted(pages)))
    if not changed or any(len(pages) > 3 for _, pages in by_source.values()):
        return targets
    texts: list[str] = []
    try:
        for key, pages in by_source.values():
            session.require([key])
            structure, _ = await session.deps.pdf_structure(key)
            async with asyncio.timeout(
                min(
                    session.policy.tool_timeout_seconds,
                    max(0, session.deadline - time.monotonic()),
                )
            ):
                view = await asyncio.to_thread(structure.inventory_context, sorted(pages))
            if any(p["limited"] for p in view["pages"]):
                return targets
            texts.extend("\n".join(line["text"] for line in p["lines"]) for p in view["pages"])
    except (ValueError, RuntimeError, ModelRetry, TimeoutError):
        return targets
    if verify_calculation(
        Calculation(part.calculation.expression, part.calculation.result), texts, part.text
    ):
        return targets
    with operation("calculation.source.bind") as span:
        span.set_attribute("evidence.input_support_ids", [s for ids, _ in narrowed for s in ids])
        span.set_attribute(
            "evidence.physical_pages", sorted({p for _, pages in narrowed for p in pages})
        )
        span.set_attribute("calculation.native_inputs_verified", True)
    return narrowed
