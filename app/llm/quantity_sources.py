"""Application-owned inspection of bounded, authorized original PDF pages."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from app.llm.agent_observability import operation
from app.llm.quantity_state import (
    QuantityCatalogPage,
    QuantityPageQuality,
    QuantitySourceInspection,
)

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


async def source_catalog(session: AdaptiveSession, ranked: list[str]) -> list[QuantityCatalogPage]:
    """Inspect only pages already covered by admitted, visible PDF source ranges."""
    if not getattr(session.deps.render_page, "snapshot", None):
        return []
    units = session.units()
    pdf_evidence = {
        b.payload["evidence_id"]
        for b in session.deps.ledger.blocks
        if b.payload.get("source_type") == "filesystem"
    }
    groups: dict[tuple[str, str], dict[int, list[str]]] = {}
    total = 0
    for key in ranked:
        u = units[key]
        if (
            not u.authorized
            or not u.model_visible
            or not u.source_id
            or not u.document_version
            or not u.page_number
            or u.evidence_id not in pdf_evidence
        ):
            continue
        identity = (u.source_id, u.document_version)
        if identity not in groups and len(groups) >= 3:
            continue
        pages = groups.setdefault(identity, {})
        for number in range(u.page_number, min(u.page_end or u.page_number, 2000) + 1):
            if number not in pages:
                if total >= 36:
                    continue
                pages[number] = []
                total += 1
            if key not in pages[number] and len(pages[number]) < 3:
                pages[number].append(key)
    result: list[QuantityCatalogPage] = []
    for (source, version), pages in groups.items():
        if not pages:
            continue
        seed = next(iter(pages.values()))[0]
        session.require([seed])
        with operation("quantity.source.catalog") as span:
            async with asyncio.timeout(
                min(
                    session.policy.tool_timeout_seconds,
                    max(0, session.research_deadline - time.monotonic()),
                )
            ):
                structure, _ = await session.deps.pdf_structure(seed)
                hints = await asyncio.to_thread(structure.page_catalog, list(pages))
            result.extend(
                QuantityCatalogPage(
                    **hint,
                    source_id=source,
                    document_version=version,
                    support_ids=pages[hint["physical_page"]],
                )
                for hint in hints
            )
            span.set_attribute("evidence.source_id", source)
            span.set_attribute("evidence.physical_pages", list(pages))
            span.set_attribute(
                "evidence.catalog_support_ids",
                list(dict.fromkeys(key for keys in pages.values() for key in keys)),
            )
    history = {
        (p.source_id, p.document_version, p.physical_page): p
        for p in [*session.state.quantity_page_catalog, *result]
    }
    session.state.quantity_page_catalog = list(history.values())[-72:]
    return result
