from __future__ import annotations

import json
from pathlib import Path

from app.reranker.cross_encoder import CrossEncoderReranker
from app.retrieval.hybrid_search import SearchResult
from scripts.benchmarks import benchmark_reranker_ablation as ablation

OUT = Path("artifacts/phase-7/reranker-ablation")


def test_forensic_artifact_has_locked_identity_and_three_queries() -> None:
    identity = json.loads((OUT / "artifact-identity.json").read_text())
    assert identity["git_sha"] == "63dbd8ed89a35c31f0968bc1ce93770fb8954602"
    assert identity["candidate_k"] == 20
    assert identity["top_n"] == 5
    manifest = json.loads((OUT / "forensic-query-manifest.json").read_text())
    assert manifest["query_ids"] == list(ablation.QUERY_IDS)


def test_fact_passage_metric_is_distinct_from_source_recall() -> None:
    metrics = json.loads((OUT / "fact-level-forensic-comparison.json").read_text())
    assert metrics["bge"]["fact_passage_recall"]["at5"] == 5 / 7
    assert metrics["bge"]["source_recall_at5"] == 1.0
    assert metrics["qwen3"]["fact_passage_recall"]["at5"] == 4 / 7


def test_reranker_adapter_preserves_candidate_identity_with_mocked_scores() -> None:
    class FakeModel:
        def predict(self, pairs):
            assert len(pairs) == 3
            return [0.1, 0.9, 0.2]

    reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)
    reranker._model = FakeModel()
    candidates = [
        SearchResult(0.0, {"text": "a"}, "a"),
        SearchResult(0.0, {"text": "b"}, "b"),
        SearchResult(0.0, {"text": "c"}, "c"),
    ]
    ranked = reranker.rerank("q", candidates, 2)
    assert [item.id for item in ranked] == ["b", "c"]
    assert [item.payload["text"] for item in ranked] == ["b", "c"]


def test_ablation_did_not_run_generation_or_closed_splits() -> None:
    config = json.loads((OUT / "experiment-config.json").read_text())
    assert config["generation_calls"] == 0
    assert config["frozen_test"] is False
    assert config["calibration"] is False
    assert json.loads((OUT / "development-manifest.json").read_text())["status"] == "SKIPPED"


def test_qwen_quality_regression_is_fail_closed_and_not_promoted() -> None:
    decision = json.loads((OUT / "decision.json").read_text())
    assert decision["status"] == "QWEN3_RERANKER_QUALITY_REGRESSION"
    assert decision["development_benchmark_status"] == "SKIPPED"
    assert decision["runtime_promotion"] is False


def test_no_closed_model_or_generation_wiring_in_ablation_script() -> None:
    source = Path(ablation.__file__).read_text()
    assert "qwen3.5:9b" not in source
    assert "qwen2.5" not in source
    assert "stream_answer" not in source
    assert "frozen_test" in source
