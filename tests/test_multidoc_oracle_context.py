# ruff: noqa: E501
"""Phase 7.9 strict oracle-context precondition tests."""

from __future__ import annotations

import inspect

from scripts.audits import diagnose_multidoc_oracle_context as oracle


def test_no_provider_retrieval_reranker_or_semantic_gate_path_exists():
    source = inspect.getsource(oracle)
    forbidden = ("OllamaClient", "stream_answer", "QdrantClient", "hybrid_search", "CrossEncoderReranker", "semantic_answerability")
    assert all(token not in source for token in forbidden)
    assert "qwen2.5:7b" not in source
    assert "qwen3.5:9b" not in source


def test_frozen_and_calibration_are_never_touched():
    source = inspect.getsource(oracle.main)
    assert '"frozen_test_touched": False' in source
    assert '"calibration": False' in source
    assert "frozen_test" not in str(oracle.DATASET)
