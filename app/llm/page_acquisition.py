"""Version-bound page context and resumable reads; no search, extraction or answers."""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING

from app.evidence.documents import DocumentRead, DocumentRef, DocumentResult
from app.evidence.support_units import SupportUnit
from app.llm.agent_observability import operation
from app.llm.quantity_state import QuantitySource
from app.llm.research_state import (
    AcquiredPageChunk,
    PageContextReceipt,
    PageReadCheckpoint,
    signature,
)
from app.retrieval.filters import filter_authorized_candidates
from app.retrieval.hybrid_search import SearchResult

if TYPE_CHECKING:
    from app.llm.adaptive import AdaptiveSession


def authorized_page_blocks(
    session: AdaptiveSession, blocks: list[SearchResult], unit: SupportUnit, page: int
) -> list[SearchResult]:
    if session.deps.ledger.context is not None:
        blocks = filter_authorized_candidates(blocks, session.deps.ledger.context)
    return [
        b
        for b in blocks
        if b.payload.get("source_type") == "filesystem"
        and (b.payload.get("source_id"), b.payload.get("document_version"))
        == (unit.source_id, unit.document_version)
        and (b.payload.get("page_number") or 1)
        <= page
        <= (b.payload.get("page_end") or b.payload.get("page_number") or 1)
        and b.payload.get("authorized", True) is True
        and b.payload.get("model_visible", True) is True
        and (
            session.deps.ledger.context is None
            or session.deps.ledger.context.is_system
            or b.payload.get("tenant_id") == session.deps.ledger.context.tenant_id
        )
    ]


async def read_complete_page(
    session: AdaptiveSession, support_id: str, page: int
) -> DocumentResult:
    """Follow only reader-issued forward cursors, within the existing shared tool cap."""
    session.require([support_id])
    unit = session.units()[support_id]
    if not unit.source_id or not unit.document_version or session.deps.documents is None:
        raise ValueError("PAGE_READ_SOURCE_UNAVAILABLE")
    key = signature(
        "page_read", dict(source=unit.source_id, version=unit.document_version, page=page), 0
    )
    saved = session.state.page_read_checkpoints.get(key)
    checkpoint = saved or PageReadCheckpoint(
        source_id=unit.source_id, document_version=unit.document_version, page=page
    )
    # Reauthorize cached chunks too: a persisted checkpoint is not an ACL receipt.
    chunks = {
        b.id: b
        for b in checkpoint.chunks
        if authorized_page_blocks(
            session, [SearchResult(id=b.id, score=0, payload=b.payload)], unit, page
        )
    }
    if len(chunks) != len(checkpoint.chunks):
        checkpoint = PageReadCheckpoint(
            source_id=unit.source_id, document_version=unit.document_version, page=page
        )
        chunks = {}
    offsets = list(checkpoint.offsets)
    offset = checkpoint.next_offset if checkpoint.next_offset is not None else 0
    more, limited = checkpoint.has_more, checkpoint.scan_limited
    reason = checkpoint.stop_reason
    cap = min(
        session.limits.tool_calls_limit or session.policy.max_tool_attempts,
        session.policy.max_tool_attempts,
    )
    with operation("quantity.source.paginate") as span:
        while more:
            remaining = session.research_deadline - time.monotonic()
            if session.deps.observations.tool_calls >= cap or remaining <= 0:
                reason = "tool_budget" if remaining > 0 else "deadline"
                break
            if offset in offsets:
                reason = "cursor_stalled"
                break
            session.deps.observations.tool_calls += 1
            async with asyncio.timeout(min(session.policy.tool_timeout_seconds, remaining)):
                result = await session.deps.documents.read(
                    DocumentRead(
                        document=DocumentRef(
                            source_type="filesystem",
                            source_id=unit.source_id,
                            document_version=unit.document_version,
                        ),
                        action="page",
                        page=page,
                        offset=offset,
                    )
                )
            offsets.append(offset)
            fresh = authorized_page_blocks(session, result.blocks, unit, page)
            new = [b for b in fresh if str(b.id) not in chunks]
            if len(chunks) + len(new) > 300:
                reason, more = "chunk_capacity", True
                break
            chunks.update(
                {str(b.id): AcquiredPageChunk(id=str(b.id), payload=dict(b.payload)) for b in new}
            )
            more, limited = result.has_more, limited or result.scan_limited
            next_offset = result.next_offset
            if not more:
                reason, offset = "reader_exhausted", offset
            elif not new or next_offset is None or not offset < next_offset <= 2000:
                reason = "cursor_stalled"
            else:
                offset, reason = next_offset, "continuation"
            checkpoint = checkpoint.model_copy(
                update=dict(
                    chunks=list(chunks.values()),
                    offsets=offsets,
                    next_offset=offset if more else None,
                    has_more=more,
                    scan_limited=limited,
                    stop_reason=reason,
                )
            )
            session.state.page_read_checkpoints[key] = checkpoint
            if reason != "continuation":
                break
        checkpoint = checkpoint.model_copy(
            update=dict(
                chunks=list(chunks.values()),
                offsets=offsets,
                next_offset=offset if more else None,
                has_more=more,
                scan_limited=limited,
                stop_reason=reason,
            )
        )
        session.state.page_read_checkpoints[key] = checkpoint
        span.set_attribute("evidence.physical_page", page)
        span.set_attribute("source.read_offsets", offsets)
        span.set_attribute("source.next_offset", offset if more else -1)
        span.set_attribute("source.has_more", more)
        span.set_attribute("source.scan_limited", limited)
        span.set_attribute("source.stop_reason", reason)
        span.set_attribute("source.retained_chunks", len(chunks))
    return DocumentResult(
        [SearchResult(id=b.id, score=0, payload=b.payload) for b in chunks.values()],
        [],
        more,
        limited,
        offset if more else None,
    )


async def attach_original_context(
    session: AdaptiveSession, selection: QuantitySource
) -> QuantitySource:
    """Attach literal text from exactly the selected original pages, never inferred headers."""
    if (
        selection.modality != "text"
        or selection.operation_kind in {"count", "list"}
        or not selection.pages
        or not getattr(session.deps.render_page, "snapshot", None)
    ):
        return selection
    session.require([*selection.support_ids, *selection.context_support_ids])
    unit = session.units()[selection.support_ids[0]]
    if not unit.source_id or not unit.document_version:
        return selection
    structure, parent = await session.deps.pdf_structure(selection.support_ids[0])
    native = await asyncio.to_thread(structure.inventory_context, selection.pages)
    ids = list(selection.context_support_ids)
    with operation("quantity.source.context") as span:
        for page in native["pages"]:
            text = "\n".join(line["text"] for line in page["lines"])
            if not text or len(ids) >= 3:
                continue
            # One reading unit per page; every source line/word survives.
            text = re.sub(r"\n\s*\n", "\n", text)
            block_id = "page-context-" + signature(
                "native_context",
                dict(
                    source=unit.source_id,
                    version=unit.document_version,
                    page=page["page"],
                    text=text,
                ),
                0,
            )
            existing = [
                k for k, u in session.units().items() if u.parent_evidence_block_id == block_id
            ]
            if not existing:
                session.admit(
                    [
                        SearchResult(
                            id=block_id,
                            score=0,
                            payload={
                                **parent.payload,
                                "text": text,
                                "section_chunks": [],
                                "evidence_block_id": block_id,
                                "contributing_chunk_ids": [block_id],
                                "page_number": page["page"],
                                "page_end": page["page"],
                                "heading_path": [],
                                "section_path": ["Original PDF page context"],
                                "reading_method": "native_pdf_text",
                            "source_caption_context": "",
                                "parent_support_ids": selection.support_ids,
                            },
                        )
                    ]
                )
                existing = [
                    k for k, u in session.units().items() if u.parent_evidence_block_id == block_id
                ]
            ids.extend(k for k in existing if k not in ids)
            receipt = PageContextReceipt(
                source_id=unit.source_id,
                document_version=unit.document_version,
                page=page["page"],
                support_ids=existing,
                limited=page["limited"],
                line_count=len(page["lines"]),
            )
            session.state.page_contexts.append(receipt)
        span.set_attribute("evidence.context_support_ids", ids)
        span.set_attribute("evidence.physical_pages", selection.pages)
    return selection.model_copy(update={"context_support_ids": ids})
