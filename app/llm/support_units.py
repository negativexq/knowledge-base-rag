"""Deterministic support units for Pipeline v2.3.

Support units are projections of already authorized evidence blocks.  They do
not retrieve, summarize, translate, or add text.  The model receives local
IDs; application code retains the complete provenance mapping.
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
    section_id: str | None
    contributing_chunk_ids: tuple[str, ...]
    tenant_id: str | None
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "support_unit_id": self.support_unit_id,
            "parent_evidence_block_id": self.parent_evidence_block_id,
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "section_id": self.section_id,
            "contributing_chunk_ids": list(self.contributing_chunk_ids),
            "tenant_id": self.tenant_id,
            "text": self.text,
        }


def _units_for_text(text: str) -> list[str]:
    """Split authored text at paragraph/list/table boundaries only.

    Sentence splitting is intentionally avoided: a paragraph is usually the
    smallest authored unit that keeps policy qualifiers with its value.
    """
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def build_support_units(blocks: list[SearchResult]) -> list[SupportUnit]:
    units: list[SupportUnit] = []
    for block_index, block in enumerate(blocks, 1):
        payload = block.payload
        evidence_id = str(payload.get("evidence_id", f"E{block_index}"))
        parent_id = str(payload.get("evidence_block_id", block.id or evidence_id))
        section = payload.get("section_key") or payload.get("heading_path") or None
        section_id = str(section) if section is not None else None
        contributing = tuple(str(value) for value in payload.get("contributing_chunk_ids", []))
        if not contributing and block.id:
            contributing = (str(block.id),)
        for unit_index, text in enumerate(_units_for_text(str(payload.get("text", ""))), 1):
            units.append(
                SupportUnit(
                    support_unit_id=f"{evidence_id}.U{unit_index}",
                    parent_evidence_block_id=parent_id,
                    evidence_id=evidence_id,
                    source_id=(
                        str(payload["source_id"]) if payload.get("source_id") is not None else None
                    ),
                    section_id=section_id,
                    contributing_chunk_ids=contributing,
                    tenant_id=(
                        str(payload["tenant_id"]) if payload.get("tenant_id") is not None else None
                    ),
                    text=text,
                )
            )
    return units


def serialize_support_units(units: list[SupportUnit]) -> str:
    records = []
    for unit in units:
        records.append(
            "[SUPPORT UNIT {id}]\nsource_id: {source}\nsection: {section}\ncontent:\n{text}".format(
                id=unit.support_unit_id,
                source=unit.source_id or "unknown",
                section=unit.section_id or "unknown",
                text=unit.text,
            )
        )
    return "\n\n".join(records)


def support_unit_map(units: list[SupportUnit]) -> dict[str, SupportUnit]:
    return {unit.support_unit_id: unit for unit in units}
