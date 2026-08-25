from collections import Counter

from scripts.benchmark_embeddings import (
    DEFAULT_GOLDEN_SET,
    _percentile,
    decide,
    load_golden_questions,
)


def _result(overall_recall=None, cells=None):
    return {"overall": {}, "by_cell": cells or {}}


def _cell(recall_at_5, mrr=0.5):
    return {"recall_at_5": recall_at_5, "mrr": mrr, "recall_at_1": 0.0, "ndcg_at_5": 0.0}


def test_decide_adopts_qwen3_when_both_cross_lingual_cells_improve_and_mono_holds():
    baseline = _result(
        cells={
            "tr_query_en_content": _cell(0.4, mrr=0.3),
            "en_query_tr_content": _cell(0.5, mrr=0.4),
            "tr_query_tr_content": _cell(0.9, mrr=0.8),
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )
    challenger = _result(
        cells={
            "tr_query_en_content": _cell(0.7, mrr=0.6),
            "en_query_tr_content": _cell(0.8, mrr=0.7),
            "tr_query_tr_content": _cell(0.9, mrr=0.8),
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )

    decision = decide(baseline, challenger)

    assert decision["recommendation"] == "ADOPT_QWEN3"


def test_decide_keeps_nomic_when_only_one_cross_lingual_cell_improves():
    baseline = _result(
        cells={
            "tr_query_en_content": _cell(0.4, mrr=0.3),
            "en_query_tr_content": _cell(0.5, mrr=0.4),
            "tr_query_tr_content": _cell(0.9, mrr=0.8),
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )
    challenger = _result(
        cells={
            "tr_query_en_content": _cell(0.7, mrr=0.6),  # improved
            "en_query_tr_content": _cell(0.3, mrr=0.2),  # WORSE
            "tr_query_tr_content": _cell(0.9, mrr=0.8),
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )

    decision = decide(baseline, challenger)

    assert decision["recommendation"] == "KEEP_NOMIC"


def test_decide_keeps_nomic_when_mono_lingual_cell_regresses_materially_despite_cross_gains():
    baseline = _result(
        cells={
            "tr_query_en_content": _cell(0.4, mrr=0.3),
            "en_query_tr_content": _cell(0.5, mrr=0.4),
            "tr_query_tr_content": _cell(0.9, mrr=0.8),
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )
    challenger = _result(
        cells={
            "tr_query_en_content": _cell(0.7, mrr=0.6),
            "en_query_tr_content": _cell(0.8, mrr=0.7),
            "tr_query_tr_content": _cell(0.5, mrr=0.4),  # regressed hard
            "en_query_en_content": _cell(0.9, mrr=0.8),
        }
    )

    decision = decide(baseline, challenger)

    assert decision["recommendation"] == "KEEP_NOMIC"
    assert decision["mono_lingual_recall_at_5_deltas"]["tr_query_tr_content"] < 0


def test_decide_reports_need_more_data_when_a_cell_is_missing():
    baseline = _result(cells={"tr_query_en_content": _cell(0.4)})
    challenger = _result(cells={"tr_query_en_content": _cell(0.7)})

    decision = decide(baseline, challenger)

    assert decision["recommendation"] == "NEED_MORE_DATA"


def test_percentile_p50_of_odd_length_list_is_the_middle_value():
    assert _percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_p95_of_uniform_list_is_near_the_top():
    values = [float(i) for i in range(1, 101)]
    assert _percentile(values, 95) >= 95.0


def test_percentile_of_empty_list_is_zero_not_a_crash():
    assert _percentile([], 50) == 0.0
    assert _percentile([], 95) == 0.0


def test_golden_set_has_at_least_15_questions_in_every_language_pair_cell():
    """Guards the corpus itself, not just the aggregation code — a future
    edit that accidentally shrinks a cell below the sprint's 15-20 target
    should fail a test, not silently degrade the benchmark's statistical
    footing.
    """
    questions = load_golden_questions(DEFAULT_GOLDEN_SET)
    cells = Counter(
        (q["query_lang"], q["content_lang"]) for q in questions if q.get("content_lang")
    )

    assert cells[("tr", "tr")] >= 15
    assert cells[("en", "en")] >= 15
    assert cells[("tr", "en")] >= 15
    assert cells[("en", "tr")] >= 15


def test_golden_set_includes_not_found_control_questions_in_both_languages():
    questions = load_golden_questions(DEFAULT_GOLDEN_SET)
    not_found = [q for q in questions if q.get("expect_not_found")]

    assert {q["query_lang"] for q in not_found} == {"tr", "en"}


def test_golden_set_every_expected_location_has_three_parts():
    questions = load_golden_questions(DEFAULT_GOLDEN_SET)
    for q in questions:
        for loc in q["expected_locations"]:
            assert len(loc) == 3


def test_benchmark_collection_names_are_isolated_per_model():
    # Same naming scheme run_model_benchmark uses — asserted directly so
    # a future rename can't silently make baseline and challenger collide
    # on the same Qdrant collection.
    assert f"kb_benchmark_{'nomic'}" != f"kb_benchmark_{'qwen3-4b'}"
