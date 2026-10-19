"""Application-owned inspection of bounded, authorized original PDF pages."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from app.llm.agent_observability import operation
from app.llm.quantity_state import QuantityPageQuality, QuantitySourceInspection

if TYPE_CHECKING:
    from app.llm.adaptive import AdaptiveSession


async def inspect_pages(
    session: AdaptiveSession, support_ids: list[str], pages: list[int]
) -> list[QuantityPageQuality]:
    session.require(support_ids)
    units = [session.units()[key] for key in support_ids]
    if not getattr(session.deps.render_page, "snapshot", None):
        return []  # Non-PDF/text connectors keep their normal evidence path.
    pdf_units = [
        u
        for u in units
        if u.source_id
        and u.document_version
        and any(
            b.payload["evidence_id"] == u.evidence_id
            and b.payload.get("source_type") == "filesystem"
            for b in session.deps.ledger.blocks
        )
    ]
    if not pdf_units:
        return []
    if len({(u.source_id, u.document_version) for u in pdf_units}) != 1:
        raise ValueError("QUANTITY_SOURCE_VERSION_MISMATCH")
    allowed = {
        p
        for u in pdf_units
        for p in range(u.page_number or 1, (u.page_end or u.page_number or 1) + 1)
    }
    requested = sorted(set(pages)) if pages else sorted(allowed)
    if not requested or len(requested) > 3:
        raise ValueError("NUMERIC_SOURCE_REQUIRES_BOUNDED_PAGE_CHECK")
    if not set(requested) <= allowed:
        raise ValueError("QUANTITY_PAGE_OUTSIDE_SOURCE")
    unit = pdf_units[0]
    # Immutable snapshot identity and page set define a reusable application receipt.
    for receipt in session.state.quantity_source_inspections:
        if (
            receipt.source_id == unit.source_id
            and receipt.document_version == unit.document_version
            and set(requested) <= {p.page for p in receipt.pages}
        ):
            return [p for p in receipt.pages if p.page in requested]
    with operation("quantity.source.inspect") as span:
        async with asyncio.timeout(
            min(
                session.policy.tool_timeout_seconds,
                max(0, session.deadline - time.monotonic()),
            )
        ):
            structure, _ = await session.deps.pdf_structure(unit.support_unit_id)
            quality = [
                QuantityPageQuality.model_validate(
                    await asyncio.to_thread(structure.page_quality, p)
                )
                for p in requested
            ]
        assert unit.source_id is not None and unit.document_version is not None
        session.state.quantity_source_inspections.append(
            QuantitySourceInspection(
                support_ids=support_ids,
                source_id=unit.source_id,
                document_version=unit.document_version,
                pages=quality,
            )
        )
        span.set_attribute("evidence.input_support_ids", support_ids)
        span.set_attribute("evidence.physical_pages", requested)
        span.set_attribute("source.native_text_chars", [p.native_text_chars for p in quality])
        span.set_attribute("source.requires_image", any(p.requires_image for p in quality))
        return quality
