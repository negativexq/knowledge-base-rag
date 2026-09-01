# ruff: noqa: E501
"""Provider-free contracts for the Phase 7.8 capacity probe."""

from __future__ import annotations

from pathlib import Path

from scripts.benchmarks.benchmark_qwen25_multidoc import (
    MODEL_4B,
    MODEL_7B,
)


def test_probe_changes_only_generator_model() -> None:
    source = Path("scripts/benchmarks/benchmark_qwen25_multidoc.py").read_text(encoding="utf-8")
    assert MODEL_4B in source
    assert MODEL_7B in source
    assert '"prompt": PROMPT' in source
    assert "Context Builder v1" in source
    assert '"retrieval_calls": 0' in source
    assert "qwen3.5:9b" not in source


def test_probe_guards_no_full_run_or_frozen_split() -> None:
    source = Path("scripts/benchmarks/benchmark_qwen25_multidoc.py").read_text(encoding="utf-8")
    assert "development=200" not in source
    assert '"frozen_test_touched": False' in source
    assert '"calibration": False' in source
