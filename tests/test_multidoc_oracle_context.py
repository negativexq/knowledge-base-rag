# ruff: noqa: E501
"""Phase 7.9 strict oracle-context precondition tests."""

from __future__ import annotations

import inspect

from scripts import diagnose_multidoc_oracle_context as oracle


def _loaded():
    actual, cache, baseline, dataset = oracle.load_inputs()
    manifests = [oracle.analyze_query(cache[query_id], dataset[query_id]) for query_id in oracle.ORDERED_IDS]
    return actual, cache, baseline, dataset, manifests


def test_exact_canonical_multidoc_queries_and_identity():
    actual, cache, baseline, dataset, manifests = _loaded()
    assert oracle.ORDERED_IDS == ("multi-00-1", "multi-00-3", "multi-03-0")
    assert actual["generator"] == "qwen3.5:4b"
    assert actual["prompt"] == "v3"
    assert actual["think"] is False
    assert all(query_id in cache and query_id in baseline and query_id in dataset for query_id in oracle.ORDERED_IDS)
    assert len(manifests) == 3


def test_oracle_selection_fails_closed_without_authored_chunk_gold():
    _, _, _, _, manifests = _loaded()
    assert all(not item["oracle_eligible"] for item in manifests)
    assert all("NO_AUTHORED_CHUNK_LEVEL_GOLD_MAPPING" in item["precondition_failure_reasons"] for item in manifests)
    assert all(item["oracle_context_chunk_ids"] == [] for item in manifests)


def test_required_14_day_fact_is_not_explicit_in_two_cached_top5_records():
    _, _, _, _, manifests = _loaded()
    by_id = {item["query_id"]: item for item in manifests}
    for query_id in ("multi-00-1", "multi-00-3"):
        checks = by_id[query_id]["fact_explicit_checks"]
        assert checks[0]["component"] == "14 calendar days"
        assert checks[0]["explicit_support"] is False
        assert "REQUIRED_FACT_NOT_EXPLICIT_IN_TOP5_SOURCE_CANDIDATES" in by_id[query_id]["precondition_failure_reasons"]


def test_oracle_never_adds_evidence_and_preserves_citation_identity_candidates():
    _, cache, _, _, manifests = _loaded()
    for item in manifests:
        original = set(item["original_top5_chunk_ids"])
        oracle_ids = set(item["oracle_context_chunk_ids"])
        source_candidates = set(item["source_derived_candidate_chunk_ids"])
        assert oracle_ids <= original
        assert source_candidates <= original
        assert source_candidates == {
            chunk["chunk_id"]
            for chunk in cache[item["query_id"]]["authorized_top5"]
            if chunk["source_id"] in item["required_source_ids"]
        }


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
