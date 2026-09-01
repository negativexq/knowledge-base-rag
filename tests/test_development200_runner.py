# ruff: noqa: E501
"""Offline runner and checkpoint invariants for Development200."""

from __future__ import annotations

import json

import pytest

from scripts.experiments.run_development200 import (
    EXPECTED_CONFIG_FINGERPRINT,
    canonical_hash,
    run_key,
)


def test_run_key_is_deterministic_and_query_scoped() -> None:
    first = run_key("native-00-0", EXPECTED_CONFIG_FINGERPRINT, "dataset", "plan")
    second = run_key("native-00-0", EXPECTED_CONFIG_FINGERPRINT, "dataset", "plan")
    different = run_key("native-00-1", EXPECTED_CONFIG_FINGERPRINT, "dataset", "plan")
    assert first == second
    assert first != different


def test_run_key_includes_final_identity() -> None:
    base = run_key("native-00-0", EXPECTED_CONFIG_FINGERPRINT, "dataset", "plan")
    changed_config = run_key("native-00-0", "changed", "dataset", "plan")
    changed_dataset = run_key("native-00-0", EXPECTED_CONFIG_FINGERPRINT, "changed", "plan")
    changed_plan = run_key("native-00-0", EXPECTED_CONFIG_FINGERPRINT, "dataset", "changed")
    assert len({base, changed_config, changed_dataset, changed_plan}) == 4


def test_canonical_hash_is_stable_for_manifest_payload() -> None:
    payload = {"query_count": 200, "seed": 42, "config": EXPECTED_CONFIG_FINGERPRINT}
    assert canonical_hash(payload) == canonical_hash(json.loads(json.dumps(payload)))


def test_config_identity_drift_is_fail_closed() -> None:
    from scripts.experiments.run_development200 import load_and_assert_identity

    config, _fingerprints, questions, fingerprint, _plan, _sample, split_hash = load_and_assert_identity()
    assert config["config_fingerprint"] == EXPECTED_CONFIG_FINGERPRINT
    assert fingerprint == EXPECTED_CONFIG_FINGERPRINT
    assert len(questions) == 200
    assert len(split_hash) == 64


@pytest.mark.parametrize("state", ["PERSISTED_COMPLETE", "GENERATION_COMPLETE", "FAILED_PROVIDER", "FAILED_SCORER"])
def test_checkpoint_states_are_explicit(state: str) -> None:
    assert state in {"NOT_STARTED", "GENERATION_COMPLETE", "SCORING_COMPLETE", "PERSISTED_COMPLETE", "FAILED_PROVIDER", "FAILED_PARSE", "FAILED_SCORER", "FAILED_PERSISTENCE"}
