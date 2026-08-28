# ruff: noqa: E501
"""Provider-free contracts for the Phase 7.8 capacity probe."""

from __future__ import annotations

from pathlib import Path

from scripts.benchmark_qwen25_multidoc import (
    IDS,
    MODEL_4B,
    MODEL_7B,
    PROMPT,
    preflight,
    validate_inputs,
)


def test_exact_three_query_probe_and_locked_identity() -> None:
    actual, baseline, cache, questions = validate_inputs()
    assert actual["generator"] == MODEL_4B
    assert actual["prompt"] == PROMPT
    assert actual["think"] is False
    assert set(cache) == IDS
    assert set(baseline) >= IDS
    assert set(questions) == IDS


def test_preflight_serializes_the_same_cached_context_before_inference() -> None:
    _, _, cache, questions = validate_inputs()
    result = preflight(cache, questions)
    assert result["status"] == "PASS"
    assert result["checked_before_inference"] is True
    assert result["json_round_trip"] is True


def test_probe_changes_only_generator_model() -> None:
    source = Path("scripts/benchmark_qwen25_multidoc.py").read_text(encoding="utf-8")
    assert MODEL_4B in source
    assert MODEL_7B in source
    assert '"prompt": PROMPT' in source
    assert "Context Builder v1" in source
    assert '"retrieval_calls": 0' in source
    assert "qwen3.5:9b" not in source


def test_probe_guards_no_full_run_or_frozen_split() -> None:
    source = Path("scripts/benchmark_qwen25_multidoc.py").read_text(encoding="utf-8")
    assert "development=200" not in source
    assert '"frozen_test_touched": False' in source
    assert '"calibration": False' in source
