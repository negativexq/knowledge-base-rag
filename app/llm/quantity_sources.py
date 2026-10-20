"""Application-owned inspection of bounded, authorized original PDF pages."""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING

from app.evidence.documents import DocumentRead, DocumentRef
from app.evidence.support_units import SupportUnit
from app.llm.agent_observability import operation
from app.llm.quantity_state import (
    QuantityCatalogPage,
    QuantityGapSearch,
    QuantityPageQuality,
    QuantityRecord,
    QuantitySource,
    QuantitySourceInspection,
)
from app.llm.research_state import SearchEvidence
from app.llm.search_context import targeted_chunks

if TYPE_CHECKING:
    from app.llm.adaptive import AdaptiveSession


def visual_page_supports(
    selection: QuantitySource,
    inputs: list[SupportUnit],
    context: list[SupportUnit],
) -> list[str]:
    """Authorize explicitly requested images without discarding a context-role page."""
    requested = set(selection.pages)
    if not requested or len(requested) > 3 or len(requested) != len(selection.pages):
        raise ValueError("NUMERIC_SOURCE_REQUIRES_BOUNDED_PAGE_CHECK")
    identities = {(u.source_id, u.document_version) for u in inputs}
    if len(identities) != 1:
        raise ValueError("QUANTITY_SOURCE_VERSION_MISMATCH")

    def pages(unit: SupportUnit) -> set[int]:
        return set(range(unit.page_number or 1, (unit.page_end or unit.page_number or 1) + 1))

    covered = {p for unit in inputs for p in pages(unit)}
    missing = requested - covered
    authorities = list(inputs)
    for unit in context:
        if not missing.intersection(pages(unit)):
            continue
        if (unit.source_id, unit.document_version) not in identities:
            raise ValueError("QUANTITY_SOURCE_VERSION_MISMATCH")
        authorities.append(unit)
        covered.update(pages(unit))
    if not requested <= covered:
        raise ValueError("QUANTITY_PAGE_OUTSIDE_SOURCE")
    if any(not u.authorized or not u.model_visible for u in authorities):
        raise ValueError("QUANTITY_SOURCE_NOT_VISIBLE")
    return list(dict.fromkeys(u.support_unit_id for u in authorities))


def relationship_context(parent: QuantityRecord, units: dict[str, SupportUnit]) -> list[str]:
    """Locate bounded definition passages for contrasted labels, without asserting a join.

    Names come from grounded objections, never a document-specific alias dictionary.
    A passage may establish a distinction rather than equivalence; only independent
    source review can decide that. This local selection changes no retrieval scores.
    """
    if not parent.assessments:
        return []
    gaps = " ".join(
        i.needed_evidence
        for i in parent.assessments[-1].issues
        if i.evidence_kind == "entity_inventory"
        or (
            parent.draft.mode == "lookup"
            and i.kind in {"wrong_binding", "missing_item", "operation"}
        )
    )
    names = set(re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\b", gaps))
    names = {name for name in names if len(name) >= 3}
    if len(names) < 2:
        return []
    ranked = []
    for key, unit in units.items():
        if (
            not unit.authorized
            or not unit.model_visible
            or len(unit.text) > 6000
            or (unit.source_id, unit.document_version)
            != (parent.source_id, parent.document_version)
            or key in [*parent.proof_support_ids, *parent.support_ids, *parent.context_support_ids]
        ):
            continue
        matches = sum(
            bool(
                re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", unit.text, re.IGNORECASE)
            )
            for name in names
        )
        definitions = len(
            re.findall(
                r"\b(?:defined?|definition|refers?|called|denotes?|aliases|alias|subset)\b"
                r"|\bwe (?:use|call)\b",
                unit.text,
                re.IGNORECASE,
            )
        )
        if matches >= 2 and definitions:
            ranked.append((key, matches, definitions, len(unit.text)))
    ranked.sort(key=lambda entry: (-entry[1], -entry[2], entry[3]))
    return [entry[0] for entry in ranked[:3]]


async def complete_sources(
    session: AdaptiveSession, parent: QuantityRecord
) -> QuantityGapSearch | None:
    """Locate a grounded missing input in the same authorized document, without an LLM."""
    if session.deps.documents is None or not parent.assessments:
        return None
    gaps = [
        i.needed_evidence
        for i in parent.assessments[-1].issues
        if (i.kind in {"missing_item", "boundary"} or i.evidence_kind == "entity_inventory")
        and i.needed_evidence.strip()
    ]
    if not gaps:
        return None
    cap = min(
        session.limits.tool_calls_limit or session.policy.max_tool_attempts,
        session.policy.max_tool_attempts,
    )
    if session.deps.observations.tool_calls >= cap:
        return None
    session.require(parent.support_ids)
    unit = session.units()[parent.support_ids[0]]
    block = next(
        b for b in session.deps.ledger.blocks if b.payload["evidence_id"] == unit.evidence_id
    )
    if not unit.source_id or not unit.document_version:
        return None
    # Descriptions locate evidence, never supply source facts or page guesses.
    # Keep the actual task authoritative: a draft/reviewer can itself misbind a
    # population. Its missing-field description must not replace the question.
    query = (" ".join(dict.fromkeys(gaps))[:300] + " " + session.state.task.question)[:500]
    session.deps.observations.tool_calls += 1
    before = set(session.units())
    with operation("quantity.source.complete") as span:
        span.set_attribute("quantity.parent_id", parent.id)
        span.set_attribute("evidence.gap_query", query)
        async with asyncio.timeout(
            min(
                session.policy.tool_timeout_seconds,
                max(0, session.research_deadline - time.monotonic()),
            )
        ):
            found = await session.deps.documents.read(
                DocumentRead(
                    document=DocumentRef(
                        source_type=block.payload.get("source_type", "doc"),
                        source_id=unit.source_id,
                        document_version=unit.document_version,
                    ),
                    action="search",
                    query=query,
                    search_mode="ranked",
                    limit=3,
                )
            )
        chunks = targeted_chunks(found.blocks, query)
        session.admit(chunks, search_query=query)
        chunk_ids = {str(c.id) for c in chunks}
        candidates = {
            key: u
            for key, u in session.units().items()
            if u.source_id == unit.source_id
            and u.document_version == unit.document_version
            and chunk_ids.intersection(u.contributing_chunk_ids)
        }
        ranked = session.ranked_ids(candidates, query_text=query, preserve_anchors=False)
        # Prefer the complete chunks returned by this search over their detached
        # pre-existing paragraphs. This retains captions, populations and values.
        chunk_texts = {str(c.payload.get("text", "")) for c in chunks}
        selected = sorted(ranked, key=lambda key: candidates[key].text not in chunk_texts)[:6]
        if selected:
            session.selected = tuple(selected)
        admitted = sorted(set(session.units()) - before)
        session.state.search_evidence.append(
            SearchEvidence(
                query=query,
                need_id=parent.need_id,
                admitted_support_ids=admitted,
                selected_support_ids=selected,
            )
        )
        span.set_attribute("evidence.admitted_support_ids", admitted)
        span.set_attribute("evidence.selected_ids", selected)
        span.set_attribute("evidence.search_has_more", found.has_more)
        span.set_attribute("evidence.search_scan_limited", found.scan_limited)
        receipt = QuantityGapSearch(
            parent_id=parent.id,
            requirements=parent.assessments[-1].issues,
            query=query,
            candidate_support_ids=selected,
            status="located" if selected else "unresolved",
        )
        session.state.quantity_gap_searches[parent.id] = receipt
        return receipt


def fresh_source_view(
    session: AdaptiveSession, parent: QuantityRecord, selection: QuantitySource
) -> bool:
    """Moving an old source ID between input/context roles is not new evidence."""
    units = session.units()
    old_ids = [*parent.support_ids, *parent.context_support_ids]
    selected_ids = [*selection.support_ids, *selection.context_support_ids]
    session.require([*old_ids, *selected_ids])
    old_text = {
        (units[key].source_id, units[key].document_version, units[key].text) for key in old_ids
    }
    # In image mode, a different paragraph ID on an already inspected full page
    # does not create a fresh visual observation. A genuinely new context passage
    # outside those pages still can establish a missing relationship.
    if parent.modality == selection.modality == "image":
        if set(selection.pages) - set(parent.pages):
            return True
        return any(
            (units[key].source_id, units[key].document_version, units[key].text) not in old_text
            and not set(
                range(
                    units[key].page_number or 1,
                    (units[key].page_end or units[key].page_number or 1) + 1,
                )
            )
            <= set(parent.pages)
            for key in selection.context_support_ids
        )
    if selection.modality != parent.modality:
        return True
    return any(
        (units[key].source_id, units[key].document_version, units[key].text) not in old_text
        for key in selected_ids
    )


def bind_gap_source(
    session: AdaptiveSession,
    parent: QuantityRecord,
    selection: QuantitySource,
    gap: QuantityGapSearch,
) -> QuantitySource:
    """Carry one bounded fresh search candidate into inspection, without asserting its truth."""
    units = session.units()
    for key in gap.candidate_support_ids:
        session.require([key])
        unit = units[key]
        if (unit.source_id, unit.document_version) != (parent.source_id, parent.document_version):
            continue
        pages = list(range(unit.page_number or 1, (unit.page_end or unit.page_number or 1) + 1))
        if selection.modality == "image" and len(pages) > 3:
            continue  # A broad candidate requires explicit bounded page selection.
        ids = [key, *[s for s in selection.support_ids if s != key]]
        if selection.modality == "image":
            # Full-page images cover same-page paragraph aliases; replace those
            # redundant seeds rather than overflowing the three-source window.
            ids = [
                key,
                *[
                    s
                    for s in ids[1:]
                    if not set(
                        range(
                            units[s].page_number or 1,
                            (units[s].page_end or units[s].page_number or 1) + 1,
                        )
                    )
                    <= set(pages)
                ],
            ]
        chosen_pages = sorted(set([*selection.pages, *pages]))
        if len(ids) > 3 or len(chosen_pages) > 3:
            continue
        proposed = selection.model_copy(
            update={
                "support_ids": ids,
                "pages": chosen_pages,
                "available": True,
            }
        )
        if not fresh_source_view(session, parent, proposed):
            continue
        with operation("quantity.gap.bind") as span:
            span.set_attribute("quantity.parent_id", parent.id)
            span.set_attribute("evidence.gap_candidate_id", key)
            span.set_attribute("evidence.input_support_ids", ids)
            span.set_attribute("evidence.physical_pages", chosen_pages)
        return proposed
    return selection


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
