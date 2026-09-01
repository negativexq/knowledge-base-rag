from collections import Counter

import pytest

from app.evaluation.embedding_cache import EmbeddingCache, cache_key
from app.llm.embedding_models import get_embedding_model_config
from app.shared.config import Settings
from scripts.benchmarks.benchmark_stability import (
    BOOTSTRAP_ITERATIONS,
    NON_INFERIORITY_MARGINS,
    _embed_query,
    canonical_per_question_metrics,
    compute_dataset_and_corpus_fingerprints,
    is_retrieval_stable,
    ranking_flip_flags,
    run_distribution,
    stratified_sample,
    vector_delta_stats,
)


def _q(id_, query_lang="en", content_lang="en", expect_not_found=False):
    q = {
        "id": id_,
        "query": f"question {id_}",
        "query_lang": query_lang,
        "content_lang": None if expect_not_found else content_lang,
        "expected_locations": [] if expect_not_found else [["filesystem", "doc", id_]],
    }
    if expect_not_found:
        q["expect_not_found"] = True
    return q


# ---- vector_delta_stats: repeated embedding delta calculation ----


def test_vector_delta_stats_of_identical_vectors_is_zero_delta_perfect_cosine():
    vectors = [[1.0, 0.0, 0.0]] * 5

    stats = vector_delta_stats(vectors)

    assert stats["max_abs_delta"] == 0.0
    assert stats["mean_abs_delta"] == 0.0
    assert stats["mean_cosine_similarity"] == 1.0


def test_vector_delta_stats_detects_a_real_difference():
    vectors = [[1.0, 0.0], [1.0, 0.1], [0.9, 0.0]]

    stats = vector_delta_stats(vectors)

    assert stats["max_abs_delta"] > 0
    assert stats["mean_cosine_similarity"] < 1.0


def test_vector_delta_stats_single_vector_has_no_comparison():
    stats = vector_delta_stats([[1.0, 2.0, 3.0]])

    assert stats["max_abs_delta"] == 0.0
    assert stats["mean_cosine_similarity"] == 1.0


def test_vector_delta_stats_matches_a_known_hand_computed_example():
    # ref=[1,0], v=[0,1]: abs diffs=[1,1], cosine=0 (orthogonal)
    stats = vector_delta_stats([[1.0, 0.0], [0.0, 1.0]])

    assert stats["max_abs_delta"] == 1.0
    assert stats["mean_abs_delta"] == 1.0
    assert stats["mean_cosine_similarity"] == 0.0


# ---- ranking_flip_flags: ranking flip-rate calculation ----


def test_ranking_flip_flags_all_false_when_ranking_is_identical_every_repeat():
    ranked = [("filesystem", "doc", "A"), ("filesystem", "doc", "B")]
    ranked_lists = [ranked, ranked, ranked]
    recalls5 = [1.0, 1.0, 1.0]
    rrs = [1.0, 1.0, 1.0]

    flags = ranking_flip_flags(ranked_lists, recalls5, rrs)

    assert not any(flags.values())


def test_ranking_flip_flags_detects_a_top1_flip():
    ranked_a = [("filesystem", "doc", "A"), ("filesystem", "doc", "B")]
    ranked_b = [("filesystem", "doc", "B"), ("filesystem", "doc", "A")]

    flags = ranking_flip_flags([ranked_a, ranked_b], recalls5=[1.0, 1.0], rrs=[1.0, 0.5])

    assert flags["top1_flip"]
    assert flags["mrr_impacting_flip"]


def test_ranking_flip_flags_bit_level_noise_with_no_ranking_impact_is_all_false():
    """The exact case Sprint 21 was designed to distinguish: the SAME
    ranking across repeats (bit-level embedding noise didn't change
    anything observable) must show every flag as False, even if the
    underlying vectors differed.
    """
    ranked = [("filesystem", "doc", "A"), ("filesystem", "doc", "B"), ("filesystem", "doc", "C")]
    ranked_lists = [ranked, ranked, ranked, ranked]

    flags = ranking_flip_flags(ranked_lists, recalls5=[1.0] * 4, rrs=[1.0] * 4)

    assert flags == {
        "top1_flip": False, "top3_set_change": False, "top5_set_change": False,
        "mrr_impacting_flip": False, "recall_at_5_impacting_flip": False,
    }


def test_ranking_flip_flags_detects_a_recall_at_5_impacting_flip_without_a_top1_flip():
    # top1 stays the same, but recall@5 outcome differs (expected item
    # dropped out of top5 on one repeat).
    ranked_a = [("filesystem", "doc", "A"), ("filesystem", "doc", "X")]
    ranked_b = [("filesystem", "doc", "A"), ("filesystem", "doc", "Y")]

    flags = ranking_flip_flags([ranked_a, ranked_b], recalls5=[1.0, 0.0], rrs=[1.0, 1.0])

    assert not flags["top1_flip"]
    assert flags["recall_at_5_impacting_flip"]
    assert not flags["mrr_impacting_flip"]


# ---- is_retrieval_stable: deterministic tie-breaking check ----


def test_is_retrieval_stable_true_for_identical_repeated_results():
    result = ("a", "0.5", "b", "0.3")
    assert is_retrieval_stable([result, result, result])


def test_is_retrieval_stable_false_when_a_repeat_differs():
    assert not is_retrieval_stable([("a", "0.5"), ("b", "0.5"), ("a", "0.5")])


def test_is_retrieval_stable_true_for_a_single_repeat():
    assert is_retrieval_stable([("a", "0.5")])


# ---- stratified_sample ----


def test_stratified_sample_meets_the_requested_minimum():
    questions = (
        [_q(f"tren{i}", "tr", "en") for i in range(81)]
        + [_q(f"entr{i}", "en", "tr") for i in range(75)]
        + [_q(f"trtr{i}", "tr", "tr") for i in range(25)]
        + [_q(f"enen{i}", "en", "en") for i in range(27)]
        + [_q(f"nf{i}", "tr", expect_not_found=True) for i in range(12)]
    )

    sample = stratified_sample(questions, 50)

    assert len(sample) >= 50


def test_stratified_sample_excludes_not_found_questions():
    questions = [_q("a", "tr", "en"), _q("nf", "tr", expect_not_found=True)]

    sample = stratified_sample(questions, 2)

    assert all(not q.get("expect_not_found") for q in sample)


def test_stratified_sample_covers_all_four_cells_proportionally():
    questions = (
        [_q(f"tren{i}", "tr", "en") for i in range(81)]
        + [_q(f"entr{i}", "en", "tr") for i in range(75)]
        + [_q(f"trtr{i}", "tr", "tr") for i in range(25)]
        + [_q(f"enen{i}", "en", "en") for i in range(27)]
    )

    sample = stratified_sample(questions, 50)
    cells = Counter((q["query_lang"], q["content_lang"]) for q in sample)

    assert set(cells.keys()) == {("tr", "en"), ("en", "tr"), ("tr", "tr"), ("en", "en")}
    assert cells[("tr", "en")] > cells[("tr", "tr")]  # bigger cell -> more samples


def test_stratified_sample_is_deterministic():
    questions = [_q(f"q{i}", "tr", "en") for i in range(30)]

    first = stratified_sample(questions, 10)
    second = stratified_sample(questions, 10)

    assert [q["id"] for q in first] == [q["id"] for q in second]


# ---- canonical_per_question_metrics ----


def test_canonical_per_question_metrics_averages_across_runs():
    passes = [
        {"per_question": {"q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                                   "mrr": 1.0, "ndcg_at_5": 1.0}}},
        {"per_question": {"q1": {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0,
                                   "mrr": 0.0, "ndcg_at_5": 0.0}}},
    ]

    canonical = canonical_per_question_metrics(passes)

    assert canonical["q1"]["recall_at_5"] == 0.5


def test_canonical_per_question_metrics_handles_a_question_missing_from_some_runs():
    passes = [
        {"per_question": {"q1": {"recall_at_1": 1.0, "recall_at_3": 1.0, "recall_at_5": 1.0,
                                   "mrr": 1.0, "ndcg_at_5": 1.0}}},
        {"per_question": {}},  # q1 was a not-found miss or otherwise absent this run
    ]

    canonical = canonical_per_question_metrics(passes)

    assert canonical["q1"]["recall_at_5"] == 1.0  # averaged over only the runs that HAD it


# ---- run_distribution ----


def test_run_distribution_reports_all_required_statistics():
    values = [0.9, 0.92, 0.88, 0.95, 0.85]

    dist = run_distribution(values)

    assert dist["mean"] == sum(values) / len(values)
    assert dist["median"] == 0.9
    assert dist["min"] == 0.85
    assert dist["max"] == 0.95
    assert dist["n_runs"] == 5
    assert dist["stddev"] > 0


def test_run_distribution_of_identical_values_has_zero_stddev():
    dist = run_distribution([0.9, 0.9, 0.9])

    assert dist["stddev"] == 0.0


# ---- dataset fingerprint (Sprint 20 dataset, via the real fixture file) ----


def test_sprint20_dataset_fingerprint_is_a_stable_valid_sha256_hex():
    import json

    with open("tests/fixtures/embedding_benchmark_golden_v2.json", encoding="utf-8") as f:
        questions = json.load(f)

    result_a = compute_dataset_and_corpus_fingerprints(questions)
    result_b = compute_dataset_and_corpus_fingerprints(questions)

    assert result_a == result_b
    assert len(result_a["dataset_fingerprint"]) == 64
    assert len(result_a["corpus_fingerprint"]) == 64
    int(result_a["dataset_fingerprint"], 16)  # valid hex, raises otherwise
    int(result_a["corpus_fingerprint"], 16)


# ---- live vs frozen embedding mode ----


class _FakeOllama:
    def __init__(self):
        self.calls = []

    async def embed(self, text, model, prefix="", dimensions=None):
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embed_query_live_mode_calls_ollama_every_time():
    ollama = _FakeOllama()
    config = get_embedding_model_config("qwen3-0.6b", Settings(), output_dimension=768)

    vector = await _embed_query(ollama, config, "a query", "fp1", cache=None, embedding_mode="live")

    assert vector == [0.1, 0.2, 0.3]
    assert ollama.calls == ["a query"]


@pytest.mark.asyncio
async def test_embed_query_frozen_mode_never_calls_ollama(tmp_path):
    ollama = _FakeOllama()
    config = get_embedding_model_config("qwen3-0.6b", Settings(), output_dimension=768)
    cache = EmbeddingCache(tmp_path / "cache.json")
    key = cache_key(
        config.ollama_model, config.revision, config.dimension, config.query_prefix(),
        "a query", "fp1",
    )
    cache.put(key, [0.9, 0.8, 0.7], fingerprint="fp1")

    vector = await _embed_query(
        ollama, config, "a query", "fp1", cache=cache, embedding_mode="frozen"
    )

    assert vector == [0.9, 0.8, 0.7]
    assert ollama.calls == []  # zero embedding calls — the entire point of frozen mode


@pytest.mark.asyncio
async def test_embed_query_frozen_mode_raises_on_a_missing_cache_entry(tmp_path):
    ollama = _FakeOllama()
    config = get_embedding_model_config("qwen3-0.6b", Settings(), output_dimension=768)
    cache = EmbeddingCache(tmp_path / "cache.json")  # empty — never populated

    with pytest.raises(KeyError, match="No frozen embedding cached"):
        await _embed_query(
            ollama, config, "an uncached query", "fp1", cache=cache, embedding_mode="frozen"
        )
    assert ollama.calls == []  # never silently falls back to a live call


# ---- sprint 21 constants sanity ----


def test_bootstrap_iterations_meets_the_minimum_10000():
    assert BOOTSTRAP_ITERATIONS >= 10000


def test_non_inferiority_margins_are_pre_committed_and_match_the_plan():
    assert NON_INFERIORITY_MARGINS == {
        "cross_recall_at_5": 0.04,
        "cross_mrr": 0.04,
        "mono_recall_at_5": 0.02,
    }
