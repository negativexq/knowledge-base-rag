"""Fact-level evidence metrics for offline evaluation.

The authored invariant is source + supporting span. Chunk IDs are derived for
the representation being measured and must never stand in for fact evidence.
This module performs no retrieval, model, or provider work.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def normalize_evidence(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold().replace("\u00a0", " ")
    return re.sub(r"\s+", " ", folded).strip()


@dataclass(frozen=True)
class FactEvidenceResult:
    required_sources_present: list[str]
    missing_sources: list[str]
    present_fact_ids: list[str]
    missing_fact_ids: list[str]
    source_recall_complete: bool
    fact_evidence_recall: float
    all_required_fact_evidence_present: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "required_sources_present": self.required_sources_present,
            "missing_sources": self.missing_sources,
            "present_fact_ids": self.present_fact_ids,
            "missing_fact_ids": self.missing_fact_ids,
            "source_recall_complete": self.source_recall_complete,
            "fact_evidence_recall": self.fact_evidence_recall,
            "all_required_fact_evidence_present": self.all_required_fact_evidence_present,
        }


def evaluate_fact_evidence(
    required_facts: Iterable[dict[str, Any]],
    evidence_blocks: Iterable[dict[str, Any]],
) -> FactEvidenceResult:
    """Measure source presence and authored-span presence independently."""
    facts = list(required_facts)
    blocks = list(evidence_blocks)
    required_sources = sorted({str(fact["authoritative_source_id"]) for fact in facts})
    available_sources = {str(block["source_id"]) for block in blocks}
    present_sources = [source for source in required_sources if source in available_sources]
    missing_sources = [source for source in required_sources if source not in available_sources]

    present_facts: list[str] = []
    missing_facts: list[str] = []
    for fact in facts:
        source_id = str(fact["authoritative_source_id"])
        span = normalize_evidence(str(fact["supporting_text_span"]))
        supported = any(
            str(block["source_id"]) == source_id
            and span in normalize_evidence(str(block["text"]))
            for block in blocks
        )
        target = present_facts if supported else missing_facts
        target.append(str(fact["required_fact_id"]))

    recall = len(present_facts) / len(facts) if facts else 0.0
    return FactEvidenceResult(
        required_sources_present=present_sources,
        missing_sources=missing_sources,
        present_fact_ids=present_facts,
        missing_fact_ids=missing_facts,
        source_recall_complete=not missing_sources,
        fact_evidence_recall=recall,
        all_required_fact_evidence_present=bool(facts) and not missing_facts,
    )
