# ruff: noqa: E501
"""Provider-free contracts for the Phase 7.7 three-query experiment."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.context_builder import build_context_v1
from app.evaluation.generation_baseline import chunks_from_cache
from app.llm.prompt import build_messages
from scripts.benchmark_multidoc_completeness import (
    BASE_PROMPT,
    COMPLETENESS_CONTRACT,
    EXPECTED_IDS,
    EXPERIMENT_PROMPT,
    serialization_preflight,
    validate_inputs,
)


def test_exact_existing_multidoc_selection_and_identity() -> None:
    actual, historical, cache, questions = validate_inputs()
    assert actual["generator"] == "qwen3.5:4b"
    assert actual["prompt"] == BASE_PROMPT
    assert actual["think"] is False
    assert set(cache) == EXPECTED_IDS
    assert set(historical) >= EXPECTED_IDS
    assert set(questions) == EXPECTED_IDS


def test_serialization_preflight_passes_before_inference() -> None:
    _, _, cache, questions = validate_inputs()
    preflight = serialization_preflight(cache, questions)
    assert preflight["status"] == "PASS"
    assert preflight["checked_before_inference"] is True
    assert preflight["json_round_trip"] is True
    assert preflight["prompt_suffix_contains_no_chain_of_thought_request"] is True


def test_candidate_changes_only_the_system_prompt_suffix() -> None:
    _, _, cache, questions = validate_inputs()
    query_id = sorted(cache)[0]
    builder = build_context_v1(chunks_from_cache(cache[query_id]), max_context_tokens=2600)
    base = build_messages(
        questions[query_id]["question"], builder.chunks, version=BASE_PROMPT,
        context_serializer=lambda _chunks, rendered=builder.context: rendered,
    )
    candidate = build_messages(
        questions[query_id]["question"], builder.chunks, version=BASE_PROMPT,
        context_serializer=lambda _chunks, rendered=builder.context: rendered,
        system_prompt_suffix=COMPLETENESS_CONTRACT,
    )
    assert candidate[1] == base[1]
    assert candidate[0]["content"].startswith(base[0]["content"])
    assert COMPLETENESS_CONTRACT in candidate[0]["content"]


def test_completeness_contract_is_experiment_only_and_minimal() -> None:
    source = Path("scripts/benchmark_multidoc_completeness.py").read_text(encoding="utf-8")
    assert EXPERIMENT_PROMPT != BASE_PROMPT
    assert "Answer every distinct component" in COMPLETENESS_CONTRACT
    assert "Do not reveal internal reasoning" in COMPLETENESS_CONTRACT
    assert "new retrieval" not in source.casefold()
    assert "neighbor" not in source.casefold()


def test_experiment_has_no_full_development_or_frozen_execution_path() -> None:
    source = Path("scripts/benchmark_multidoc_completeness.py").read_text(encoding="utf-8")
    assert "development=200" not in source
    assert '"frozen_test_touched": False' in source
    assert '"calibration": False' in source
