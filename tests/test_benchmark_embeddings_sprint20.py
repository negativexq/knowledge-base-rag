from scripts.benchmark_embeddings import (
    SPRINT20_CONFIGS,
    SPRINT20_GOLDEN_SET,
    _subset_question_ids,
    compute_bootstrap_report,
    render_sprint20_extra_section,
    sprint20_production_decision,
)


def _result(label, cross_recall5, cross_mrr, mono_recall5, dimension, p95, per_question=None):
    return {
        "label": label,
        "supported": True,
        "requested_dimension": dimension,
        "cross_lingual": {
            "recall_at_5": cross_recall5, "mrr": cross_mrr, "ndcg_at_5": cross_recall5
        },
        "mono_lingual": {
            "recall_at_5": mono_recall5, "mrr": mono_recall5, "ndcg_at_5": mono_recall5
        },
        "overall": {"ndcg_at_5": cross_recall5},
        "operational": {"query_embed_p95_ms": p95},
        "per_question": per_question or {},
    }


def _bootstrap_entry(metric, subset, lower, upper, observed=None):
    return {
        "compared_configs": ["qwen3-0.6b@768", "qwen3-4b@1024"],
        "metric": metric,
        "subset": subset,
        "observed_delta": observed if observed is not None else (lower + upper) / 2,
        "lower_ci": lower,
        "upper_ci": upper,
        "seed": 1,
        "iterations": 5000,
        "n_questions": 100,
    }


# ---- production decision: within tolerance, CI agrees -> small wins ----


def test_production_decision_recommends_small_when_within_tolerance_and_ci_agrees():
    small = _result("qwen3-0.6b@768", cross_recall5=0.93, cross_mrr=0.72, mono_recall5=1.0,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.96, cross_mrr=0.75, mono_recall5=1.0,
                     dimension=1024, p95=260)
    bootstrap_entries = [
        _bootstrap_entry("recall_at_5", "cross_lingual", lower=-0.06, upper=0.02),
        _bootstrap_entry("mrr", "cross_lingual", lower=-0.07, upper=0.01),
    ]

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large}, bootstrap_entries
    )

    assert decision["production_winner"] == "qwen3-0.6b@768"
    assert decision["within_tolerance"]
    assert not decision["ci_confirms_material_gap"]


# ---- production decision: exceeds tolerance, CI confirms -> large wins ----


def test_production_decision_recommends_large_when_gap_exceeds_tolerance_and_ci_confirms():
    small = _result("qwen3-0.6b@768", cross_recall5=0.70, cross_mrr=0.50, mono_recall5=1.0,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.97, cross_mrr=0.80, mono_recall5=1.0,
                     dimension=1024, p95=260)
    bootstrap_entries = [
        _bootstrap_entry("recall_at_5", "cross_lingual", lower=-0.35, upper=-0.20),
        _bootstrap_entry("mrr", "cross_lingual", lower=-0.40, upper=-0.25),
    ]

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large}, bootstrap_entries
    )

    assert decision["production_winner"] == "qwen3-4b@1024"
    assert not decision["within_tolerance"]
    assert decision["ci_confirms_material_gap"]


# ---- production decision: point estimate and CI disagree -> NEED_MORE_DATA ----


def test_production_decision_is_need_more_data_when_point_estimate_and_ci_disagree():
    """Point estimate says within tolerance, but the CI's upper bound
    still shows a gap beyond the threshold — genuine ambiguity, not a
    confident answer either direction.
    """
    small = _result("qwen3-0.6b@768", cross_recall5=0.94, cross_mrr=0.73, mono_recall5=1.0,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.96, cross_mrr=0.75, mono_recall5=1.0,
                     dimension=1024, p95=260)
    # Point estimate loss is small (within tolerance) but the CI is wide
    # and its upper bound still exceeds -threshold.
    bootstrap_entries = [
        _bootstrap_entry("recall_at_5", "cross_lingual", lower=-0.30, upper=-0.05),
        _bootstrap_entry("mrr", "cross_lingual", lower=-0.30, upper=-0.06),
    ]

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large}, bootstrap_entries
    )

    assert decision["production_winner"] == "NEED_MORE_DATA"


def test_production_decision_is_need_more_data_when_configs_missing():
    decision = sprint20_production_decision({}, [])

    assert decision["production_winner"] == "NEED_MORE_DATA"


# ---- production decision: crisis floor -> nomic wins ----


def test_production_decision_falls_back_to_nomic_when_both_qwen_candidates_are_in_crisis():
    small = _result("qwen3-0.6b@768", cross_recall5=0.30, cross_mrr=0.20, mono_recall5=0.9,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.35, cross_mrr=0.25, mono_recall5=0.9,
                     dimension=1024, p95=260)
    nomic = _result("nomic@768", cross_recall5=0.60, cross_mrr=0.40, mono_recall5=1.0,
                     dimension=768, p95=45)
    bootstrap_entries = [
        _bootstrap_entry("recall_at_5", "cross_lingual", lower=-0.10, upper=0.05),
        _bootstrap_entry("mrr", "cross_lingual", lower=-0.10, upper=0.05),
    ]

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large, "nomic@768": nomic},
        bootstrap_entries,
    )

    assert decision["production_winner"] == "nomic@768"


# ---- quality / efficiency winners ----


def test_quality_winner_is_the_highest_weighted_score_config():
    small = _result("qwen3-0.6b@768", cross_recall5=0.90, cross_mrr=0.70, mono_recall5=1.0,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.97, cross_mrr=0.80, mono_recall5=1.0,
                     dimension=1024, p95=260)

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large}, []
    )

    assert decision["quality_winner"] == "qwen3-4b@1024"


def test_efficiency_winner_prefers_lower_dimension_and_lower_latency():
    small = _result("qwen3-0.6b@768", cross_recall5=0.90, cross_mrr=0.70, mono_recall5=1.0,
                     dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.97, cross_mrr=0.80, mono_recall5=1.0,
                     dimension=1024, p95=260)

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": small, "qwen3-4b@1024": large}, []
    )

    assert decision["efficiency_winner"] == "qwen3-0.6b@768"


def test_efficiency_winner_excludes_a_fast_but_much_lower_quality_config_even_above_crisis_floor():
    """Regression test for a real bug caught by actually running Sprint
    20's benchmark: nomic@768 (cross_recall5=0.58, well above the 0.5
    crisis floor but far below both Qwen candidates) used to win
    EFFICIENCY WINNER purely on latency, despite being clearly worse in
    quality than every other option. The fix makes the quality bar
    relative to the best config, not an absolute floor.
    """
    nomic = _result("nomic@768", cross_recall5=0.58, cross_mrr=0.42, mono_recall5=0.92,
                     dimension=768, p95=45)
    small = _result("qwen3-0.6b@768", cross_recall5=0.91, cross_mrr=0.70, mono_recall5=0.98,
                     dimension=768, p95=137)
    large = _result("qwen3-4b@1024", cross_recall5=0.96, cross_mrr=0.75, mono_recall5=1.0,
                     dimension=1024, p95=256)

    decision = sprint20_production_decision(
        {"nomic@768": nomic, "qwen3-0.6b@768": small, "qwen3-4b@1024": large}, []
    )

    assert decision["efficiency_winner"] != "nomic@768"
    assert decision["efficiency_winner"] == "qwen3-0.6b@768"


def test_efficiency_winner_excludes_configs_below_the_crisis_floor():
    crisis = _result("qwen3-0.6b@768", cross_recall5=0.10, cross_mrr=0.05, mono_recall5=1.0,
                      dimension=768, p95=140)
    large = _result("qwen3-4b@1024", cross_recall5=0.97, cross_mrr=0.80, mono_recall5=1.0,
                     dimension=1024, p95=260)

    decision = sprint20_production_decision(
        {"qwen3-0.6b@768": crisis, "qwen3-4b@1024": large}, []
    )

    assert decision["efficiency_winner"] == "qwen3-4b@1024"  # the only non-crisis config


# ---- subset filtering ----


def test_subset_question_ids_cross_lingual_excludes_mono_and_not_found():
    questions = [
        {"id": "a", "query_lang": "tr", "content_lang": "en"},
        {"id": "b", "query_lang": "en", "content_lang": "tr"},
        {"id": "c", "query_lang": "tr", "content_lang": "tr"},
        {"id": "d", "query_lang": "en", "content_lang": "en"},
        {"id": "nf", "query_lang": "tr", "content_lang": None, "expect_not_found": True},
    ]

    cross = _subset_question_ids(questions, "cross_lingual")

    assert cross == {"a", "b"}


def test_subset_question_ids_mono_lingual_excludes_cross_and_not_found():
    questions = [
        {"id": "a", "query_lang": "tr", "content_lang": "en"},
        {"id": "c", "query_lang": "tr", "content_lang": "tr"},
        {"id": "d", "query_lang": "en", "content_lang": "en"},
        {"id": "nf", "query_lang": "tr", "content_lang": None, "expect_not_found": True},
    ]

    mono = _subset_question_ids(questions, "mono_lingual")

    assert mono == {"c", "d"}


def test_subset_question_ids_overall_excludes_only_not_found():
    questions = [
        {"id": "a", "query_lang": "tr", "content_lang": "en"},
        {"id": "nf", "query_lang": "tr", "content_lang": None, "expect_not_found": True},
    ]

    overall = _subset_question_ids(questions, "overall")

    assert overall == {"a"}


def test_subset_question_ids_rejects_unknown_subset():
    import pytest

    with pytest.raises(ValueError, match="Unknown subset"):
        _subset_question_ids([], "not_a_real_subset")


# ---- compute_bootstrap_report: paired, id-keyed, deterministic ----


def test_compute_bootstrap_report_pairs_by_question_id_not_position():
    questions = [
        {"id": "q1", "query_lang": "tr", "content_lang": "en"},
        {"id": "q2", "query_lang": "tr", "content_lang": "en"},
    ]
    # Deliberately different insertion order between the two configs —
    # pairing must still be correct because it's keyed by id.
    result_a = _result(
        "a", 0.5, 0.5, 1.0, 768, 100,
        per_question={"q2": {"recall_at_1": 0.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                               "mrr": 0.5, "ndcg_at_5": 0.5},
                       "q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                               "mrr": 1.0, "ndcg_at_5": 1.0}},
    )
    result_b = _result(
        "b", 0.5, 0.5, 1.0, 1024, 200,
        per_question={"q1": {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0,
                               "mrr": 0.0, "ndcg_at_5": 0.0},
                       "q2": {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0,
                               "mrr": 0.0, "ndcg_at_5": 0.0}},
    )

    entries = compute_bootstrap_report(result_a, result_b, questions, seed=1, iterations=200)

    recall5_cross = next(
        e for e in entries if e["metric"] == "recall_at_5" and e["subset"] == "cross_lingual"
    )
    # a: q1=1.0, q2=1.0 -> mean 1.0; b: q1=0.0, q2=0.0 -> mean 0.0; delta=1.0
    assert recall5_cross["observed_delta"] == 1.0
    assert recall5_cross["n_questions"] == 2


def test_compute_bootstrap_report_is_deterministic_for_a_fixed_seed():
    questions = [{"id": "q1", "query_lang": "tr", "content_lang": "en"}]
    pq_a = {"q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                    "mrr": 1.0, "ndcg_at_5": 1.0}}
    pq_b = {"q1": {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0,
                    "mrr": 0.0, "ndcg_at_5": 0.0}}
    result_a = _result("a", 0.5, 0.5, 1.0, 768, 100, per_question=pq_a)
    result_b = _result("b", 0.5, 0.5, 1.0, 1024, 200, per_question=pq_b)

    first = compute_bootstrap_report(result_a, result_b, questions, seed=42, iterations=500)
    second = compute_bootstrap_report(result_a, result_b, questions, seed=42, iterations=500)

    assert first == second


def test_compute_bootstrap_report_skips_questions_missing_from_either_config():
    questions = [
        {"id": "q1", "query_lang": "tr", "content_lang": "en"},
        {"id": "q2", "query_lang": "tr", "content_lang": "en"},
    ]
    pq_a = {"q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                    "mrr": 1.0, "ndcg_at_5": 1.0}}  # q2 missing (e.g. not-found for this config)
    pq_b = {"q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                    "mrr": 1.0, "ndcg_at_5": 1.0},
            "q2": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                    "mrr": 1.0, "ndcg_at_5": 1.0}}
    result_a = _result("a", 1.0, 1.0, 1.0, 768, 100, per_question=pq_a)
    result_b = _result("b", 1.0, 1.0, 1.0, 1024, 200, per_question=pq_b)

    entries = compute_bootstrap_report(result_a, result_b, questions, seed=1, iterations=200)

    recall5_cross = next(
        e for e in entries if e["metric"] == "recall_at_5" and e["subset"] == "cross_lingual"
    )
    assert recall5_cross["n_questions"] == 1  # only q1, the shared question


# ---- sprint 20 constants / report rendering smoke test ----


def test_sprint20_configs_are_exactly_the_three_specified():
    assert SPRINT20_CONFIGS == ["nomic@768", "qwen3-0.6b@768", "qwen3-4b@1024"]


def test_sprint20_golden_set_points_at_the_v2_fixture():
    assert SPRINT20_GOLDEN_SET == "tests/fixtures/embedding_benchmark_golden_v2.json"


def test_render_sprint20_extra_section_includes_all_three_verdicts():
    bootstrap_entries = [_bootstrap_entry("recall_at_5", "cross_lingual", -0.02, 0.01)]
    decision = {
        "quality_winner": "qwen3-4b@1024",
        "efficiency_winner": "qwen3-0.6b@768",
        "production_winner": "qwen3-0.6b@768",
        "reason": "test reason",
        "loss_vs_large": {"cross_recall_at_5": 0.01},
        "within_tolerance": True,
        "ci_confirms_material_gap": False,
        "thresholds": {"max_cross_recall_at_5_loss": 0.03},
    }

    section = render_sprint20_extra_section(bootstrap_entries, decision)

    assert "QUALITY WINNER: qwen3-4b@1024" in section
    assert "EFFICIENCY WINNER: qwen3-0.6b@768" in section
    assert "PRODUCTION WINNER: qwen3-0.6b@768" in section
