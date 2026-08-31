"""Experimental Architecture V2 pipeline; never selected by production config."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.evaluation.critical_occurrence_validation import validate_occurrences_v3
from app.evaluation.critical_occurrences import extract_critical_occurrences
from app.evaluation.critical_roles import classify_occurrence_roles


def audit_claim_architecture_v2(
    claim: str,
    support_texts: Sequence[str],
    *,
    claim_id: str = "claim",
) -> dict[str, Any]:
    """Run extraction, occurrence-local roles, structured filtering, and V3."""
    occurrences = extract_critical_occurrences(claim, claim_id=claim_id)
    role_decisions = classify_occurrence_roles(claim, occurrences)
    validate_ids = tuple(
        decision.occurrence_id
        for decision in role_decisions
        if decision.role != "SKIP_REJECTED_PREMISE"
    )
    validate_occurrences = tuple(
        occurrence for occurrence in occurrences if occurrence.occurrence_id in validate_ids
    )
    v3 = validate_occurrences_v3(claim, support_texts, validate_occurrences)
    return {
        "architecture": "CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2",
        "claim": claim,
        "occurrences": occurrences,
        "role_decisions": role_decisions,
        "validate_occurrence_ids": validate_ids,
        "v3": v3,
        "raw_text_masked": False,
        "post_role_reextraction": False,
        "role_layer_rediscovery": False,
    }
