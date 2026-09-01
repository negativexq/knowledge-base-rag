from pathlib import Path


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
