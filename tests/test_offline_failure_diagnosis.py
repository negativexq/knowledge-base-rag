# ruff: noqa: E501

"""Provider-free contract tests for the Phase 7.6 offline diagnosis."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.diagnose_offline_failure import (
    classify_acl,
    classify_validator_rejections,
    dataset_questions,
    identity_check,
    review_citations,
)


def _artifacts() -> tuple[dict[str, dict], dict[str, dict], list[dict], dict[tuple[str, str, str], dict]]:
    _, _, cache_rows, b_rows = identity_check()
    questions = dataset_questions([row["query_id"] for row in cache_rows])
    from scripts.diagnose_offline_failure import chunk_index

    return questions, b_rows, cache_rows, chunk_index(cache_rows)


def test_phase_7_6_artifact_identity_and_exact_review_set() -> None:
    actual, _, cache_rows, b_rows = identity_check()

    assert actual["generator"] == "qwen3.5:4b"
    assert actual["prompt"] == "v3"
    assert actual["think"] is False
    assert len(cache_rows) == 36
    assert len(b_rows) == 36

    questions, rows, cache_rows, chunks = _artifacts()
    review = review_citations(rows, questions, cache_rows, chunks)
    assert len(review) == 23
    assert len({item["query_id"] for item in review}) == 15


def test_phase_7_6_required_diagnostic_slices_are_exact() -> None:
    questions, rows, cache_rows, chunks = _artifacts()
    review = review_citations(rows, questions, cache_rows, chunks)
    assert len(review) == 23
    assert sum(row["category"] == "multi_document" for row in rows.values()) == 3
    assert len(classify_acl(rows)) == 3
    assert len(classify_validator_rejections(rows)) == 8


def test_phase_7_6_no_inference_or_retrieval_clients_in_script() -> None:
    source = Path("scripts/diagnose_offline_failure.py").read_text(encoding="utf-8")
    forbidden = ("ollama", "qdrant", "reranker", "openai", "anthropic", "deep_eval")
    lowered = source.casefold()
    assert not any(f"import {name}" in lowered or f"from {name}" in lowered for name in forbidden)


def test_phase_7_6_outputs_are_json_serializable() -> None:
    output = Path("artifacts/phase-7/offline-failure-diagnosis")
    for path in output.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in output.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
