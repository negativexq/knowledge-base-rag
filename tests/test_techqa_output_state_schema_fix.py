import pytest

from scripts.run_techqa_output_state_schema_fix import (
    assert_debug_only,
    preflight_allows_official,
    require_preflight_for_official,
    target_ids,
)


def test_debug_target_is_disjoint_from_frozen_holdout() -> None:
    ids = target_ids()
    assert len(ids) == 11
    assert_debug_only(ids)


def test_successful_matching_preflight_allows_official_calls() -> None:
    payload = {
        "schema_acceptance": True,
        "result": {"state": "RAW_COMPLETE", "schema_hash": "schema-v2"},
    }
    assert preflight_allows_official(payload, schema_hash="schema-v2") is True
    require_preflight_for_official(payload, schema_hash="schema-v2")


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_acceptance": False, "result": {"state": "FAILED_PROVIDER"}},
        {
            "schema_acceptance": True,
            "result": {"state": "FAILED_PROVIDER", "schema_hash": "schema-v2"},
        },
        {
            "schema_acceptance": True,
            "result": {"state": "RAW_COMPLETE", "schema_hash": "old-schema"},
        },
    ],
)
def test_failed_or_stale_preflight_blocks_official_calls(payload: dict) -> None:
    assert preflight_allows_official(payload, schema_hash="schema-v2") is False
    with pytest.raises(RuntimeError, match="PREFLIGHT_GATE_BLOCKED_OFFICIAL_CALLS"):
        require_preflight_for_official(payload, schema_hash="schema-v2")
