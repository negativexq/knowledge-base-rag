"""Canonical immutable critical-value occurrences for experimental validation.

This module deliberately does not participate in the production validator
selector. It gives architecture experiments one identity-bearing extraction
result that can be passed to role classification and validation without
masking or re-extracting the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.evaluation.critical_values import _v6_tokenized

CriticalValueType = Literal[
    "NUMBER",
    "SIGNED_NUMBER",
    "DURATION",
    "PERCENTAGE",
    "VERSION",
    "DATE",
    "CURRENCY",
    "BOOLEAN",
    "IDENTIFIER",
]


@dataclass(frozen=True, slots=True)
class CriticalValueOccurrence:
    """One extractor-owned lexical occurrence in one source text."""

    occurrence_id: str
    span_start: int
    span_end: int
    raw_literal: str
    normalized_value: str
    lexical_type: str
    unit: str | None
    claim_unit_id: str | None
    extraction_source: str
    overlap_group_id: str | None = None
    parent_occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ValueError("occurrence span must be non-empty and non-negative")


def extract_critical_occurrences(
    text: str,
    *,
    claim_id: str = "claim",
) -> tuple[CriticalValueOccurrence, ...]:
    """Extract exactly one canonical, immutable occurrence ledger.

    `_v6_tokenized` is the frozen lexical-boundary implementation used as the
    starting contract here. The conversion gives its typed, non-overlapping
    spans an immutable identity; it does not change V6 or production behavior.
    """
    normalized = text or ""
    tokens = _v6_tokenized(normalized)
    occurrences: list[CriticalValueOccurrence] = []
    for index, token in enumerate(tokens, start=1):
        start = int(token["start"])
        end = int(token["end"])
        raw = str(token.get("raw_literal") or normalized[start:end])
        lexical_type = str(token.get("kind") or "NUMBER")
        if lexical_type == "NUMBER" and raw[:1] in {"+", "-"}:
            lexical_type = "SIGNED_NUMBER"
        occurrences.append(
            CriticalValueOccurrence(
                occurrence_id=f"{claim_id}.O{index}",
                span_start=start,
                span_end=end,
                raw_literal=raw,
                normalized_value=str(token.get("value", "")),
                lexical_type=lexical_type,
                unit=token.get("unit"),
                # All occurrences extracted from one answer belong to the
                # same claim unit. Clause-local context is derived later from
                # the immutable span; it must not become a second identity.
                claim_unit_id=claim_id,
                extraction_source="canonical-v2-v6-lexical-boundary-contract",
            )
        )
    return tuple(occurrences)


def occurrence_local_context(
    text: str, occurrence: CriticalValueOccurrence, *, radius: int = 96
) -> tuple[str, str, str]:
    """Return bounded `(clause, left, right)` context for a known occurrence."""
    start, end = occurrence.span_start, occurrence.span_end
    bounded_start = max(0, start - radius)
    bounded_end = min(len(text), end + radius)
    bounded = text[bounded_start:bounded_end]
    local_start = start - bounded_start
    local_end = end - bounded_start
    # A period is a clause boundary only when followed by whitespace/end.
    # This keeps decimal and version interiors attached to the known span.
    boundaries = [match.start() for match in re.finditer(r"[!?;]|\.(?=\s|$)", bounded)]
    left_boundary = max((position for position in boundaries if position < local_start), default=-1)
    right_boundary = min(
        (position for position in boundaries if position >= local_end),
        default=len(bounded),
    )
    return (
        bounded[left_boundary + 1 : right_boundary],
        bounded[left_boundary + 1 : local_start],
        bounded[local_end:right_boundary],
    )
