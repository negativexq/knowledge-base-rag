"""Reusable contract and rollout-control tests for the V3 validator port."""

from __future__ import annotations

import pytest

import app.evaluation.critical_values as critical_values
from app.evaluation.critical_values import claim_local_critical_value_audit
from app.shared.config import Settings


def audit(claim: str, support: str, *, version: str = "v3", shadow: bool = False) -> dict:
    return claim_local_critical_value_audit(
        claim,
        [support],
        validator_version=version,  # type: ignore[arg-type]
        shadow_enabled=shadow,
    )


def test_validator_rollout_defaults_to_baseline_and_shadow_off() -> None:
    settings = Settings(_env_file=None)
    assert settings.critical_validator_version == "baseline"
    assert settings.critical_validator_v3_shadow_enabled is False


def test_invalid_validator_version_fails_closed() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, critical_validator_version="v4")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("claim", "support", "expected"),
    [
        ("The limit is 131,072 bytes.", "The limit is 131072 bytes.", "PASS"),
        ("The ratio is 1.000.", "The ratio is 1000.", "INDETERMINATE"),
        ("The return code is -204.", "The return code is 204.", "REJECT"),
        ("The issue is CVE-2024-1234.", "The issue is CVE-2024-1235.", "REJECT"),
        ("SQLCODE -204 is returned.", "SQLCODE -204 is returned.", "PASS"),
        ("Version 8 family is supported.", "Version 8.1.2 is supported.", "PASS"),
        ("Exactly version 8.0.0 is required.", "Version 8.1.2 is installed.", "REJECT"),
        ("Version 8.1 is supported.", "Version 8.1.7 is installed.", "INDETERMINATE"),
    ],
)
def test_v3_reusable_contracts(claim: str, support: str, expected: str) -> None:
    assert audit(claim, support)["validator_outcome"] == expected


def test_shadow_evaluates_v3_without_changing_baseline_result() -> None:
    without_shadow = audit(
        "The limit is 131,072 bytes.",
        "The limit is 131072 bytes.",
        version="baseline",
    )
    with_shadow = audit(
        "The limit is 131,072 bytes.",
        "The limit is 131072 bytes.",
        version="baseline",
        shadow=True,
    )
    assert with_shadow["validator_outcome"] == without_shadow["validator_outcome"] == "REJECT"
    assert with_shadow["shadow_disagreement"] == "BASELINE_REJECT_V3_PASS"


def test_v3_primary_does_not_run_a_second_shadow_path() -> None:
    result = audit(
        "Version 8 family is supported.",
        "Version 8.1.2 is supported.",
        version="v3",
        shadow=True,
    )
    assert result["validator_outcome"] == "PASS"
    assert result["shadow_disagreement"] is None
    assert result["shadow_v3_duration_ms"] == 0


def test_validator_telemetry_is_bounded_and_contains_no_raw_inputs() -> None:
    claim = "The limit is 131,072 bytes."
    support = "The limit is 131072 bytes."
    result = audit(claim, support)
    telemetry_keys = {
        "validator_version",
        "validator_outcome",
        "validator_reason_class",
        "critical_value_type",
        "critical_value_count",
        "duration_ms",
        "baseline_duration_ms",
        "shadow_v3_duration_ms",
        "shadow_error",
        "shadow_error_class",
        "shadow_disagreement",
    }
    assert telemetry_keys <= result.keys()
    telemetry = {key: result[key] for key in telemetry_keys}
    assert claim not in str(telemetry)
    assert support not in str(telemetry)
    assert result["duration_ms"] >= 0
    assert result["baseline_duration_ms"] >= 0
    assert result["shadow_v3_duration_ms"] == 0
    assert result["shadow_error"] is False


def test_shadow_failure_is_isolated_from_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = audit(
        "The limit is 131,072 bytes.",
        "The limit is 131072 bytes.",
        version="baseline",
    )

    def fail_shadow(*args: object, **kwargs: object) -> str:
        raise RuntimeError("synthetic shadow failure")

    monkeypatch.setattr(critical_values, "_v3_status", fail_shadow)
    with_shadow = audit(
        "The limit is 131,072 bytes.",
        "The limit is 131072 bytes.",
        version="baseline",
        shadow=True,
    )

    assert with_shadow["validator_outcome"] == baseline["validator_outcome"] == "REJECT"
    assert with_shadow["failure_codes"] == baseline["failure_codes"]
    assert with_shadow["shadow_error"] is True
    assert with_shadow["shadow_error_class"] == "SHADOW_EVALUATION_FAILURE"
    assert with_shadow["shadow_disagreement"] == "SHADOW_ERROR"
    assert with_shadow["shadow_v3_duration_ms"] >= 0
