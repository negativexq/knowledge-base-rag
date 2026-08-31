"""Occurrence-aware adapter that delegates comparison semantics to frozen V3."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.evaluation.critical_occurrences import CriticalValueOccurrence
from app.evaluation.critical_values import (
    _v3_ambiguous_locale_pair,
    _v3_relation_audit,
    _v3_version_guard_status,
    _v3_version_signal,
)


def _token(occurrence: CriticalValueOccurrence, answer: str) -> dict[str, Any]:
    kind = "NUMBER" if occurrence.lexical_type == "SIGNED_NUMBER" else occurrence.lexical_type
    return {
        "kind": kind,
        "value": occurrence.normalized_value,
        "unit": occurrence.unit,
        "start": occurrence.span_start,
        "end": occurrence.span_end,
        "local_context": answer[
            max(0, occurrence.span_start - 64) : min(len(answer), occurrence.span_end + 64)
        ],
    }


def validate_occurrences_v3(
    answer: str,
    support_texts: Sequence[str],
    occurrences: Sequence[CriticalValueOccurrence],
) -> dict[str, Any]:
    """Validate selected occurrences while preserving V3 comparison primitives.

    The answer is never masked and the canonical occurrence tuple is the only
    source for claim tokens. Support text is tokenized once per support unit by
    the canonical extractor before entering this adapter.
    """
    from app.evaluation.critical_occurrences import extract_critical_occurrences

    claim_tokens = [_token(occurrence, answer) for occurrence in occurrences]
    support_occurrences = [extract_critical_occurrences(text) for text in support_texts]
    support_tokens = [
        [_token(occurrence, text) for occurrence in occurrences_for_support]
        for text, occurrences_for_support in zip(support_texts, support_occurrences)
    ]
    support = " ".join(support_texts)
    statuses: list[str] = []
    if occurrences and _v3_version_signal(answer) and any(
        occurrence.lexical_type == "VERSION" for occurrence in occurrences
    ):
        claim_versions = [
            tuple(int(part) for part in occurrence.normalized_value.split("."))
            for occurrence in occurrences
            if occurrence.lexical_type == "VERSION"
        ]
        version_status = _v3_version_guard_status(
            answer,
            support,
            claim_versions=claim_versions,
        )
        if version_status:
            statuses.append(version_status)
    if occurrences and not statuses:
        statuses.extend(
            _v3_relation_audit(
                answer,
                support_texts,
                claim_tokens=claim_tokens,
                support_tokens=support_tokens,
            )
        )
    if occurrences and _v3_ambiguous_locale_pair(answer, support):
        statuses.append("INDETERMINATE")
    outcome = (
        "REJECT"
        if "DIRECT_CONFLICT" in statuses
        else "INDETERMINATE"
        if "INDETERMINATE" in statuses
        else "PASS"
    )
    return {
        "validator_version": "v3",
        "validator_outcome": outcome,
        "validator_reason_class": (
            "CRITICAL_VALUE_DIRECT_CONFLICT"
            if outcome == "REJECT"
            else "CRITICAL_VALUE_INDETERMINATE"
            if outcome == "INDETERMINATE"
            else "CRITICAL_VALUE_SUPPORTED"
        ),
        "pass": outcome == "PASS",
        "failure_codes": (
            ["CRITICAL_VALUE_DIRECT_CONFLICT"]
            if outcome == "REJECT"
            else ["CRITICAL_VALUE_INDETERMINATE"]
            if outcome == "INDETERMINATE"
            else []
        ),
        "occurrence_statuses": statuses,
        "validated_occurrence_ids": [occurrence.occurrence_id for occurrence in occurrences],
    }
