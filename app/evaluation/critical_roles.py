"""Occurrence-local deterministic role classification for Architecture V2."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.evaluation.critical_occurrences import (
    CriticalValueOccurrence,
    occurrence_local_context,
)

OccurrenceRole = Literal[
    "VALIDATE",
    "SKIP_REJECTED_PREMISE",
    "AMBIGUOUS_KEEP_VALIDATING",
]
RoleDeterminism = Literal["DETERMINISTIC", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class OccurrenceRoleDecision:
    occurrence_id: str
    role: OccurrenceRole
    reason_code: str
    determinism: RoleDeterminism


_CORRECTION_WORDS = re.compile(
    r"\b(?:correct|incorrect|wrong|accurate|inaccurate|documented|supported|actual|valid)\b",
    re.IGNORECASE,
)
_REJECTION_WORDS = re.compile(
    r"\b(?:not|unsupported|wrong|incorrect|rather\s+than|instead\s+of)\b",
    re.IGNORECASE,
)


def _has_sibling(
    occurrence: CriticalValueOccurrence,
    occurrences: Sequence[CriticalValueOccurrence],
) -> bool:
    """Use the existing ledger as context; never rediscover text occurrences."""
    for sibling in occurrences:
        if sibling.occurrence_id == occurrence.occurrence_id:
            continue
        if sibling.claim_unit_id != occurrence.claim_unit_id:
            continue
        if sibling.span_start == occurrence.span_start and sibling.span_end == occurrence.span_end:
            continue
        if sibling.normalized_value == occurrence.normalized_value:
            return True
        if (
            sibling.lexical_type == occurrence.lexical_type
            and sibling.unit == occurrence.unit
            and sibling.normalized_value != occurrence.normalized_value
        ):
            return True
    return False


def _is_rejected_premise(
    text: str,
    occurrence: CriticalValueOccurrence,
    occurrences: Sequence[CriticalValueOccurrence],
) -> bool:
    clause, left, right = occurrence_local_context(text, occurrence)
    left_for_match = left.rstrip()
    explicit_separator = bool(
        re.search(
            r"[,;]\s*(?:not(?:\s+(?:(?:the|a|an)\s+)?"
            r"(?:release|version|value|figure|number))?|rather\s+than|instead\s+of)\s*$",
            left_for_match,
            re.IGNORECASE,
        )
        or re.search(r"(?:rather\s+than|instead\s+of)\s*$", left_for_match, re.IGNORECASE)
    )
    immediate_rejection = bool(
        re.search(
            r"\b(?:is|was)\s+(?:not\s+(?:correct|accurate|exact)|incorrect|wrong|inaccurate|rejected)\b",
            right,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:is|was)\s+not\s*$",
            left_for_match,
            re.IGNORECASE,
        )
        or re.search(
            r"\bdoes\s+not\s+support\s*$",
            left_for_match,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:rather\s+than|instead\s+of)\s+(?:(?:the|a|an)\s+)?"
            r"(?:release|version|value|figure|number)\s*$",
            left_for_match,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:is|was)\s+not\s+(?:the\s+)?"
            r"(?:setting|documented\s+value|limit|rate|version|identifier)\b",
            right,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:in|from)\s+(?:(?:the|your)\s+)?question\b.*\b(?:not|unsupported|wrong|incorrect)\b",
            right,
            re.IGNORECASE,
        )
        or (
            re.search(
                r"\b(?:you|user)\s+(?:mentioned|said|gave|provided|cited)\b",
                left_for_match,
                re.IGNORECASE,
            )
            and re.search(r"\b(?:but|not|unsupported|wrong|incorrect)\b", right, re.IGNORECASE)
        )
        or (
            re.search(
                r"\b(?:you|user)\s+(?:mentioned|said|gave|provided|cited)\s*$",
                left_for_match,
                re.IGNORECASE,
            )
            and re.search(r"\bbut\b", right, re.IGNORECASE)
        )
    )
    explicit_leading_rejection = bool(
        re.search(r"\b(?:is|was)\s+not\s*$", left_for_match, re.IGNORECASE)
        or re.search(r"\bdoes\s+not\s+support\s*$", left_for_match, re.IGNORECASE)
        or re.search(
            r"\b(?:rather\s+than|instead\s+of)\s+(?:(?:the|a|an)\s+)?"
            r"(?:release|version|value|figure|number|code|identifier|SQLCODE)\s*$",
            left_for_match,
            re.IGNORECASE,
        )
    )
    reported_correction = bool(
        re.search(
            r"\b(?:you|user)\s+(?:mentioned|said|gave|provided|cited)\s*$",
            left_for_match,
            re.IGNORECASE,
        )
        and re.search(
            r"\bbut\b.*\b(?:documentation|source|docs?)\b",
            right,
            re.IGNORECASE,
        )
    )
    return (
        _has_sibling(occurrence, occurrences)
        and (explicit_separator or immediate_rejection)
        and (
            explicit_separator
            or explicit_leading_rejection
            or reported_correction
            or _CORRECTION_WORDS.search(clause) is not None
            or _REJECTION_WORDS.search(right) is not None
            or re.search(r"\brejected\b", right, re.IGNORECASE) is not None
        )
    )


def classify_occurrence_roles(
    answer: str,
    occurrences: Sequence[CriticalValueOccurrence],
) -> tuple[OccurrenceRoleDecision, ...]:
    """Assign a role to each known occurrence without creating new ones."""
    decisions: list[OccurrenceRoleDecision] = []
    for occurrence in occurrences:
        if _is_rejected_premise(answer, occurrence, occurrences):
            decisions.append(
                OccurrenceRoleDecision(
                    occurrence.occurrence_id,
                    "SKIP_REJECTED_PREMISE",
                    "QUERY_ECHO_REJECTED_PREMISE",
                    "DETERMINISTIC",
                )
            )
        else:
            decisions.append(
                OccurrenceRoleDecision(
                    occurrence.occurrence_id,
                    "VALIDATE",
                    "NO_POLARITY_EXCEPTION",
                    "AMBIGUOUS"
                    if re.search(
                        r"\b(?:could|might|may|possibly)\b",
                        occurrence_local_context(answer, occurrence)[0],
                        re.I,
                    )
                    else "DETERMINISTIC",
                )
            )
    return tuple(decisions)
