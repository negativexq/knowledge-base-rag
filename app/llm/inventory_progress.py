"""Application-owned accumulation of checked occurrences across count windows.

Window input accuracy and whole-object completeness are independent. This module
never turns a partial inventory into a publishable total or a source absence claim.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal

from app.evidence.support_units import SupportUnit
from app.llm.agent_observability import operation
from app.llm.quantity_state import (
    InventoryItemRef,
    InventoryProgress,
    InventoryWindow,
    QuantityItem,
    QuantityRecord,
)

if TYPE_CHECKING:
    from app.llm.research_state import ResearchState


def key(parts: list[Any]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def input_status(record: QuantityRecord) -> Literal["pending", "supported", "rejected"]:
    if not record.assessments:
        return "pending"
    review = record.assessments[-1]
    if (
        record.diagnostic_errors
        or record.inventory_errors
        or record.scope_diagnostic
        or review.inputs != "supported"
        or any(i.kind in {"wrong_binding", "unreadable"} for i in review.issues)
    ):
        return "rejected"
    return "supported"


def occurrence(record: QuantityRecord, item: QuantityItem) -> str | None:
    if item.source_ranges:
        locator: Any = [r.model_dump() for r in item.source_ranges]
    elif item.page is not None and item.source_object and any(
        b.physical_page == item.page
        and b.source_id == record.source_id
        and b.document_version == record.document_version
        and b.image_id in item.image_ids
        for b in record.image_bindings
    ):
        locator = [item.page, normalized(item.source_object), item.position]
    else:
        return None
    return key([record.source_id, record.document_version, locator])


def checkpoint_inventory(state: ResearchState, record: QuantityRecord) -> InventoryProgress | None:
    if record.draft.mode != "count" or not record.document_version:
        return None
    inventory_id = key([record.need_id, record.source_id, record.document_version])
    windows = []
    refs: dict[str, InventoryItemRef] = {}
    readings: dict[str, str] = {}
    conflicts = set()
    for current in state.quantities.values():
        if current.draft.mode != "count" or (
            current.need_id, current.source_id, current.document_version
        ) != (record.need_id, record.source_id, record.document_version):
            continue
        status = input_status(current)
        windows.append(InventoryWindow(
            quantity_id=current.id, pages=current.pages,
            input_status=status,
            coverage=current.assessments[-1].coverage if current.assessments else "unknown",
        ))
        if status != "supported":
            continue
        for gi, group in enumerate(current.draft.groups):
            for ii, item in enumerate(group.items):
                identity = occurrence(current, item)
                if identity is None:
                    continue
                reading = normalized(item.text)
                if identity in readings and readings[identity] != reading:
                    conflicts.add(identity)
                readings[identity] = reading
                refs.setdefault(identity, InventoryItemRef(
                    occurrence_id=identity, quantity_id=current.id, group_index=gi, item_index=ii,
                ))
    progress = InventoryProgress(
        id=inventory_id, need_id=record.need_id, source_id=record.source_id,
        document_version=record.document_version, windows=windows,
        items=[ref for identity, ref in refs.items() if identity not in conflicts],
        conflicts=sorted(conflicts),
    )
    state.inventories[inventory_id] = progress
    with operation("quantity.inventory.progress") as span:
        span.set_attribute("inventory.id", progress.id)
        span.set_attribute("quantity.id", record.id)
        span.set_attribute("inventory.checked_occurrences", len(progress.items))
        span.set_attribute("inventory.conflicts", len(progress.conflicts))
        span.set_attribute("inventory.pending_windows", sum(
            window.input_status == "pending" for window in progress.windows
        ))
        span.set_attribute("inventory.global_complete", False)
        span.set_attribute("evidence.physical_pages", sorted({
            page for window in progress.windows for page in window.pages
        }))
    return progress


def inventory_view(state: ResearchState, units: dict[str, SupportUnit]) -> list[dict[str, Any]]:
    """Resolve typed references afresh; no stale/hidden source becomes a model fact."""
    views = []
    for progress in state.inventories.values():
        def visible(record: QuantityRecord) -> bool:
            return bool(record.support_ids) and (
                record.need_id, record.source_id, record.document_version
            ) == (progress.need_id, progress.source_id, progress.document_version) and all(
                k in units and units[k].authorized and units[k].model_visible
                and (units[k].source_id, units[k].document_version)
                == (progress.source_id, progress.document_version)
                for k in record.support_ids
            )

        windows = [w for w in progress.windows if (
            w.quantity_id in state.quantities and visible(state.quantities[w.quantity_id])
        )]
        if not windows:
            continue
        items = []
        for ref in progress.items:
            record = state.quantities.get(ref.quantity_id)
            if record is None or not visible(record) or input_status(record) != "supported":
                continue
            if not 0 <= ref.group_index < len(record.draft.groups):
                continue
            group = record.draft.groups[ref.group_index]
            if not 0 <= ref.item_index < len(group.items):
                continue
            item = group.items[ref.item_index]
            if occurrence(record, item) != ref.occurrence_id:
                continue
            items.append(dict(
                quantity_id=record.id, occurrence_id=ref.occurrence_id,
                group=group.label, text=item.text, page=item.page,
                source_object=item.source_object, position=item.position,
                support_ids=record.support_ids,
            ))
        views.append(dict(
            inventory_id=progress.id, need_id=progress.need_id,
            source_id=progress.source_id, document_version=progress.document_version,
            complete=False, conflicts=len(progress.conflicts),
            windows=[w.model_dump() for w in windows],
            checked_occurrences=items[:40], omitted_occurrences=max(0, len(items)-40),
            # A page list here describes checked findings, not all document pages.
            observed_positive_pages=sorted({i["page"] for i in items if i["page"] is not None}),
        ))
    return views
