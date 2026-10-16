"""Deterministic support units for model-visible evidence.

Support units are projections of already authorized evidence blocks. They do
not retrieve, summarize, translate, or add text. The model receives local IDs;
the application retains the complete provenance mapping and resolves the
canonical citation text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.retrieval.hybrid_search import SearchResult


@dataclass(frozen=True)
class SupportUnit:
    support_unit_id: str
    parent_evidence_block_id: str
    evidence_id: str
    source_id: str | None
    document_version: str | None
    section_id: str | None
    contributing_chunk_ids: tuple[str, ...]
    tenant_id: str | None
    authorized: bool
    model_visible: bool
    text: str
    # Human-readable section shown to the model ("Kurulum > Adım 1", "page 3").
    section_label: str | None = None
    # The pages the unit's own chunk covers (a merged block spans several).
    page_number: int | None = None
    page_end: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "support_unit_id": self.support_unit_id,
            "parent_evidence_block_id": self.parent_evidence_block_id,
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "document_version": self.document_version,
            "section_id": self.section_id,
            "contributing_chunk_ids": list(self.contributing_chunk_ids),
            "tenant_id": self.tenant_id,
            "authorized": self.authorized,
            "model_visible": self.model_visible,
            "text": self.text,
            "section_label": self.section_label,
            "page_number": self.page_number,
            "page_end": self.page_end,
        }


def _units_for_text(text: str) -> list[str]:
    """Keep policy qualifiers together while separating authored paragraphs."""
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def section_label(payload: dict[str, Any]) -> str | None:
    heading_path = payload.get("heading_path") or []
    if heading_path:
        return " > ".join(str(heading) for heading in heading_path)
    section_path = payload.get("section_path") or []
    if section_path and payload.get("page_number") is not None:
        first, last = payload["page_number"], payload.get("page_end") or payload["page_number"]
        pages = f"page {first}" if last == first else f"pages {first}–{last}"
        return " > ".join(str(heading) for heading in section_path) + f" ({pages})"
    if payload.get("page_number") is not None:
        return f"page {payload['page_number']}"
    return None


def _pages(payload: dict[str, Any]) -> tuple[int | None, int | None]:
    first = payload.get("page_number")
    if first is None:
        return None, None
    return int(first), int(payload.get("page_end") or first)


def _sections(
    payload: dict[str, Any], block_id: str | None
) -> list[tuple[str, Any, str | None, tuple[str, ...], tuple[int | None, int | None]]]:
    """(text, section id, label, chunk ids, pages) per chunk of the block, in order.

    A section-aware block records its chunks in ``section_chunks``; they are
    used only while they still reproduce the block text exactly (a truncated
    block does not), so unit IDs and texts are the same either way.
    """
    text = str(payload.get("text", ""))
    chunks = payload.get("section_chunks") or []
    if chunks and "\n\n".join(str(chunk["text"]) for chunk in chunks) == text:
        return [
            (
                str(chunk["text"]),
                chunk["section_key"],
                section_label(chunk),
                (str(chunk["chunk_id"]),),
                _pages(chunk),
            )
            for chunk in chunks
        ]
    contributing = tuple(str(value) for value in payload.get("contributing_chunk_ids", []))
    if not contributing and block_id:
        contributing = (block_id,)
    section = payload.get("section_key") or payload.get("heading_path") or None
    return [(text, section, section_label(payload), contributing, _pages(payload))]


def build_support_units(blocks: list[SearchResult]) -> list[SupportUnit]:
    units: list[SupportUnit] = []
    for block_index, block in enumerate(blocks, 1):
        payload = block.payload
        evidence_id = str(payload.get("evidence_id", f"E{block_index}"))
        parent_id = str(payload.get("evidence_block_id", block.id or evidence_id))
        unit_texts = [
            (text, section, label, contributing, pages)
            for chunk_text, section, label, contributing, pages in _sections(
                payload, str(block.id) if block.id else None
            )
            for text in _units_for_text(chunk_text)
        ]
        for unit_index, (text, section, label, contributing, pages) in enumerate(unit_texts, 1):
            units.append(
                SupportUnit(
                    support_unit_id=f"{evidence_id}.S{unit_index}",
                    parent_evidence_block_id=parent_id,
                    evidence_id=evidence_id,
                    source_id=(
                        str(payload["source_id"]) if payload.get("source_id") is not None else None
                    ),
                    document_version=(
                        str(payload["document_version"])
                        if payload.get("document_version") is not None
                        else None
                    ),
                    section_id=str(section) if section is not None else None,
                    contributing_chunk_ids=contributing,
                    tenant_id=(
                        str(payload["tenant_id"]) if payload.get("tenant_id") is not None else None
                    ),
                    authorized=bool(payload.get("authorized", True)),
                    model_visible=bool(payload.get("model_visible", True)),
                    text=text,
                    section_label=label,
                    page_number=pages[0],
                    page_end=pages[1],
                )
            )
    return units


def serialize_support_units(units: list[SupportUnit]) -> str:
    """Units in order; consecutive units of one source and section share a
    single source/section header, so the prompt is mostly evidence text."""
    parts: list[str] = []
    header: tuple[str, str] | None = None
    for unit in units:
        current = (unit.source_id or "unknown", unit.section_label or "unknown")
        if current != header:
            header = current
            parts.append("[SOURCE]\nsource_id: {}\nsection: {}".format(*current))
        parts.append(f"[SUPPORT UNIT {unit.support_unit_id}]\ncontent:\n{unit.text}")
    return "\n\n".join(parts)


def support_unit_map(units: list[SupportUnit]) -> dict[str, SupportUnit]:
    return {unit.support_unit_id: unit for unit in units}


def resolve_support_ids(units: list[SupportUnit], support_ids: list[str]) -> list[SupportUnit]:
    """Resolve IDs to exact application-owned units in request scope."""
    available = support_unit_map(units)
    resolved = [available.get(support_id) for support_id in support_ids]
    if any(unit is None for unit in resolved):
        raise ValueError("support ID is not present in the current request")
    return [unit for unit in resolved if unit is not None]
