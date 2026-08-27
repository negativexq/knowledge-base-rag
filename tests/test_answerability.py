from app.evaluation.answerability import extract_answerability_observation
from app.retrieval.hybrid_search import SearchResult
from app.shared.config import Settings
from scripts.export_answerability_features import _config_snapshot, load_questions


def _result(score: float, source_id: str, doc_id: str = "doc") -> SearchResult:
    return SearchResult(score=score, payload={"source_id": source_id, "doc_id": doc_id})


def test_features_are_extracted_from_authorized_top_five_only():
    observation = extract_answerability_observation(
        [
            _result(0.9, "source-a", "doc-a"),
            _result(0.5, "source-a", "doc-a"),
            _result(0.1, "source-b", "doc-b"),
        ],
        authorized_candidate_count=3,
    )

    assert observation.reason == "FEATURES_AVAILABLE"
    assert observation.top_authorized_source_ids == ["source-a", "source-a", "source-b"]
    assert observation.features.top1_score == 0.9
    assert observation.features.top1_top2_margin == 0.4
    assert observation.features.top1_top3_margin == 0.8
    assert observation.features.mean_top3_score == 0.5
    assert observation.features.distinct_source_count_top5 == 2
    assert observation.features.distinct_document_count_top5 == 2
    assert observation.features.duplicate_source_chunk_count_top5 == 1


def test_unauthorized_only_case_is_distinguished_without_exposing_sources():
    observation = extract_answerability_observation(
        [], authorized_candidate_count=0, pre_acl_candidate_count=4
    )

    assert observation.reason == "NO_AUTHORIZED_EVIDENCE"
    assert observation.features.pre_acl_candidate_count == 4
    assert observation.top_authorized_source_ids == []
    assert observation.top_raw_reranker_scores == []


def test_empty_retrieval_and_empty_rerank_reasons_are_distinct():
    no_retrieval = extract_answerability_observation(
        [], authorized_candidate_count=0, pre_acl_candidate_count=0
    )
    empty_rerank = extract_answerability_observation(
        [], authorized_candidate_count=2
    )

    assert no_retrieval.reason == "NO_RETRIEVAL_CANDIDATES"
    assert empty_rerank.reason == "EMPTY_RERANK_RESULT"


def test_optional_branch_features_are_null_and_scores_are_not_confidence():
    observation = extract_answerability_observation(
        [_result(-0.2, "source-a")], authorized_candidate_count=1
    )

    features = observation.features
    assert features.top1_score == -0.2
    assert features.top1_fused_rank is None
    assert features.top1_dense_rank is None
    assert features.top1_sparse_rank is None
    assert features.dense_sparse_agreement is None
    assert features.fused_rerank_agreement is None


def test_empty_top_five_has_nullable_numeric_features():
    features = extract_answerability_observation(
        [], authorized_candidate_count=0
    ).features

    assert features.top1_score is None
    assert features.top1_top2_margin is None
    assert features.mean_top5_score is None
    assert features.distinct_source_count_top5 is None


def test_reference_export_profile_uses_candidate_k_20_even_when_dev_fast_is_15():
    settings = Settings(_env_file=None)
    snapshot = _config_snapshot(
        settings,
        {"corpus_fingerprint": "corpus", "dataset_fingerprint": "dataset"},
        "evaluation",
    )

    assert settings.reranker_candidate_k == 15
    assert snapshot["runtime_profile"] == "BENCHMARK_REFERENCE"
    assert snapshot["candidate_k"] == 20
    assert snapshot["generation_invoked"] is False


def test_calibration_and_frozen_split_require_explicit_opt_in(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        '[{"id":"q","split":"calibration"}, {"id":"f","split":"frozen_test"}]',
        encoding="utf-8",
    )

    import pytest

    with pytest.raises(ValueError, match="calibration"):
        load_questions(dataset, "calibration", allow_frozen_test=False)
    with pytest.raises(ValueError, match="frozen_test"):
        load_questions(dataset, "frozen_test", allow_frozen_test=False)
