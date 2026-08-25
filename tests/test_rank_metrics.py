from app.evaluation.rank_metrics import aggregate_rank_metrics, compute_rank_metrics

A = ("filesystem", "doc", "1/0")
B = ("filesystem", "doc", "2/0")
C = ("filesystem", "doc", "3/0")
D = ("filesystem", "doc", "4/0")


def test_expected_at_rank_1_gives_perfect_scores():
    metrics = compute_rank_metrics([A, B, C], [A])

    assert metrics.recall_at_1 == 1.0
    assert metrics.recall_at_3 == 1.0
    assert metrics.recall_at_5 == 1.0
    assert metrics.reciprocal_rank == 1.0
    assert metrics.ndcg_at_5 == 1.0


def test_expected_at_rank_3_misses_recall_at_1_but_not_recall_at_3():
    metrics = compute_rank_metrics([B, C, A, D], [A])

    assert metrics.recall_at_1 == 0.0
    assert metrics.recall_at_3 == 1.0
    assert metrics.reciprocal_rank == 1 / 3
    assert 0.0 < metrics.ndcg_at_5 < 1.0


def test_expected_beyond_rank_5_scores_zero_everywhere():
    metrics = compute_rank_metrics([B, C, D, A, A, A], [("filesystem", "doc", "9/9")])

    assert metrics.recall_at_1 == 0.0
    assert metrics.recall_at_5 == 0.0
    assert metrics.reciprocal_rank == 0.0
    assert metrics.ndcg_at_5 == 0.0


def test_no_expected_locations_scores_zero_not_a_crash():
    metrics = compute_rank_metrics([A, B, C], [])

    assert metrics.recall_at_1 == 0.0
    assert metrics.recall_at_5 == 0.0
    assert metrics.reciprocal_rank == 0.0
    assert metrics.ndcg_at_5 == 0.0


def test_multiple_expected_locations_recall_is_fraction_found():
    metrics = compute_rank_metrics([A, C], [A, B])

    assert metrics.recall_at_5 == 0.5


def test_ndcg_rewards_earlier_rank_more_than_later_rank():
    early = compute_rank_metrics([A, B, C], [A])
    late = compute_rank_metrics([B, C, A], [A])

    assert early.ndcg_at_5 > late.ndcg_at_5


def test_aggregate_rank_metrics_averages_across_questions():
    perfect = compute_rank_metrics([A], [A])
    miss = compute_rank_metrics([B], [A])

    aggregated = aggregate_rank_metrics([perfect, miss])

    assert aggregated["recall_at_1"] == 0.5
    assert aggregated["mrr"] == 0.5


def test_aggregate_rank_metrics_of_empty_list_is_zero_not_a_crash():
    aggregated = aggregate_rank_metrics([])

    assert aggregated == {
        "recall_at_1": 0.0,
        "recall_at_3": 0.0,
        "recall_at_5": 0.0,
        "mrr": 0.0,
        "ndcg_at_5": 0.0,
    }
