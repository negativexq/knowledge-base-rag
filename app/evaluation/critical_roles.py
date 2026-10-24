"""Occurrence-local deterministic role classification for Architecture V2."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.evaluation.critical_occurrences import (
    CriticalValueOccurrence,
    extract_critical_occurrences,
    occurrence_local_context,
)

OccurrenceRole = Literal[
    "VALIDATE",
    "SKIP_REJECTED_PREMISE",
    "SKIP_QUERY_ECHO",
    "SKIP_VERDICT",
    "AMBIGUOUS_KEEP_VALIDATING",
]
SKIP_ROLES = frozenset({"SKIP_REJECTED_PREMISE", "SKIP_QUERY_ECHO", "SKIP_VERDICT"})
_VERDICT_END = re.compile(r"\s*(?:[.,;:!]|—|-\s|$)")


def _is_leading_verdict(answer: str, occurrence: CriticalValueOccurrence) -> bool:
    """A yes/no that opens the answer ("No. CA03 is ...") judges the question;
    it is not a value copied from the support."""
    return (
        occurrence.lexical_type == "BOOLEAN"
        and not answer[: occurrence.span_start].strip(" \t\n*\"'")
        and _VERDICT_END.match(answer, occurrence.span_end) is not None
    )


QueryValue = tuple[str, str]
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


def question_values(question: str | None) -> frozenset[QueryValue]:
    """Every value the question states. They are premises an answer repeats
    when an independent scope review checks the answer's question binding
    (a period the evidence lacks is a scope mismatch there)."""
    if not question:
        return frozenset()
    return frozenset(
        (o.normalized_value, o.lexical_type) for o in extract_critical_occurrences(question)
    )


def grounded_query_values(
    question: str | None, evidence_texts: Iterable[str]
) -> frozenset[QueryValue]:
    """Values the question states that the evidence also holds ("FY 2021",
    "65+"): premises an answer repeats, not values it claims."""
    asked = question_values(question)
    if not asked:
        return frozenset()
    held = {
        (o.normalized_value, o.lexical_type)
        for text in evidence_texts
        for o in extract_critical_occurrences(text)
    }
    return frozenset(asked & held)


def _query_echo_ids(
    occurrences: Sequence[CriticalValueOccurrence],
    query_values: frozenset[QueryValue],
    verdicts: set[str],
) -> set[str]:
    """Echoes are skipped only beside a value that is still validated in the
    same claim unit: an answer made only of question values (a yes/no
    confirmation of the question's figure) is validated in full. A skipped
    verdict is not such a value."""
    if not query_values:
        return set()
    echoes = {
        o.occurrence_id for o in occurrences if (o.normalized_value, o.lexical_type) in query_values
    }
    claimed_units = {
        o.claim_unit_id for o in occurrences if o.occurrence_id not in echoes | verdicts
    }
    return {
        o.occurrence_id
        for o in occurrences
        if o.occurrence_id in echoes and o.claim_unit_id in claimed_units
    }


def classify_occurrence_roles(
    answer: str,
    occurrences: Sequence[CriticalValueOccurrence],
    *,
    query_values: frozenset[QueryValue] = frozenset(),
    support_states_boolean: bool = True,
) -> tuple[OccurrenceRoleDecision, ...]:
    """Assign a role to each known occurrence without creating new ones.

    A leading verdict is skipped only when the support states no boolean of
    its own; otherwise it is compared ("Yes" against "enabled: false")."""
    decisions: list[OccurrenceRoleDecision] = []
    verdicts = (
        set()
        if support_states_boolean
        else {o.occurrence_id for o in occurrences if _is_leading_verdict(answer, o)}
    )
    echoes = _query_echo_ids(occurrences, query_values, verdicts)
    for occurrence in occurrences:
        if occurrence.occurrence_id in verdicts:
            decisions.append(
                OccurrenceRoleDecision(
                    occurrence.occurrence_id,
                    "SKIP_VERDICT",
                    "LEADING_VERDICT_NO_SUPPORT_BOOLEAN",
                    "DETERMINISTIC",
                )
            )
        elif occurrence.occurrence_id in echoes:
            decisions.append(
                OccurrenceRoleDecision(
                    occurrence.occurrence_id,
                    "SKIP_QUERY_ECHO",
                    "QUERY_ECHO_GROUNDED_PREMISE",
                    "DETERMINISTIC",
                )
            )
        elif _is_rejected_premise(answer, occurrence, occurrences):
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
