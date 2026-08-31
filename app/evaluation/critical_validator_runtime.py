"""Server-side adapter for the frozen V3 and Architecture V2 validators.

Architecture V2 is deliberately kept in its frozen experimental modules. This
adapter owns only runtime selection, isolated shadow comparison, and the
bounded result fields consumed by the existing support-ID pipeline.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, Literal, cast

from app.evaluation.critical_validator_architecture_v2 import (
    audit_claim_architecture_v2,
)
from app.evaluation.critical_values import claim_local_critical_value_audit

ValidatorSelector = Literal["baseline", "v3", "architecture_v2"]
VALIDATOR_SELECTORS = ("baseline", "v3", "architecture_v2")
ARCHITECTURE_V2_ID = "CRITICAL_VALUE_VALIDATOR_ARCHITECTURE_V2_09d94bb7c9d1"


def validate_validator_selector(value: str) -> ValidatorSelector:
    """Validate the server-owned selector and fail closed on unknown values."""
    if value not in VALIDATOR_SELECTORS:
        raise ValueError(
            "critical validator selector must be one of "
            f"{VALIDATOR_SELECTORS}, got {value!r}"
        )
    return cast(ValidatorSelector, value)


def _outcome(result: dict[str, Any]) -> str:
    value = result.get("validator_outcome") or result.get("outcome")
    if value in {"PASS", "REJECT", "INDETERMINATE"}:
        return str(value)
    if result.get("pass"):
        return "PASS"
    return "REJECT"


def _shadow_comparison(authoritative: str, shadow: str) -> str:
    if authoritative == shadow:
        return "SAME"
    shadow_code = "IND" if shadow == "INDETERMINATE" else shadow
    return f"AUTHORITATIVE_{authoritative}_ARCHV2_{shadow_code}"


def _architecture_v2_result(
    claim: str,
    support_texts: Sequence[str],
    *,
    claim_id: str = "claim",
) -> dict[str, Any]:
    """Adapt the frozen Architecture V2 result to the production result shape."""
    started = time.perf_counter()
    architecture = audit_claim_architecture_v2(
        claim, support_texts, claim_id=claim_id
    )
    v3_result = dict(architecture["v3"])
    decisions = architecture["role_decisions"]
    role_counts = {
        "validate_role_count": sum(d.role == "VALIDATE" for d in decisions),
        "skip_rejected_premise_count": sum(
            d.role == "SKIP_REJECTED_PREMISE" for d in decisions
        ),
        "ambiguous_keep_validating_count": sum(
            d.role == "AMBIGUOUS_KEEP_VALIDATING" for d in decisions
        ),
    }
    result = {
        **v3_result,
        "validator_version": "architecture_v2",
        "architecture_id": ARCHITECTURE_V2_ID,
        "validator_outcome": _outcome(v3_result),
        "validator_reason_class": v3_result.get(
            "validator_reason_class", "CRITICAL_VALUE_SUPPORTED"
        ),
        "forced_abstain": _outcome(v3_result) != "PASS",
        "status": (
            "CRITICAL_VALUE_DIRECT_CONFLICT"
            if _outcome(v3_result) == "REJECT"
            else "CRITICAL_VALUE_INDETERMINATE"
            if _outcome(v3_result) == "INDETERMINATE"
            else "CRITICAL_VALUE_SUPPORTED"
        ),
        "indeterminate": _outcome(v3_result) == "INDETERMINATE",
        "locale_ambiguity": False,
        "version_ambiguity": False,
        "version_specificity_reject": _outcome(v3_result) == "REJECT"
        and any(
            occurrence.lexical_type == "VERSION"
            for occurrence in architecture["occurrences"]
        ),
        "identifier_reject": _outcome(v3_result) == "REJECT"
        and any(
            occurrence.lexical_type in {"IDENTIFIER", "SIGNED_IDENTIFIER"}
            for occurrence in architecture["occurrences"]
        ),
        "duration_ms": 0.0,
        "baseline_duration_ms": 0.0,
        "shadow_v3_duration_ms": 0.0,
        "shadow_enabled": False,
        "shadow_disagreement": None,
        "shadow_error": False,
        "shadow_error_class": None,
        "shadow_v3_outcome": None,
        "shadow_v3_reason_class": None,
        "critical_value_count": len(architecture["occurrences"]),
        "critical_value_type": (
            architecture["occurrences"][0].lexical_type
            if architecture["occurrences"]
            else None
        ),
        "occurrence_count": len(architecture["occurrences"]),
        **role_counts,
        "occurrence_identity_error_count": 0,
        "role_classification_error_count": 0,
        "architecture_v2_forensic": {
            "architecture_id": ARCHITECTURE_V2_ID,
            "occurrences": [
                {
                    "occurrence_id": occurrence.occurrence_id,
                    "span_start": occurrence.span_start,
                    "span_end": occurrence.span_end,
                    "raw_literal": occurrence.raw_literal,
                    "normalized_value": occurrence.normalized_value,
                    "lexical_type": occurrence.lexical_type,
                    "unit": occurrence.unit,
                    "claim_unit_id": occurrence.claim_unit_id,
                }
                for occurrence in architecture["occurrences"]
            ],
            "role_decisions": [
                {
                    "occurrence_id": decision.occurrence_id,
                    "role": decision.role,
                    "reason": decision.reason_code,
                    "determinism": decision.determinism,
                }
                for decision in decisions
            ],
            "filtered_validate_occurrence_ids": list(
                architecture["validate_occurrence_ids"]
            ),
            "v3_result": v3_result,
        },
    }
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def audit_critical_value(
    claim: str,
    support_texts: Sequence[str],
    *,
    selector: ValidatorSelector = "architecture_v2",
    v3_shadow_enabled: bool = False,
    architecture_v2_shadow_enabled: bool = False,
    claim_id: str = "claim",
) -> dict[str, Any]:
    """Run the selected validator and optional diagnostic Architecture V2 shadow."""
    selected = validate_validator_selector(selector)
    if selected == "architecture_v2":
        result = _architecture_v2_result(claim, support_texts, claim_id=claim_id)
        # V2 already delegates to frozen V3 comparison semantics. A second V2
        # shadow would duplicate work and make telemetry ambiguous.
        result["architecture_v2_shadow_enabled"] = False
        result["architecture_v2_shadow_outcome"] = None
        result["architecture_v2_shadow_disagreement"] = None
        result["architecture_v2_shadow_error"] = False
        result["architecture_v2_shadow_executed"] = False
        result["architecture_v2_shadow_architecture_id"] = None
        result["architecture_v2_shadow_occurrence_count"] = 0
        result["architecture_v2_shadow_validate_role_count"] = 0
        result["architecture_v2_shadow_skip_rejected_premise_count"] = 0
        result["architecture_v2_shadow_ambiguous_keep_validating_count"] = 0
        result["architecture_v2_shadow_duration_ms"] = 0.0
        return result

    result = claim_local_critical_value_audit(
        claim,
        support_texts,
        validator_version=selected,
        shadow_enabled=v3_shadow_enabled,
    )
    result = dict(result)
    result["architecture_id"] = None
    result["architecture_v2_shadow_enabled"] = bool(architecture_v2_shadow_enabled)
    result["architecture_v2_shadow_outcome"] = None
    result["architecture_v2_shadow_disagreement"] = None
    result["architecture_v2_shadow_error"] = False
    result["architecture_v2_shadow_executed"] = False
    result["architecture_v2_shadow_architecture_id"] = None
    result["architecture_v2_shadow_occurrence_count"] = 0
    result["architecture_v2_shadow_validate_role_count"] = 0
    result["architecture_v2_shadow_skip_rejected_premise_count"] = 0
    result["architecture_v2_shadow_ambiguous_keep_validating_count"] = 0
    result["architecture_v2_shadow_duration_ms"] = 0.0
    result["occurrence_count"] = 0
    result["validate_role_count"] = 0
    result["skip_rejected_premise_count"] = 0
    result["ambiguous_keep_validating_count"] = 0
    result["occurrence_identity_error_count"] = 0
    result["role_classification_error_count"] = 0
    if architecture_v2_shadow_enabled:
        try:
            shadow_result = _architecture_v2_result(claim, support_texts, claim_id=claim_id)
            shadow_outcome = _outcome(shadow_result)
            result["architecture_v2_shadow_outcome"] = shadow_outcome
            result["architecture_v2_shadow_disagreement"] = _shadow_comparison(
                _outcome(result), shadow_outcome
            )
            result["architecture_v2_shadow_executed"] = True
            result["architecture_v2_shadow_architecture_id"] = shadow_result.get(
                "architecture_id"
            )
            result["architecture_v2_shadow_occurrence_count"] = int(
                shadow_result.get("occurrence_count", 0)
            )
            result["architecture_v2_shadow_validate_role_count"] = int(
                shadow_result.get("validate_role_count", 0)
            )
            result["architecture_v2_shadow_skip_rejected_premise_count"] = int(
                shadow_result.get("skip_rejected_premise_count", 0)
            )
            result["architecture_v2_shadow_ambiguous_keep_validating_count"] = int(
                shadow_result.get("ambiguous_keep_validating_count", 0)
            )
            result["architecture_v2_shadow_duration_ms"] = float(
                shadow_result.get("duration_ms", 0.0)
            )
            result["architecture_v2_shadow_forensic"] = shadow_result.get(
                "architecture_v2_forensic"
            )
        except Exception:
            # Diagnostic only: never alter the authoritative result.
            result["architecture_v2_shadow_error"] = True
            result["architecture_v2_shadow_error_class"] = (
                "ARCHITECTURE_V2_SHADOW_EVALUATION_FAILURE"
            )
            result["architecture_v2_shadow_disagreement"] = "SHADOW_ERROR"
            result["architecture_v2_shadow_executed"] = False
    return result
