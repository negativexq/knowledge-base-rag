import json

import pytest

from scripts.benchmarks.benchmark_context_builder_full import (
    MODEL,
    PROMPT,
    _metrics,
    load_checkpoint,
    serialization_preflight,
    validate_inputs,
)


def test_full_validation_identity_and_composition_are_locked():
    metadata, historical, cache, questions = validate_inputs()
    assert len(historical) == len(cache) == 36
    assert metadata["candidate_k"] == 20
    assert metadata["top_n"] == 5
    assert MODEL == "qwen3.5:4b"
    assert PROMPT == "v3"
    assert {row["category"] for row in historical} >= {
        "standard_answerable", "hard_answerable", "cross_lingual", "multi_document",
        "version_conflict", "injection_bearing", "unanswerable", "acl_negative", "ambiguous",
    }
    assert all(row["query_id"] in questions for row in historical)


def test_serialization_preflight_passes_without_inference():
    _, _, cache, questions = validate_inputs()
    result = serialization_preflight(cache, questions)
    assert result["status"] == "PASS"
    assert result["json_round_trip"] is True
    assert result["atomic_checkpoint"] is True


def test_checkpoint_rejects_duplicate_or_unknown_records(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    row = {"query_id": "acl-02-0", "category": "acl_negative", "context_builder": {}}
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_checkpoint(path, ["acl-02-0"])

    path.write_text(json.dumps({**row, "query_id": "unknown"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_checkpoint(path, ["acl-02-0"])


def test_metrics_handle_nested_builder_citations_and_non_answerable_rows():
    row = {
        "answerability": "unanswerable",
        "all_required_present": False,
        "fact_score": {"status": "NOT_APPLICABLE"},
        "generation_latency_ms": 1.0,
        "validator_pass": True,
        "citations": {"identity_valid": True},
    }
    metrics = _metrics([row])
    assert metrics["fully_correct_complete"] == 0
    assert metrics["citation_identity_pass"] == 1
