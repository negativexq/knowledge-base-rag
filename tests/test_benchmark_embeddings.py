from collections import Counter
from unittest.mock import patch

from app.llm.embedding_models import get_embedding_model_config
from app.shared.config import Settings
from scripts.benchmark_embeddings import (
    DEFAULT_CONFIGS,
    DEFAULT_GOLDEN_SET,
    _measure_real_collection_disk_bytes,
    _percentile,
    _sanitize_label,
    collection_name_for,
    load_golden_questions,
    pareto_dominated,
    score,
)


def _config_result(
    label,
    cross_recall=0.5,
    cross_mrr=0.5,
    mono_recall=0.9,
    ndcg=0.5,
    dimension=1024,
    p95=100.0,
    supported=True,
):
    if not supported:
        return {"label": label, "supported": False, "requested_dimension": dimension,
                 "actual_dimension_returned": 0}
    return {
        "label": label,
        "supported": True,
        "requested_dimension": dimension,
        "actual_dimension_returned": dimension,
        "cross_lingual": {"recall_at_5": cross_recall, "mrr": cross_mrr, "ndcg_at_5": cross_recall},
        "mono_lingual": {"recall_at_5": mono_recall, "mrr": mono_recall, "ndcg_at_5": mono_recall},
        "overall": {"ndcg_at_5": ndcg},
        "operational": {"query_embed_p95_ms": p95},
    }


# ---- pure helper functions ----


def test_percentile_p50_of_odd_length_list_is_the_middle_value():
    assert _percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_p95_of_uniform_list_is_near_the_top():
    values = [float(i) for i in range(1, 101)]
    assert _percentile(values, 95) >= 95.0


def test_percentile_of_empty_list_is_zero_not_a_crash():
    assert _percentile([], 50) == 0.0
    assert _percentile([], 95) == 0.0


def test_sanitize_label_produces_a_qdrant_safe_collection_suffix():
    assert _sanitize_label("qwen3-0.6b@native") == "qwen3_06b_native"
    assert _sanitize_label("qwen3-4b@1024") == "qwen3_4b_1024"
    assert _sanitize_label("nomic@native") == "nomic_native"


def test_collection_name_for_is_isolated_per_config():
    settings = Settings()
    native = get_embedding_model_config("qwen3-4b", settings)
    truncated = get_embedding_model_config("qwen3-4b", settings, output_dimension=1024)

    names = {collection_name_for(native), collection_name_for(truncated)}

    assert len(names) == 2  # no collision between native and truncated
    assert all(n.startswith("kb_benchmark_") for n in names)


def test_collection_names_are_isolated_across_all_default_configs():
    settings = Settings()
    from scripts.benchmark_embeddings import parse_config_token

    names = {collection_name_for(parse_config_token(t, settings)) for t in DEFAULT_CONFIGS}

    assert len(names) == len(DEFAULT_CONFIGS)  # every default config gets its own collection


# ---- Pareto dominance ----


def test_pareto_dominance_when_another_config_wins_on_every_axis():
    dominated = _config_result("small", cross_recall=0.5, cross_mrr=0.5, dimension=2560, p95=200)
    dominator = _config_result("big", cross_recall=0.6, cross_mrr=0.6, dimension=1024, p95=100)

    assert pareto_dominated(dominated, [dominated, dominator]) == "big"
    assert pareto_dominated(dominator, [dominated, dominator]) is None


def test_pareto_no_dominance_when_trade_off_exists():
    """Higher quality but also higher dimension/latency — a genuine
    trade-off, not dominance either direction.
    """
    a = _config_result("a", cross_recall=0.9, dimension=2560, p95=300)
    b = _config_result("b", cross_recall=0.5, dimension=768, p95=50)

    assert pareto_dominated(a, [a, b]) is None
    assert pareto_dominated(b, [a, b]) is None


def test_pareto_frontier_survives_a_tied_config():
    a = _config_result("a", cross_recall=0.5, cross_mrr=0.5, dimension=1024, p95=100)
    b = _config_result("b", cross_recall=0.5, cross_mrr=0.5, dimension=1024, p95=100)

    # Identical on every axis — neither strictly better, so neither dominates.
    assert pareto_dominated(a, [a, b]) is None
    assert pareto_dominated(b, [a, b]) is None


# ---- score() / production decision rule ----


def test_score_picks_the_highest_weighted_quality_config_as_quality_winner():
    low = _config_result("low", cross_recall=0.3, cross_mrr=0.3, ndcg=0.3)
    high = _config_result("high", cross_recall=0.9, cross_mrr=0.9, ndcg=0.9)

    decision = score([low, high])

    assert decision["quality_winner"] == "high"


def test_score_recommends_a_smaller_config_that_meets_acceptance_thresholds():
    ceiling = _config_result(
        "qwen3-4b@native", cross_recall=0.97, cross_mrr=0.86, mono_recall=1.0,
        ndcg=0.9, dimension=2560, p95=300,
    )
    small_and_close = _config_result(
        "qwen3-0.6b@768", cross_recall=0.95, cross_mrr=0.85, mono_recall=1.0,
        ndcg=0.88, dimension=768, p95=80,
    )

    decision = score([ceiling, small_and_close])

    assert decision["efficiency_winner"] == "qwen3-0.6b@768"
    assert "qwen3-0.6b@768" in decision["production_recommendation"]


def test_score_does_not_recommend_a_config_that_loses_too_much_cross_lingual_quality():
    ceiling = _config_result(
        "qwen3-4b@native", cross_recall=0.97, cross_mrr=0.86, mono_recall=1.0, dimension=2560,
    )
    too_lossy = _config_result(
        "qwen3-0.6b@768", cross_recall=0.70, cross_mrr=0.60, mono_recall=1.0, dimension=768,
    )

    decision = score([ceiling, too_lossy])

    assert decision["efficiency_winner"] != "qwen3-0.6b@768"


def test_score_does_not_recommend_a_config_with_material_mono_lingual_regression():
    ceiling = _config_result(
        "qwen3-4b@native", cross_recall=0.97, cross_mrr=0.86, mono_recall=1.0, dimension=2560,
    )
    mono_regressed = _config_result(
        "qwen3-0.6b@768", cross_recall=0.97, cross_mrr=0.86, mono_recall=0.80, dimension=768,
    )

    decision = score([ceiling, mono_regressed])

    assert decision["efficiency_winner"] != "qwen3-0.6b@768"


def test_score_when_ceiling_itself_is_both_winners():
    ceiling = _config_result("qwen3-4b@native", cross_recall=0.97, dimension=2560)
    worse = _config_result("qwen3-0.6b@768", cross_recall=0.5, dimension=768)

    decision = score([ceiling, worse])

    assert decision["quality_winner"] == "qwen3-4b@native"
    assert decision["efficiency_winner"] == "qwen3-4b@native"
    assert "no smaller/cheaper config met" in decision["production_recommendation"].lower()


def test_score_excludes_unsupported_configs_entirely():
    supported = _config_result("qwen3-4b@native", cross_recall=0.9)
    unsupported = _config_result("qwen3-0.6b@4000", supported=False)

    decision = score([supported, unsupported])

    assert decision["quality_winner"] == "qwen3-4b@native"
    assert "qwen3-0.6b@4000" not in decision["pareto_dominated"]


def test_score_with_no_supported_configs_reports_no_recommendation():
    decision = score([_config_result("x", supported=False)])

    assert decision["quality_winner"] is None
    assert decision["efficiency_winner"] is None


# ---- golden set integrity (shared with Sprint 18 — must not have changed) ----


def test_golden_set_has_at_least_15_questions_in_every_language_pair_cell():
    questions = load_golden_questions(DEFAULT_GOLDEN_SET)
    cells = Counter(
        (q["query_lang"], q["content_lang"]) for q in questions if q.get("content_lang")
    )

    assert cells[("tr", "tr")] >= 15
    assert cells[("en", "en")] >= 15
    assert cells[("tr", "en")] >= 15
    assert cells[("en", "tr")] >= 15


def test_golden_set_is_unchanged_from_sprint_18_question_count():
    """Sprint 19's rule: same 68-question dataset as Sprint 18, for
    apples-to-apples comparison — this sprint must not edit the golden
    set.
    """
    questions = load_golden_questions(DEFAULT_GOLDEN_SET)

    assert len(questions) == 68


# ---- real disk measurement (not the apparent/sparse-file-inflated size) ----


def test_storage_measurement_uses_block_based_du_not_apparent_size():
    """Sprint 19: `du -sb` (--apparent-size) reports Qdrant's PREALLOCATED
    sparse mmap/WAL file sizes, not real disk consumption — verified for
    real to be nearly identical (~211MB) across every config regardless
    of actual dimension. `-sk` (block-based) is what genuinely
    differed between configs when checked directly against the running
    container. This test locks in that the command uses -sk, not -sb.
    """
    with patch("scripts.benchmark_embeddings.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "2444\t/qdrant/storage/collections/x\n"

        result = _measure_real_collection_disk_bytes("x")

        called_args = mock_run.call_args[0][0]
        assert "-sk" in called_args
        assert "-sb" not in called_args
        assert result == 2444 * 1024


def test_storage_measurement_returns_none_when_docker_is_unavailable():
    with patch("scripts.benchmark_embeddings.subprocess.run", side_effect=FileNotFoundError):
        assert _measure_real_collection_disk_bytes("x") is None


def test_storage_measurement_returns_none_on_nonzero_exit():
    with patch("scripts.benchmark_embeddings.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""

        assert _measure_real_collection_disk_bytes("x") is None


def test_default_configs_include_all_six_sprint_19_configurations():
    assert set(DEFAULT_CONFIGS) == {
        "nomic@native",
        "qwen3-0.6b@native",
        "qwen3-4b@native",
        "qwen3-4b@1024",
        "qwen3-0.6b@1024",
        "qwen3-0.6b@768",
    }
