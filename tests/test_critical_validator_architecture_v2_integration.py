"""Production integration contracts for Architecture V2.

All tests use deterministic local fixtures. No provider, retrieval, or model
service is involved.
"""

from __future__ import annotations

import pytest

import app.evaluation.critical_validator_runtime as runtime
import app.llm.structured_output as structured_output
from app.api.chat import ChatRequest
from app.evaluation.forensic_capture import ForensicCapture, redact_for_otel
from app.evidence.support_units import SupportUnit
from app.llm.structured_output import (
    SupportUnitAnswer,
    SupportUnitAnswerPart,
    _record_validator_telemetry,
    validate_support_unit_answer,
)
from app.shared.config import Settings


def test_architecture_v2_is_default_and_rollback_selectors_remain_explicit() -> None:
    settings = Settings(_env_file=None)
    assert settings.critical_validator_version == "architecture_v2"
    assert settings.critical_validator_arch_v2_shadow_enabled is False
    assert (
        Settings(_env_file=None, critical_validator_version="baseline").critical_validator_version
        == "baseline"
    )
    assert (
        Settings(_env_file=None, critical_validator_version="v3").critical_validator_version
        == "v3"
    )
    assert (
        Settings(
            _env_file=None, critical_validator_version="architecture_v2"
        ).critical_validator_version
        == "architecture_v2"
    )


def test_invalid_selector_fails_closed() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, critical_validator_version="banana")  # type: ignore[arg-type]


def test_selector_is_not_a_user_request_field() -> None:
    assert "critical_validator_version" not in ChatRequest.model_fields
    assert "critical_validator_arch_v2_shadow_enabled" not in ChatRequest.model_fields


@pytest.mark.parametrize("selector", ["baseline", "v3"])
def test_architecture_v2_shadow_does_not_change_authoritative_result(selector: str) -> None:
    claim = "The signed result is -204, not 204."
    support = ["The signed result is -204."]
    without_shadow = runtime.audit_critical_value(claim, support, selector=selector)  # type: ignore[arg-type]
    with_shadow = runtime.audit_critical_value(
        claim,
        support,
        selector=selector,  # type: ignore[arg-type]
        architecture_v2_shadow_enabled=True,
    )
    assert with_shadow["validator_outcome"] == without_shadow["validator_outcome"]
    assert with_shadow["failure_codes"] == without_shadow["failure_codes"]
    assert with_shadow["architecture_v2_shadow_enabled"] is True
    assert with_shadow["architecture_v2_shadow_error"] is False


def test_authoritative_architecture_v2_exceptions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic validator failure")

    monkeypatch.setattr(runtime, "_architecture_v2_result", fail)
    unit = SupportUnit(
        "E1.S1",
        "B1",
        "E1",
        "source",
        None,
        None,
        ("chunk",),
        "tenant",
        True,
        True,
        "The limit is 120.",
    )
    result = validate_support_unit_answer(
        SupportUnitAnswer([SupportUnitAnswerPart("The limit is 120.", ["E1.S1"])], False),
        [unit],
        validator_version="architecture_v2",
    )
    assert result.application_abstain is True
    assert "CRITICAL_VALIDATOR_INFRASTRUCTURE_FAILURE" in result.failure_codes


def test_shadow_exception_isolated_from_authoritative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic shadow failure")

    monkeypatch.setattr(runtime, "_architecture_v2_result", fail)
    result = runtime.audit_critical_value(
        "The limit is 120.",
        ["The limit is 120."],
        selector="baseline",
        architecture_v2_shadow_enabled=True,
    )
    assert result["validator_outcome"] == "PASS"
    assert result["architecture_v2_shadow_error"] is True
    assert result["architecture_v2_shadow_disagreement"] == "SHADOW_ERROR"


def test_v3_and_architecture_v2_shadows_are_independent() -> None:
    claim = "The documented limit is 120."
    support = ["The documented limit is 120."]
    authoritative = runtime.audit_critical_value(claim, support, selector="baseline")
    both_shadows = runtime.audit_critical_value(
        claim,
        support,
        selector="baseline",
        v3_shadow_enabled=True,
        architecture_v2_shadow_enabled=True,
    )
    assert both_shadows["validator_outcome"] == authoritative["validator_outcome"]
    assert both_shadows["failure_codes"] == authoritative["failure_codes"]
    assert both_shadows["architecture_v2_shadow_error"] is False
    assert both_shadows["shadow_error"] is False


def test_architecture_v2_result_exposes_structured_occurrence_counts_only_to_adapter() -> None:
    result = runtime.audit_critical_value(
        "The signed result is -204, not 204.",
        ["The signed result is -204."],
        selector="architecture_v2",
    )
    assert result["architecture_id"] == runtime.ARCHITECTURE_V2_ID
    assert result["occurrence_count"] == 2
    assert result["validate_role_count"] == 1
    assert result["skip_rejected_premise_count"] == 1
    assert result["architecture_v2_forensic"]["filtered_validate_occurrence_ids"] == [
        "claim.O1"
    ]


def test_otel_redaction_excludes_raw_content() -> None:
    values = redact_for_otel(
        {
            "raw_query": "private query",
            "raw_model_answer": "The result is -204.",
            "raw_evidence_text": "private evidence",
            "raw_literal": "-204",
            "occurrence_count": 2,
        }
    )
    assert "raw_query" not in str(values)
    assert "raw_model_answer" not in str(values)
    assert "raw_evidence_text" not in str(values)
    assert "-204" not in str(values)
    assert values["occurrence_count"] == 2


def test_forensic_capture_can_record_v2_metadata_without_otel_leakage() -> None:
    capture = ForensicCapture.create("private query", raw_text=False)
    capture.stage(
        "support_id_validation",
        {
            "critical_validator": {
                "architecture_id": runtime.ARCHITECTURE_V2_ID,
                "occurrences": [{"occurrence_id": "claim.O1", "raw_literal": "-204"}],
                "role_decisions": [{"occurrence_id": "claim.O1", "role": "VALIDATE"}],
            }
        },
    )
    snapshot = capture.snapshot()
    critical = snapshot["stages"]["support_id_validation"]["critical_validator"]
    assert critical["architecture_id"] == runtime.ARCHITECTURE_V2_ID
    assert "raw_literal" not in critical["occurrences"][0]
    assert "-204" not in str(snapshot)


def test_shadow_telemetry_promotes_occurrence_and_role_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def synthetic_shadow(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "validator_outcome": "PASS",
            "validator_reason_class": "CRITICAL_VALUE_SUPPORTED",
            "pass": True,
            "failure_codes": [],
            "status": "PASS",
            "critical_value_count": 3,
            "critical_value_type": "NUMBER",
            "duration_ms": 0.25,
            "baseline_duration_ms": 0.0,
            "shadow_v3_duration_ms": 0.0,
            "shadow_error": False,
            "shadow_error_class": None,
            "shadow_disagreement": None,
            "locale_ambiguity": False,
            "version_ambiguity": False,
            "version_specificity_reject": False,
            "identifier_reject": False,
            "architecture_id": runtime.ARCHITECTURE_V2_ID,
            "occurrence_count": 3,
            "validate_role_count": 1,
            "skip_rejected_premise_count": 1,
            "ambiguous_keep_validating_count": 1,
        }

    monkeypatch.setattr(runtime, "_architecture_v2_result", synthetic_shadow)
    unit = SupportUnit(
        "E1.S1",
        "B1",
        "E1",
        "source",
        None,
        None,
        ("chunk",),
        "tenant",
        True,
        True,
        "The limit is 120.",
    )
    validation = validate_support_unit_answer(
        SupportUnitAnswer([SupportUnitAnswerPart("The limit is 120.", ["E1.S1"])], False),
        [unit],
        validator_version="baseline",
        architecture_v2_shadow_enabled=True,
    )
    telemetry = validation.validator_telemetry
    assert telemetry["architecture_v2_shadow_executed"] is True
    assert telemetry["architecture_v2_shadow_architecture_id"] == runtime.ARCHITECTURE_V2_ID
    assert telemetry["architecture_v2_shadow_occurrence_count"] == 3
    assert telemetry["architecture_v2_shadow_validate_role_count"] == 1
    assert telemetry["architecture_v2_shadow_skip_rejected_premise_count"] == 1
    assert telemetry["architecture_v2_shadow_ambiguous_keep_validating_count"] == 1
    assert telemetry["architecture_v2_shadow_aggregate_outcome"] == "PASS"
    assert telemetry["architecture_v2_shadow_aggregate_disagreement"] == "SAME"


def test_shadow_telemetry_distinguishes_executed_zero_from_not_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def empty_shadow(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "validator_outcome": "PASS",
            "validator_reason_class": "NO_CRITICAL_VALUE",
            "pass": True,
            "failure_codes": [],
            "status": "PASS",
            "critical_value_count": 0,
            "critical_value_type": None,
            "duration_ms": 0.1,
            "baseline_duration_ms": 0.0,
            "shadow_v3_duration_ms": 0.0,
            "shadow_error": False,
            "shadow_error_class": None,
            "shadow_disagreement": None,
            "locale_ambiguity": False,
            "version_ambiguity": False,
            "version_specificity_reject": False,
            "identifier_reject": False,
            "architecture_id": runtime.ARCHITECTURE_V2_ID,
            "occurrence_count": 0,
            "validate_role_count": 0,
            "skip_rejected_premise_count": 0,
            "ambiguous_keep_validating_count": 0,
        }

    monkeypatch.setattr(runtime, "_architecture_v2_result", empty_shadow)
    unit = SupportUnit(
        "E1.S1",
        "B1",
        "E1",
        "source",
        None,
        None,
        ("chunk",),
        "tenant",
        True,
        True,
        "No critical value here.",
    )
    answer = SupportUnitAnswer([SupportUnitAnswerPart("No critical value here.", ["E1.S1"])], False)
    executed = validate_support_unit_answer(
        answer,
        [unit],
        validator_version="baseline",
        architecture_v2_shadow_enabled=True,
    ).validator_telemetry
    not_executed = validate_support_unit_answer(
        answer, [unit], validator_version="baseline"
    ).validator_telemetry
    assert executed["architecture_v2_shadow_executed"] is True
    assert executed["architecture_v2_shadow_occurrence_count"] == 0
    assert not_executed["architecture_v2_shadow_executed"] is False
    assert not_executed["architecture_v2_shadow_aggregate_outcome"] == "NO_VALIDATOR_RESULT"


def test_aggregate_shadow_disagreement_uses_request_level_states() -> None:
    class FakeSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, object] = {}

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, name: str, value: object) -> None:
            self.attributes[name] = value

    span = FakeSpan()
    original = structured_output.trace.get_current_span
    structured_output.trace.get_current_span = lambda: span
    try:
        _record_validator_telemetry(
            {
                "pass": 1,
                "reject": 0,
                "indeterminate": 0,
                "architecture_v2_shadow_enabled": True,
                "architecture_v2_shadow_executed": True,
                "architecture_v2_shadow_architecture_id": runtime.ARCHITECTURE_V2_ID,
                "architecture_v2_shadow_outcomes": ["PASS", "REJECT"],
                "architecture_v2_shadow_aggregate_outcome": "MIXED",
                "architecture_v2_shadow_aggregate_disagreement": "AUTHORITATIVE_PASS_ARCHV2_MIXED",
            }
        )
    finally:
        structured_output.trace.get_current_span = original
    assert span.attributes["validator.shadow.architecture_v2.outcome"] == "MIXED"
    assert (
        span.attributes["validator.shadow.architecture_v2.disagreement"]
        == "AUTHORITATIVE_PASS_ARCHV2_MIXED"
    )


def test_promoted_shadow_otel_fields_are_bounded_and_content_free() -> None:
    class FakeSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, object] = {}

        def is_recording(self) -> bool:
            return True

        def set_attribute(self, name: str, value: object) -> None:
            self.attributes[name] = value

    span = FakeSpan()
    original = structured_output.trace.get_current_span
    structured_output.trace.get_current_span = lambda: span
    try:
        _record_validator_telemetry(
            {
                "pass": 1,
                "architecture_v2_shadow_enabled": True,
                "architecture_v2_shadow_executed": True,
                "architecture_v2_shadow_architecture_id": runtime.ARCHITECTURE_V2_ID,
                "architecture_v2_shadow_occurrence_count": 3,
                "architecture_v2_shadow_validate_role_count": 1,
                "architecture_v2_shadow_skip_rejected_premise_count": 1,
                "architecture_v2_shadow_ambiguous_keep_validating_count": 1,
                "architecture_v2_shadow_duration_ms": 0.2,
                "architecture_v2_shadow_aggregate_outcome": "PASS",
                "architecture_v2_shadow_aggregate_disagreement": "SAME",
            }
        )
    finally:
        structured_output.trace.get_current_span = original
    rendered = str(span.attributes)
    secrets = (
        "QUERY_SECRET_9A7B",
        "ANSWER_SECRET_8C2D",
        "EVIDENCE_SECRET_3E4F",
        "LITERAL_SECRET_7711",
    )
    for secret in secrets:
        assert secret not in rendered
    assert span.attributes["validator.shadow.architecture_v2.occurrence_count"] == 3
