# ruff: noqa: E501
"""Provider-free contracts for the Phase 7.7 three-query experiment."""

from __future__ import annotations

from pathlib import Path

from scripts.benchmarks.benchmark_multidoc_completeness import (
    BASE_PROMPT,
    COMPLETENESS_CONTRACT,
    EXPERIMENT_PROMPT,
)


def test_completeness_contract_is_experiment_only_and_minimal() -> None:
    source = Path("scripts/benchmarks/benchmark_multidoc_completeness.py").read_text(encoding="utf-8")
    assert EXPERIMENT_PROMPT != BASE_PROMPT
    assert "Answer every distinct component" in COMPLETENESS_CONTRACT
    assert "Do not reveal internal reasoning" in COMPLETENESS_CONTRACT
    assert "new retrieval" not in source.casefold()
    assert "neighbor" not in source.casefold()


def test_experiment_has_no_full_development_or_frozen_execution_path() -> None:
    source = Path("scripts/benchmarks/benchmark_multidoc_completeness.py").read_text(encoding="utf-8")
    assert "development=200" not in source
    assert '"frozen_test_touched": False' in source
    assert '"calibration": False' in source
