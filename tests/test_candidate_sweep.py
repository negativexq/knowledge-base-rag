from pathlib import Path

import pytest

from app.evaluation.candidate_sweep import (
    aggregate_case_families,
    classify_rescue_drop,
    post_rerank_metrics,
    pre_rerank_metrics,
    recommend_candidate_k,
    validate_candidate_k,
)
from scripts.benchmark_candidate_k import _load_questions, select_questions


def _record(query_id: str, family: str, **metrics):
    return {"query_id": query_id, "case_family": family, **metrics}


def test_candidate_k_must_cover_top_n():
    validate_candidate_k(5, 5)
    with pytest.raises(ValueError, match="candidate_k must be >= top_n"):
        validate_candidate_k(4, 5)


def test_pre_rerank_metrics_distinguish_any_and_all_required_evidence():
    metrics = pre_rerank_metrics(["a", "d"], ["a", "b"])

    assert metrics["candidate_recall"] == 0.5
    assert metrics["any_required_evidence"] == 1.0
    assert metrics["all_required_evidence"] == 0.0


def test_rescue_and_drop_classification_is_deterministic():
    distractors = ["d1", "d2", "d3", "d4", "d5"]
    assert (
        classify_rescue_drop(distractors + ["gold"], ["gold"] + distractors, ["gold"]) == "rescued"
    )
    assert (
        classify_rescue_drop(["gold"] + distractors, distractors + ["gold"], ["gold"]) == "dropped"
    )
    assert (
        classify_rescue_drop(["gold"] + distractors, ["gold"] + distractors, ["gold"])
        == "unchanged"
    )


def test_post_rerank_metrics_include_required_rank_metrics():
    metrics = post_rerank_metrics(["d", "gold"], ["gold"])

    assert metrics["recall_at_5"] == 1.0
    assert metrics["mrr"] == 0.5
    assert metrics["ndcg_at_5"] > 0


def test_ndcg_perfect_ranking_is_one():
    assert post_rerank_metrics(["gold-a", "gold-b"], ["gold-a", "gold-b"])["ndcg_at_5"] == 1.0


def test_ndcg_lower_rank_is_below_one():
    assert post_rerank_metrics(["distractor", "gold"], ["gold"])["ndcg_at_5"] < 1.0


def test_ndcg_missing_relevant_doc_is_below_one():
    assert post_rerank_metrics(["gold-a"], ["gold-a", "gold-b"])["ndcg_at_5"] < 1.0


def test_ndcg_no_relevant_retrieved_is_zero():
    assert post_rerank_metrics(["distractor-a", "distractor-b"], ["gold"])["ndcg_at_5"] == 0.0


def test_ndcg_multiple_relevant_docs_with_one_missing_is_below_one():
    assert post_rerank_metrics(["gold-a", "distractor"], ["gold-a", "gold-b"])["ndcg_at_5"] < 1.0


def test_ndcg_ideal_normalization_uses_full_binary_relevance_set():
    partial = post_rerank_metrics(["gold-a", "distractor"], ["gold-a", "gold-b"])["ndcg_at_5"]
    perfect = post_rerank_metrics(["gold-a", "gold-b"], ["gold-a", "gold-b"])["ndcg_at_5"]

    assert perfect == 1.0
    assert partial == pytest.approx(1 / (1 + 1 / 1.584962500721156))


def test_ndcg_does_not_double_count_duplicate_chunks_from_one_source():
    metrics = post_rerank_metrics(["gold", "gold", "distractor"], ["gold"])

    assert metrics["ndcg_at_5"] == 1.0


def test_case_family_aggregation_is_sorted_and_deterministic():
    records = [
        _record(
            "q2",
            "family-b",
            candidate_recall=0.0,
            recall_at_10=0.0,
            recall_at_15=0.0,
            recall_at_20=0.0,
            recall_at_5=0.0,
            mrr=0.0,
            ndcg_at_5=0.0,
        ),
        _record(
            "q1",
            "family-a",
            candidate_recall=1.0,
            recall_at_10=1.0,
            recall_at_15=1.0,
            recall_at_20=1.0,
            recall_at_5=1.0,
            mrr=1.0,
            ndcg_at_5=1.0,
        ),
    ]

    assert aggregate_case_families(records) == {
        "case_family_count": 2,
        "candidate_recall": 0.5,
        "any_required_evidence": None,
        "all_required_evidence": None,
        "recall_at_10": 0.5,
        "recall_at_15": 0.5,
        "recall_at_20": 0.5,
        "recall_at_5": 0.5,
        "mrr": 0.5,
        "ndcg_at_5": 0.5,
    }


def test_development_is_default_and_frozen_requires_explicit_opt_in():
    dataset = "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
    questions = _load_questions(Path(dataset), "development", False)
    assert len(questions) == 200
    with pytest.raises(ValueError, match="frozen_test requires"):
        _load_questions(Path(dataset), "frozen_test", False)


def test_category_sampling_is_deterministic():
    dataset = "data/evaluation/evaluation-corpus-v2/golden-dataset-v2.json"
    questions = _load_questions(Path(dataset), "development", False)
    first = select_questions(questions, sample_per_category=1)
    second = select_questions(questions, sample_per_category=1)
    assert [question["id"] for question in first] == [question["id"] for question in second]


def test_recommendation_requires_no_critical_slice_regression():
    def result(k, r5, family_r5, candidate, p95):
        return {
            "candidate_k": k,
            "query_level": {
                "candidate_recall": candidate,
                "all_required_evidence": candidate,
                "recall_at_5": r5,
                "mrr": r5,
                "ndcg_at_5": r5,
            },
            "case_family_level": {"recall_at_5": family_r5},
            "latency": {
                "reranker": {"p95_ms": p95},
                "total_pipeline": {"p95_ms": p95},
            },
        }

    slices = {
        "category": {
            str(k): {
                "cross_lingual": {"query_level": {"recall_at_5": r5}},
                "hard_answerable": {"query_level": {"recall_at_5": r5}},
                "multi_document": {"query_level": {"recall_at_5": r5}},
                "version_conflict": {"query_level": {"recall_at_5": r5}},
                "injection_bearing": {"query_level": {"recall_at_5": r5}},
            }
            for k, r5 in ((20, 1.0), (15, 1.0), (10, 0.8))
        }
    }
    recommendation = recommend_candidate_k(
        [
            result(20, 1.0, 1.0, 1.0, 100),
            result(15, 1.0, 1.0, 0.98, 75),
            result(10, 1.0, 0.9, 0.9, 50),
        ],
        slices,
    )

    assert recommendation["recommendation"] == "PROMOTE 15"
    assert recommendation["automatic_promotion"] is False


def test_partial_20_15_comparison_does_not_require_k10():
    result = {
        "candidate_k": 20,
        "query_level": {
            "candidate_recall": 1.0,
            "all_required_evidence": 1.0,
            "recall_at_5": 1.0,
            "mrr": 1.0,
            "ndcg_at_5": 1.0,
        },
        "case_family_level": {"recall_at_5": 1.0},
        "latency": {"reranker": {"p95_ms": 100.0}, "total_pipeline": {"p95_ms": 110.0}},
    }
    candidate = {**result, "candidate_k": 15}

    critical_slices = (
        "cross_lingual",
        "hard_answerable",
        "multi_document",
        "version_conflict",
        "injection_bearing",
    )
    slices = {
        "category": {
            str(k): {
                name: {"query_level": {"recall_at_5": 1.0}}
                for name in critical_slices
            }
            for k in (20, 15)
        }
    }

    recommendation = recommend_candidate_k([result, candidate], slices)

    assert recommendation["recommendation"] == "PROMOTE 15"
