from pathlib import Path

from scripts.benchmarks.benchmark_context_builder import SELECTION, _cache, selection_artifact


def test_context_builder_probe_selection_is_fixed_and_balanced():
    metadata, historical, _, questions = _cache()
    selection = selection_artifact(metadata, historical, questions)
    assert selection["probe_count"] == 12
    assert selection["query_ids"] == [item[0] for item in SELECTION]
    assert selection["composition"] == {
        "multi_document": 3,
        "hard_answerable": 3,
        "cross_lingual": 2,
        "version_conflict": 2,
        "standard_answerable": 1,
        "injection_bearing": 1,
    }


def test_context_builder_probe_has_no_retrieval_or_semantic_stage():
    source = Path("scripts/benchmarks/benchmark_context_builder.py").read_text(encoding="utf-8")
    assert "QdrantClient" not in source
    assert "CrossEncoderReranker" not in source
    assert "from app.evaluation.semantic_answerability" not in source


def test_context_builder_probe_artifact_records_isolated_calls():
    import json

    summary = json.loads(
        Path("artifacts/phase-7/context-builder-probe/summary.json").read_text(encoding="utf-8")
    )
    assert summary["calls"] == {
        "a_generation": 0,
        "b_generation": 12,
        "retrieval": 0,
        "embedding": 0,
        "reranker": 0,
        "semantic_evaluator": 0,
    }
    assert summary["evidence_lost"] is False
    assert summary["top5_membership_expanded"] is False
