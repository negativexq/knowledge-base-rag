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
        }


def _units_for_text(text: str) -> list[str]:
    """Keep policy qualifiers together while separating authored paragraphs."""
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def build_support_units(blocks: list[SearchResult]) -> list[SupportUnit]:
    units: list[SupportUnit] = []
    for block_index, block in enumerate(blocks, 1):
        payload = block.payload
        evidence_id = str(payload.get("evidence_id", f"E{block_index}"))
        parent_id = str(payload.get("evidence_block_id", block.id or evidence_id))
        section = payload.get("section_key") or payload.get("heading_path") or None
        contributing = tuple(str(value) for value in payload.get("contributing_chunk_ids", []))
        if not contributing and block.id:
            contributing = (str(block.id),)
        for unit_index, text in enumerate(_units_for_text(str(payload.get("text", ""))), 1):
            units.append(
                SupportUnit(
                    support_unit_id=f"{evidence_id}.S{unit_index}",
                    parent_evidence_block_id=parent_id,
                    evidence_id=evidence_id,
                    source_id=(
                        str(payload["source_id"])
                        if payload.get("source_id") is not None
                        else None
                    ),
                    document_version=(
                        str(payload["document_version"])
                        if payload.get("document_version") is not None
                        else None
                    ),
                    section_id=str(section) if section is not None else None,
                    contributing_chunk_ids=contributing,
                    tenant_id=(
                        str(payload["tenant_id"])
                        if payload.get("tenant_id") is not None
                        else None
                    ),
                    authorized=bool(payload.get("authorized", True)),
                    model_visible=bool(payload.get("model_visible", True)),
                    text=text,
                )
            )
    return units


def serialize_support_units(units: list[SupportUnit]) -> str:
    return "\n\n".join(
        "[SUPPORT UNIT {id}]\nsource_id: {source}\nsection: {section}\ncontent:\n{text}".format(
            id=unit.support_unit_id,
            source=unit.source_id or "unknown",
            section=unit.section_id or "unknown",
            text=unit.text,
        )
        for unit in units
    )


def support_unit_map(units: list[SupportUnit]) -> dict[str, SupportUnit]:
    return {unit.support_unit_id: unit for unit in units}


def resolve_support_ids(units: list[SupportUnit], support_ids: list[str]) -> list[SupportUnit]:
    """Resolve IDs to exact application-owned units in request scope."""
    available = support_unit_map(units)
    resolved = [available.get(support_id) for support_id in support_ids]
    if any(unit is None for unit in resolved):
        raise ValueError("support ID is not present in the current request")
    return [unit for unit in resolved if unit is not None]
